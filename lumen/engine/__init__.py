"""
Telegram Bot Generation Engine

Active path (Cline SDK only):
  user text
    → BuildIR
    → engine_router.execute_ir
    → Cline runtime
    → project files on disk (inside per-user sandbox)

Deterministic / zero-AI / catalog / hybrid generation paths have been
permanently removed. Do not reintroduce them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # explicit for mypy/pylint/IDEs — no runtime cycle
    from .pipeline import PipelineOrchestrator as PipelineOrchestrator
    from .registry import EngineRegistry as EngineRegistry
    from .core import bootstrap as bootstrap, build_configuration as build_configuration


__all__ = [
    "bootstrap",
    "build_configuration",
    "generate_bot",
    "PipelineOrchestrator",
    "EngineRegistry",
]


def generate_bot(request: str, work_dir=None, user_id: int = 0, preferred_keys=None):
    """Legacy entry — redirects to Cline SDK.

    Do not use for new call sites; prefer engine_router.execute_ir / cline_runtime.
    """
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


def bootstrap(*args, **kwargs):
    from .core import bootstrap as _bootstrap
    return _bootstrap(*args, **kwargs)


def build_configuration(*args, **kwargs):
    from .core import build_configuration as _bc
    return _bc(*args, **kwargs)


def PipelineOrchestrator(*args, **kwargs):
    from .pipeline import PipelineOrchestrator as _PO
    return _PO(*args, **kwargs)


def EngineRegistry(*args, **kwargs):
    from .registry import EngineRegistry as _ER
    return _ER(*args, **kwargs)
