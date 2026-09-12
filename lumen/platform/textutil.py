"""Small text helpers shared across bot UI and presentation."""
from __future__ import annotations


def clip_text(
    text: object,
    limit: int = 40,
    *,
    ellipsis: str = "…",
    strip: bool = True,
    flatten_newlines: bool = False,
) -> str:
    t = str(text if text is not None else "")
    if flatten_newlines:
        t = t.replace(chr(10), " ")
    if strip:
        t = t.strip()
    limit = max(1, int(limit))
    if len(t) <= limit:
        return t
    keep = max(1, limit - len(ellipsis))
    return t[:keep] + ellipsis


_clip = clip_text

__all__ = ["clip_text", "_clip"]
