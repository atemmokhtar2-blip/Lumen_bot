"""Canonical bot-token / GitHub-PAT shape checks (no Telegram I/O).

All product layers must use these helpers so classification never drifts.
"""
from __future__ import annotations

import re

_BOT_RE = re.compile(r"^\d{6,12}:[A-Za-z0-9_-]{30,}$")
_PAT_PREFIXES = ("ghp_", "github_pat_", "glpat_", "gho_", "ghu_")


def normalize_bot_token(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").strip())


def looks_like_bot_token(text: str) -> bool:
    return bool(_BOT_RE.match(normalize_bot_token(text)))


def looks_like_github_pat(text: str) -> bool:
    v = (text or "").strip()
    return any(v.startswith(p) for p in _PAT_PREFIXES)


__all__ = [
    "normalize_bot_token",
    "looks_like_bot_token",
    "looks_like_github_pat",
]
