"""
Telegram Bot Generation Engine

Active path (Cline SDK only):
  user text
    → BuildIR
    → engine_router.execute_ir
    → Cline runtime
    → project files on disk (inside per-user sandbox)

The deterministic / zero-AI / catalog / hybrid / PipelineOrchestrator path
has been permanently removed from the repository.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .core import bootstrap as bootstrap, build_configuration as build_configuration


__all__ = [
    "generate_bot",
]


def generate_bot(request: str, work_dir=None, user_id: int = 0, preferred_keys=None):
    """Legacy name — redirects to Cline-only execute_ir."""
    import logging
    from pathlib import Path as _Path

    _log = logging.getLogger(__name__)
    _log.warning("generate_bot called — redirecting to Cline-only execute_ir")
    try:
        from lumen.engine.services.engine_router import build_ir_from_package, execute_ir

        package = {
            "original_text": request or "",
            "spec_request": request or "",
            "preferred_keys": list(preferred_keys or []),
            "engine_mode": "cline",
            "confidence": 0.5,
        }
        ir = build_ir_from_package(package, user_id=int(user_id or 0))
        wd = work_dir if work_dir is not None else _Path("/tmp/lumen_output/cline_redirect")
        return execute_ir(ir, wd, user_id=int(user_id or 0))
    except Exception as exc:
        _log.exception("cline redirect failed")
        from .core.result import GenerationResult

        return GenerationResult(
            success=False,
            errors=[f"cline_redirect_failed:{type(exc).__name__}"],
            metadata={"engine": "cline"},
        )
