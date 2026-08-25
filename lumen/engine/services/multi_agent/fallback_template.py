"""Verified Template Fallback — escape stagnant Architect→Builder→Critic loops.

Catalog path only: detect_preset / default_spec_from_request → build_from_spec.
Does NOT mark QA passed; caller must run Critic on a successful build.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def fallback_after_attempts() -> int:
    """Hard default: verified template after the first failed attempt.

    Override with FALLBACK_TEMPLATE_AFTER_ATTEMPTS (1..5). Soft repair must not
    burn tokens once the budget is reached or the loop is stagnant.
    """
    try:
        return max(1, min(int(os.environ.get("FALLBACK_TEMPLATE_AFTER_ATTEMPTS") or "1"), 5))
    except ValueError:
        return 1


def should_trigger_verified_fallback(
    *,
    attempts: int,
    stagnant: bool,
    already_tried: bool,
) -> bool:
    """Trigger once: stagnant OR attempts budget reached; never if already tried.

    Fail-closed against endless Architect→Builder→Critic: a repeated spec hash
    or the attempt budget forces the verified template path immediately.
    """
    if already_tried:
        return False
    if stagnant:
        return True
    return int(attempts or 0) >= fallback_after_attempts()


@dataclass
class FallbackBuild:
    ok: bool
    project_path: str = ""
    preset: str = ""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    generation_result: Any = None
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("generation_result", None)
        d["has_result"] = self.generation_result is not None
        return d


def _user_text_from_state(state: Any) -> str:
    ext = getattr(state, "extensions", None) or {}
    strict = getattr(state, "strict_spec", None) or {}
    for candidate in (
        getattr(state, "user_text", None),
        getattr(state, "spec_request", None),
        ext.get("user_text"),
        strict.get("spec_request") if isinstance(strict, dict) else None,
        strict.get("purpose") if isinstance(strict, dict) else None,
    ):
        t = str(candidate or "").strip()
        if t:
            return t[:20000]
    return ""


def _resolve_output_root(work_dir: str | Path | None) -> Path:
    """Always return a directory under OUTPUT_DIR (safe_fs policy)."""
    from lumen.engine.services.safe_fs import enforce_under_output_dir, output_dir

    out_root = output_dir()
    out_root.mkdir(parents=True, exist_ok=True)

    if work_dir is not None and str(work_dir).strip() and str(work_dir).strip() not in {".", "./"}:
        wd = Path(work_dir)
        try:
            wd.mkdir(parents=True, exist_ok=True)
            return Path(enforce_under_output_dir(wd))
        except Exception:
            # Nest under OUTPUT_DIR instead of failing or writing outside policy
            leaf = wd.name if wd.name and wd.name not in {".", ".."} else "work"
            nested = out_root / "fallback_work" / leaf
            nested.mkdir(parents=True, exist_ok=True)
            return Path(enforce_under_output_dir(nested))

    nested = out_root / "fallback_work"
    nested.mkdir(parents=True, exist_ok=True)
    return Path(enforce_under_output_dir(nested))


def build_verified_bot(
    request: str,
    *,
    work_dir: str | Path,
    user_id: int = 0,
) -> FallbackBuild:
    t0 = time.monotonic()
    req = (request or "").strip()
    if not req:
        return FallbackBuild(ok=False, errors=["empty_request"])

    try:
        work = _resolve_output_root(work_dir)
    except Exception as exc:
        return FallbackBuild(ok=False, errors=[f"output_root:{type(exc).__name__}:{exc}"])

    stamp = time.strftime("%Y%m%d_%H%M%S")
    out = work / f"verified_{int(user_id or 0)}_{stamp}"
    try:
        out.mkdir(parents=True, exist_ok=True)
        from lumen.engine.services.safe_fs import enforce_under_output_dir
        out = Path(enforce_under_output_dir(out))
        out.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        return FallbackBuild(ok=False, errors=[f"outdir:{type(exc).__name__}:{exc}"])

    preset = "echo_basic"
    try:
        from lumen.engine.spec_core.presets import (
            default_spec_from_request,
            detect_preset,
            sanitize_spec_for_request,
        )
        from lumen.engine.spec_core.pipeline import build_from_spec

        detected = detect_preset(req)
        if detected:
            preset = str(detected)
        spec = default_spec_from_request(req, user_id=int(user_id or 0))
        try:
            spec = sanitize_spec_for_request(spec, req)
        except Exception:
            logger.exception("sanitize_spec_for_request failed in verified fallback")

        try:
            if hasattr(spec, "spec_request"):
                existing = (getattr(spec, "spec_request", None) or "").strip()
                if not existing:
                    spec.spec_request = req
                elif req not in existing:
                    spec.spec_request = f"{existing}\n\n# user_request\n{req}"[:20000]
            if hasattr(spec, "meta") and spec.meta is not None:
                desc = (getattr(spec.meta, "description", None) or "").strip()
                if req and req not in desc:
                    spec.meta.description = (f"{desc}\n{req}" if desc else req)[:800]
        except Exception:
            logger.exception("merge user request into verified spec failed")

        build = build_from_spec(spec, out_dir=out, request=req)
    except Exception as exc:
        logger.exception("verified template build failed")
        return FallbackBuild(
            ok=False,
            preset=preset,
            errors=[f"{type(exc).__name__}:{exc}"],
            duration_ms=(time.monotonic() - t0) * 1000,
        )

    ok = bool(getattr(build, "ok", False))
    path = str(getattr(build, "project_path", None) or "")
    errors = [str(e) for e in (getattr(build, "errors", None) or [])]
    warnings = [str(w) for w in (getattr(build, "warnings", None) or [])]
    if ok and (not path or not Path(path).is_dir()):
        ok = False
        errors.append("project_path_missing")

    gen_result = None
    try:
        from lumen.engine.core.result import GenerationResult

        gen_result = GenerationResult(
            success=ok,
            project_path=path if ok else None,
            errors=list(errors),
            metadata={
                "engine": "verified_template_fallback",
                "preset": preset,
                "zero_ai": True,
                "fallback": True,
                "warnings": list(warnings),
            },
        )
    except Exception:
        logger.exception("wrap GenerationResult failed")

    return FallbackBuild(
        ok=ok,
        project_path=path if ok else "",
        preset=preset,
        errors=errors,
        warnings=warnings + ([f"verified_preset:{preset}"] if ok else []),
        generation_result=gen_result,
        duration_ms=(time.monotonic() - t0) * 1000,
    )


def run_verified_fallback_on_state(state: Any, *, work_dir: str | Path) -> Any:
    """Apply verified build onto AgentState.

    On success: sets build_success + path + _generation_result.
    Does NOT set qa_passed — orchestrator must run Critic.
    """
    from .state import AgentRole, AgentStatus

    state.extensions = dict(state.extensions or {})
    state.extensions["fallback_template_tried"] = True
    req = _user_text_from_state(state)
    if not req:
        state.build_success = False
        state.build_errors = ["empty_user_text"]
        state.qa_passed = False
        state.record(AgentRole.ORCHESTRATOR, "verified_fallback_skip", "empty_user_text")
        state.extensions["fallback_template"] = {"ok": False, "errors": ["empty_user_text"]}
        return state

    result = build_verified_bot(
        req,
        work_dir=work_dir,
        user_id=int(getattr(state, "user_id", 0) or 0),
    )
    state.extensions["fallback_template"] = result.to_dict()
    state.record(
        AgentRole.ORCHESTRATOR,
        "verified_fallback",
        f"ok={result.ok} preset={result.preset} errs={result.errors[:3]}",
    )

    if result.ok and result.project_path:
        state.build_success = True
        state.generated_path = result.project_path
        state.build_errors = []
        # Leave qa_passed False until Critic runs
        state.qa_passed = False
        state.qa_report = {
            "ok": False,
            "errors": [],
            "warnings": list(result.warnings),
            "source": "verified_template_pending_critic",
            "attempt": int(getattr(state, "attempts", 0) or 0),
        }
        if result.generation_result is not None:
            state.extensions["_generation_result"] = result.generation_result
        try:
            state.transition(AgentStatus.QA, role=AgentRole.ORCHESTRATOR, force=True)
        except Exception:
            state.status = AgentStatus.QA.value
    else:
        state.build_success = False
        state.build_errors = list(result.errors) or ["verified_fallback_failed"]
        state.qa_passed = False
        state.qa_report = {
            "ok": False,
            "errors": list(result.errors) or ["verified_fallback_failed"],
            "source": "verified_template",
            "attempt": int(getattr(state, "attempts", 0) or 0),
        }
        try:
            state.transition(AgentStatus.FAILED, role=AgentRole.ORCHESTRATOR, force=True)
        except Exception:
            state.status = AgentStatus.FAILED.value
    return state


__all__ = [
    "FallbackBuild",
    "fallback_after_attempts",
    "should_trigger_verified_fallback",
    "build_verified_bot",
    "run_verified_fallback_on_state",
]
