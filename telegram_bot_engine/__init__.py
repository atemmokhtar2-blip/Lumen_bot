"""
Telegram Bot Generation Engine
==============================

A modular engine that generates complete Telegram bot projects from a
natural-language description.  The engine is not a bot itself — it is a
factory that builds bots.

Quick start
-----------
::

    from telegram_bot_engine import generate_bot

    result = generate_bot("اعمل بوت متجر إلكتروني")
    print(result.project_path)
"""

from __future__ import annotations

__all__ = [
    "bootstrap",
    "build_configuration",
    "generate_bot",
    "PipelineOrchestrator",
    "EngineRegistry",
]


def __getattr__(name: str):
    """Lazy imports so that ``import telegram_bot_engine`` stays fast."""
    if name in ("bootstrap", "build_configuration"):
        from .core import bootstrap, build_configuration
        return {"bootstrap": bootstrap, "build_configuration": build_configuration}[name]
    if name == "PipelineOrchestrator":
        from .pipeline import PipelineOrchestrator
        return PipelineOrchestrator
    if name == "EngineRegistry":
        from .registry import EngineRegistry
        return EngineRegistry
    if name == "generate_bot":
        return generate_bot
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def generate_bot(request: str, work_dir=None):
    """Generate a complete Telegram bot project from a description.

    This is the main entry point.  It bootstraps the engine, runs the
    full pipeline, and returns a GenerationResult.
    """
    from .core import bootstrap
    _registry, orchestrator, _manager = bootstrap()
    return orchestrator.run(request, work_dir=work_dir)
