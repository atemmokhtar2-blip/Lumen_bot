"""Lightweight non-bot request detector (feasibility_gate removed)."""
from __future__ import annotations

import re

_NON_BOT = re.compile(
    r"(?i)("
    r"recipe|وصفة|طبخ|weather\s*forecast|نشرة\s*جوية|"
    r"homework|واجب\s*مدرسي|translate\s*this\s*paragraph|"
    r"write\s*me\s*an\s*essay|اكتب\s*مقال"
    r")"
)


def is_clearly_non_bot(text: str) -> bool:
    t = (text or "").strip()
    if len(t) < 8:
        return False
    # Explicit bot/build signals → not non-bot
    if re.search(r"(?i)bot|telegram|بوت|تيليجرام|discord|whatsapp", t):
        return False
    return bool(_NON_BOT.search(t))
