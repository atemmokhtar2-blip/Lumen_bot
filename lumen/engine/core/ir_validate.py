"""IR validation — strengthen control plane before any engine runs."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lumen.engine.core.ir import AcceptanceCriterion, BuildIR, EngineMode, IRStatus


@dataclass
class IRValidation:
    ok: bool
    ir: BuildIR
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _catalog_keys() -> set[str]:
    try:
        CAPABILITIES = {}

        return set(CAPABILITIES.keys())
    except Exception:
        return set()


def validate_and_normalize_ir(ir: BuildIR) -> IRValidation:
    """Reject empty/unsafe IR; attach kind-aware acceptance (Phase 2)."""
    errors: list[str] = []
    warnings: list[str] = []
    caps = _catalog_keys()

    text = (ir.original_text or ir.spec_request or "").strip()
    if len(text) < 3:
        errors.append("ir_text_too_short")

    # Phase 5: Python-only platform
    try:
        from lumen.engine.security.phase5_bounds import is_python_only_request
        ok_lang, reason = is_python_only_request(text)
        if not ok_lang:
            errors.append(reason or "python_only_v1")
        meta_v = (ir.metadata or {}).get("python_only_violation")
        if meta_v:
            errors.append(str(meta_v))
    except Exception:
        pass

    preferred = [k for k in ir.preferred_keys if not caps or k in caps]
    matched = [k for k in ir.capabilities_matched if not caps or k in caps]
    unknown = [k for k in ir.preferred_keys if caps and k not in caps]
    if unknown:
        warnings.append("dropped_unknown_keys:" + ",".join(unknown[:8]))

    kind = str(getattr(ir, "project_kind", None) or (ir.metadata or {}).get("project_kind") or "").strip().lower()

    # Only force start/help for telegram bots
    if kind in {"", "telegram_bot"}:
        for c in ("start", "help"):
            if caps and c in caps and c not in preferred:
                preferred.append(c)

    ir.preferred_keys = preferred[:20]
    ir.capabilities_matched = matched[:20]
    ir.spec_request = (ir.spec_request or ir.original_text or "").strip()
    if not ir.spec_request:
        # Kind-aware default — never invent a Telegram bot for other kinds
        if kind == "web_site":
            ir.spec_request = text or "Website with home page and health endpoint"
        elif kind == "web_api":
            ir.spec_request = text or "JSON API with health endpoint"
        elif kind == "cli_app":
            ir.spec_request = text or "CLI application with --help"
        elif kind == "library":
            ir.spec_request = text or "Python library package"
        elif kind == "telegram_bot":
            ir.spec_request = text or "Telegram bot with start and help"
        else:
            ir.spec_request = text or "Python project"

    # Preserve kind_gate criteria; add telegram feature gates only for bots
    acc: list[AcceptanceCriterion] = []
    existing = list(ir.acceptance or [])
    for item in existing:
        if getattr(item, "kind", "") == "kind_gate" or str(getattr(item, "id", "")).startswith("kind_"):
            acc.append(item)

    if not acc:
        try:
            from lumen.engine.core.project_kind import acceptance_hints, parse_kind
            pk = parse_kind(kind)
            if pk is not None:
                for i, hint in enumerate(acceptance_hints(pk)):
                    acc.append(
                        AcceptanceCriterion(
                            id=f"kind_{i}_{pk.value}",
                            description=str(hint),
                            kind="kind_gate",
                        )
                    )
        except Exception:
            pass

    if kind in {"", "telegram_bot"}:
        for k in preferred:
            if k in {"start", "help"}:
                continue
            acc.append(
                AcceptanceCriterion(
                    id=f"feat:{k}",
                    description=f"Feature {k} present in generated bot",
                    kind="command",
                )
            )

    acc.append(
        AcceptanceCriterion(
            id="smoke",
            description="Smoke must pass before delivery",
            kind="smoke",
        )
    )
    ir.acceptance = acc

    if errors:
        ir.status = IRStatus.REJECTED
        return IRValidation(ok=False, ir=ir, errors=errors, warnings=warnings)

    ir.status = IRStatus.VALIDATED
    return IRValidation(ok=True, ir=ir, errors=errors, warnings=warnings)



def check_project_against_ir(project_path: str, ir: BuildIR) -> dict[str, Any]:
    """Post-generation acceptance — kind-aware (Phase 2).

    Telegram bots: optional command registration checks for preferred_keys.
    Web / CLI / library: delegate to check_agent_project (no CommandHandler bias).
    """
    from pathlib import Path
    import re

    root = Path(project_path)
    report: dict[str, Any] = {
        "ok": True,
        "missing_features": [],
        "checked": [],
        "path": str(root),
        "project_kind": getattr(ir, "project_kind", None) or (ir.metadata or {}).get("project_kind") or "",
    }

    kind = str(report["project_kind"] or "").strip().lower()
    goal = str(getattr(ir, "raw_request", None) or getattr(ir, "user_request", None) or "")

    # Primary gate: kind-aware structural acceptance
    try:
        from lumen.engine.services.cline_runtime.agent_acceptance import check_agent_project
        agent = check_agent_project(root, goal=goal, project_kind=kind)
        report["agent_acceptance"] = {
            "ok": agent.get("ok"),
            "missing": list(agent.get("missing") or [])[:20],
            "found": list(agent.get("found") or [])[:20],
            "warnings": list(agent.get("warnings") or [])[:12],
            "score": agent.get("score"),
        }
        if not agent.get("ok"):
            report["ok"] = False
            report["missing_features"].extend(str(x) for x in (agent.get("missing") or [])[:20])
    except Exception as exc:
        report["agent_acceptance_error"] = f"{type(exc).__name__}:{exc}"

    # Telegram-only: preferred_keys as CommandHandler names
    if kind in {"", "telegram_bot"} or kind == "telegram_bot":
        main = root / "main.py"
        if main.exists():
            text = main.read_text(encoding="utf-8", errors="ignore")
            cmds = set(re.findall(r"CommandHandler\(\s*['\"]([^'\"]+)", text))
            core = {"start", "help", "lang", "language", "cancel"}
            for feat in list(ir.preferred_keys or []):
                if feat in core:
                    continue
                report["checked"].append(feat)
                stem = str(feat).replace("_", "")
                found = feat in cmds or any(stem in c.replace("_", "") for c in cmds)
                if not found:
                    # soft for telegram features only — do not fail site/API
                    if kind in {"", "telegram_bot"}:
                        report["missing_features"].append(str(feat))
            if kind == "telegram_bot" and report["missing_features"] and not report.get("agent_acceptance", {}).get("ok", True):
                report["ok"] = False
        elif kind == "telegram_bot":
            report["ok"] = False
            report["missing_features"].append("main.py")

    # Kind-specific acceptance hints as checked list
    try:
        from lumen.engine.core.project_kind import acceptance_hints, parse_kind
        pk = parse_kind(kind)
        if pk is not None:
            report["checked"].extend(acceptance_hints(pk)[:12])
    except Exception:
        pass

    if report["missing_features"]:
        # Deduplicate
        report["missing_features"] = list(dict.fromkeys(report["missing_features"]))
        # If agent gate failed, ok already False; for telegram soft feature gaps keep agent decision
        if kind in {"web_site", "web_api", "cli_app", "library"}:
            report["ok"] = False
    return report



__all__ = ["IRValidation", "check_project_against_ir", "validate_and_normalize_ir"]
