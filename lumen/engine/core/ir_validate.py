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
        from lumen.engine.spec_core.registry import CAPABILITIES

        return set(CAPABILITIES.keys())
    except Exception:
        return set()


def validate_and_normalize_ir(ir: BuildIR) -> IRValidation:
    """Reject empty/unsafe IR; drop unknown keys; attach lean pack hints."""
    errors: list[str] = []
    warnings: list[str] = []
    caps = _catalog_keys()
    core = {"start", "help", "lang", "language", "cancel"}

    text = (ir.original_text or ir.spec_request or "").strip()
    if len(text) < 3:
        errors.append("ir_text_too_short")

    preferred = [k for k in ir.preferred_keys if not caps or k in caps]
    matched = [k for k in ir.capabilities_matched if not caps or k in caps]
    unknown = [k for k in ir.preferred_keys if caps and k not in caps]
    if unknown:
        warnings.append("dropped_unknown_keys:" + ",".join(unknown[:8]))

    for c in ("start", "help"):
        if caps and c in caps and c not in preferred:
            preferred.append(c)

    try:
        from lumen.engine.spec_core.domain_detector import decide
        from lumen.engine.spec_core.lean_packs import pack_for_domain

        dec = decide(text)
        pack = pack_for_domain(getattr(dec, "primary", None))
        conf = float(getattr(dec, "confidence", 0.0) or 0.0)
        if pack and conf >= 0.30:
            for k in pack:
                if (not caps or k in caps) and k not in preferred:
                    preferred.append(k)
                if (not caps or k in caps) and k not in matched and k not in core:
                    matched.append(k)
            ir.metadata = dict(ir.metadata or {})
            ir.metadata["domain_primary"] = getattr(dec, "primary", None)
            ir.metadata["domain_confidence"] = conf
            ir.metadata["lean_pack_applied"] = list(pack)
    except Exception as exc:
        warnings.append(f"domain_enrich_failed:{type(exc).__name__}")

    ir.preferred_keys = preferred[:20]
    ir.capabilities_matched = matched[:20]
    ir.spec_request = (ir.spec_request or ir.original_text or "").strip()
    if not ir.spec_request:
        ir.spec_request = text or "Telegram bot with start and help"

    acc: list[AcceptanceCriterion] = []
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
    """Post-generation: preferred features should appear as registered commands."""
    from pathlib import Path
    import re

    root = Path(project_path)
    main = root / "main.py"
    report: dict[str, Any] = {
        "ok": True,
        "missing_features": [],
        "checked": [],
        "path": str(root),
    }
    if not main.exists():
        report["ok"] = False
        report["missing_features"] = ["main.py"]
        return report

    text = main.read_text(encoding="utf-8", errors="ignore")
    cmds = set(re.findall(r"CommandHandler\(\s*['\"]([^'\"]+)", text))
    core = {"start", "help", "lang", "language", "cancel"}
    try:
        from lumen.engine.spec_core.command_map import primary_commands

        prim = primary_commands()
    except Exception:
        prim = {}

    for feat in ir.preferred_keys:
        if feat in core:
            continue
        report["checked"].append(feat)
        candidates = {feat, feat.replace("_", ""), prim.get(feat, "")}
        candidates = {c for c in candidates if c}
        stem = feat.replace("_", "")
        found = any(c in cmds for c in candidates) or any(
            stem in c.replace("_", "") for c in cmds
        )
        if not found:
            report["missing_features"].append(feat)

    if report["missing_features"]:
        report["ok"] = False
    return report


__all__ = ["IRValidation", "check_project_against_ir", "validate_and_normalize_ir"]
