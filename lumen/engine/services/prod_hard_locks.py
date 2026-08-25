"""Production hard locks for supply-chain and token exposure.

Imported by pip heal paths and docker driver — cannot be overridden by
accidental TBE_AUTO_HEAL_PIP=1 or TBE_TOKEN_IN_ENV_FILE=1 in production.
"""
from __future__ import annotations

import os


def is_production() -> bool:
    env = (os.getenv("ENVIRONMENT") or os.getenv("TBE_ENV") or "").strip().lower()
    return env in {"production", "prod", "staging"}


def auto_heal_pip_allowed() -> bool:
    """Never allow auto-heal package install in production."""
    if is_production():
        return False
    return (os.getenv("TBE_AUTO_HEAL_PIP") or "0").strip().lower() in {
        "1", "true", "yes", "on",
    }


def token_in_env_file_allowed() -> bool:
    """Never put bot token in docker env-file in production."""
    if is_production():
        return False
    return (os.getenv("TBE_TOKEN_IN_ENV_FILE") or "0").strip().lower() in {
        "1", "true", "yes", "on",
    }
