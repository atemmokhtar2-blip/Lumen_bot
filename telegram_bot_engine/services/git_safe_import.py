"""Safe loader for git_operations modules — avoids engines package circular import.

Critical: register module in sys.modules BEFORE exec_module, otherwise
@dataclass fails with: AttributeError: 'NoneType' object has no attribute '__dict__'
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

_CACHE: dict[str, ModuleType] = {}
_GIT_OPS = (
    Path(__file__).resolve().parents[1]
    / "engines"
    / "generators"
    / "git_operations"
)


def _ensure_namespace_packages() -> None:
    """Create empty parent package entries so relative imports can resolve."""
    # We intentionally do NOT import telegram_bot_engine.engines (circular).
    # Only ensure namespace modules exist for relative imports inside smart_clone.
    parts = [
        "telegram_bot_engine",
        "telegram_bot_engine.engines",
        "telegram_bot_engine.engines.generators",
        "telegram_bot_engine.engines.generators.git_operations",
    ]
    # telegram_bot_engine is normally already imported
    for name in parts:
        if name in sys.modules:
            continue
        # If real package can be imported without side effects for top-level only
        if name == "telegram_bot_engine":
            continue
        # Create a lightweight namespace package pointing at the directory
        m = ModuleType(name)
        # map path
        rel = name.replace("telegram_bot_engine.", "").replace(".", "/")
        if name == "telegram_bot_engine.engines":
            pkg_path = Path(__file__).resolve().parents[1] / "engines"
        elif name == "telegram_bot_engine.engines.generators":
            pkg_path = Path(__file__).resolve().parents[1] / "engines" / "generators"
        else:
            pkg_path = _GIT_OPS
        m.__path__ = [str(pkg_path)]  # type: ignore[attr-defined]
        m.__package__ = name
        sys.modules[name] = m


def load_git_op_module(stem: str) -> ModuleType:
    stem = (stem or "").strip().replace(".py", "")
    if stem in _CACHE:
        return _CACHE[stem]

    path = _GIT_OPS / f"{stem}.py"
    if not path.is_file():
        raise ImportError(f"git op module missing: {path}")

    mod_name = f"telegram_bot_engine.engines.generators.git_operations.{stem}"
    existing = sys.modules.get(mod_name)
    if existing is not None and getattr(existing, "__dict__", None) is not None:
        if hasattr(existing, "smart_clone") or hasattr(existing, "git_pull") or stem not in ("smart_clone", "smart_git"):
            # only trust if it looks initialized
            if stem == "smart_clone" and hasattr(existing, "smart_clone"):
                _CACHE[stem] = existing
                return existing
            if stem == "smart_git" and hasattr(existing, "git_pull"):
                _CACHE[stem] = existing
                return existing
            if stem not in ("smart_clone", "smart_git"):
                _CACHE[stem] = existing
                return existing

    _ensure_namespace_packages()

    spec = importlib.util.spec_from_file_location(
        mod_name,
        path,
        submodule_search_locations=[str(_GIT_OPS)],
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = "telegram_bot_engine.engines.generators.git_operations"
    # CRITICAL order
    sys.modules[mod_name] = mod
    sys.modules[f"cm_{stem}"] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules.pop(mod_name, None)
        sys.modules.pop(f"cm_{stem}", None)
        raise
    _CACHE[stem] = mod
    return mod


def get_smart_clone() -> ModuleType:
    return load_git_op_module("smart_clone")


def get_smart_git() -> ModuleType:
    return load_git_op_module("smart_git")
