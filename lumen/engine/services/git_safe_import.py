"""Compatibility loaders for git_operations — standard imports only.

Historically this module used sys.modules hacks to avoid circular imports.
Those are removed: smart_clone/smart_git import cleanly as package modules.
"""
from __future__ import annotations

from types import ModuleType


def load_git_op_module(stem: str) -> ModuleType:
    """Load a git_operations submodule via normal importlib.import_module."""
    stem = (stem or "").strip().replace(".py", "")
    if not stem.isidentifier():
        raise ImportError(f"invalid git op module name: {stem!r}")
    import importlib
    return importlib.import_module(
        f"lumen.engine.engines.generators.git_operations.{stem}"
    )


def get_smart_clone() -> ModuleType:
    return load_git_op_module("smart_clone")


def get_smart_git() -> ModuleType:
    return load_git_op_module("smart_git")
