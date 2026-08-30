"""Loaders for git_operations modules."""
from __future__ import annotations

from types import ModuleType


def load_git_op_module(stem: str) -> ModuleType:
    stem = (stem or "").strip().replace(".py", "")
    if not stem.isidentifier():
        raise ImportError(f"invalid git op module name: {stem!r}")
    import importlib
    return importlib.import_module(f"lumen.engine.services.git_operations.{stem}")


def get_smart_clone() -> ModuleType:
    return load_git_op_module("smart_clone")


def get_smart_git() -> ModuleType:
    return load_git_op_module("smart_git")
