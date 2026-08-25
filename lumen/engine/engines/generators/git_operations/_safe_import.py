"""Load git_operations modules without package circular imports or dataclass crashes.

Root bug: importlib.util.module_from_spec + exec_module WITHOUT registering the
module in sys.modules first makes @dataclass fail with:
  AttributeError: 'NoneType' object has no attribute '__dict__'
because dataclasses looks up sys.modules[cls.__module__].__dict__.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Optional

_DIR = Path(__file__).resolve().parent
_CACHE: dict[str, ModuleType] = {}


def load_git_op_module(stem: str) -> ModuleType:
    """Load smart_clone / smart_git / etc. by file stem, once, safely."""
    stem = (stem or "").strip().replace(".py", "")
    if stem in _CACHE:
        return _CACHE[stem]
    # Prefer already-imported real package module when available
    pkg_name = f"lumen.engine.engines.generators.git_operations.{stem}"
    existing = sys.modules.get(pkg_name)
    if existing is not None and hasattr(existing, "__dict__"):
        _CACHE[stem] = existing
        return existing

    path = _DIR / f"{stem}.py"
    if not path.is_file():
        raise ImportError(f"git_operations module not found: {path}")

    # Use stable package-style name so relative imports inside file still work when possible
    mod_name = f"lumen.engine.engines.generators.git_operations.{stem}"
    # If a broken partial module is present, drop it
    prev = sys.modules.get(mod_name)
    if prev is not None and not hasattr(prev, "__dict__"):
        sys.modules.pop(mod_name, None)

    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load spec for {path}")
    mod = importlib.util.module_from_spec(spec)
    # CRITICAL: register before exec_module so @dataclass can resolve __dict__
    sys.modules[mod_name] = mod
    # Also register short alias used historically by tool_runtime
    sys.modules.setdefault(f"cm_{stem}", mod)
    try:
        spec.loader.exec_module(mod)
    except Exception:
        # don't leave a broken module cached
        sys.modules.pop(mod_name, None)
        sys.modules.pop(f"cm_{stem}", None)
        raise
    _CACHE[stem] = mod
    return mod


def get_smart_clone():
    return load_git_op_module("smart_clone")


def get_smart_git():
    return load_git_op_module("smart_git")
