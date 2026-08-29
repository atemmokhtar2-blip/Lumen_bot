"""Bidirectional text helpers for Arabic UI mixed with LTR paths.

Uses Unicode isolates (preferred over older RLE/LRE) so paths and URLs
do not scramble surrounding Arabic in Telegram clients.
Reference: Unicode UAX #9 — RLI/LRI/PDI isolates.
"""
from __future__ import annotations

# Unicode bidi isolates (Unicode 6.3+)
_LRI = "\u2066"  # LEFT-TO-RIGHT ISOLATE
_RLI = "\u2067"  # RIGHT-TO-LEFT ISOLATE
_PDI = "\u2069"  # POP DIRECTIONAL ISOLATE
_LRM = "\u200E"  # LEFT-TO-RIGHT MARK
_RLM = "\u200F"  # RIGHT-TO-LEFT MARK


def isolate_ltr(text: str) -> str:
    """Force LTR rendering for a path/URL inside RTL paragraph."""
    s = (text or "").strip()
    if not s:
        return s
    return f"{_LRI}{s}{_PDI}"


def isolate_rtl(text: str) -> str:
    s = (text or "").strip()
    if not s:
        return s
    return f"{_RLI}{s}{_PDI}"


def code_path(path: str) -> str:
    """Telegram Markdown-safe path: backticks + LTR isolate.

    Always prefer this over bare path insertion in Arabic messages.
    """
    s = (path or "").strip().replace("`", "'")
    if not s:
        return "`—`"
    # Cap length so messages stay readable on mobile
    if len(s) > 120:
        s = "…" + s[-117:]
    return f"`{isolate_ltr(s)}`"


def code_url(url: str) -> str:
    s = (url or "").strip().replace("`", "'")
    if not s:
        return "`—`"
    if len(s) > 140:
        s = s[:137] + "…"
    return f"`{isolate_ltr(s)}`"
