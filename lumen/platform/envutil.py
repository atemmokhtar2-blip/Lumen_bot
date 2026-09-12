"""Single source for environment flags and production detection.

Import from here instead of redefining _flag / is_production / _truthy.
"""
from __future__ import annotations

import os


def environment_name() -> str:
    return (os.environ.get("ENVIRONMENT") or os.environ.get("TBE_ENV") or "").strip().lower()


def env_flag(name: str, default: str = "0") -> bool:
    """Truthy env var: 1/true/yes/on."""
    return (os.environ.get(name) or default).strip().lower() in {"1", "true", "yes", "on"}


# Back-compat aliases used across the codebase
_flag = env_flag
_truthy = lambda name: env_flag(name, "0")  # noqa: E731


def is_dev_environment() -> bool:
    return environment_name() in {"dev", "development", "local", "test"}


def is_production() -> bool:
    """Production/staging lock surface — one definition for the whole product."""
    return environment_name() in {"production", "prod", "staging"}


def is_production_runtime() -> bool:
    return is_production()


__all__ = [
    "environment_name",
    "env_flag",
    "_flag",
    "_truthy",
    "is_dev_environment",
    "is_production",
    "is_production_runtime",
]
