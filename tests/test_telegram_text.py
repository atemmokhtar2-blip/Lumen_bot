"""Markdown Hell — full wiring: no legacy MARKDOWN, split, safe outbound."""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    path = ROOT / "lumen" / "bot" / "telegram_text.py"
    spec = importlib.util.spec_from_file_location("tg_text_test", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_escape_markdown_v2_covers_agent_noise():
    tt = _load()
    raw = r"file_name *bold* [link](x) code`x` a.b ! # + - = | { } ~ >"
    esc = tt.escape_markdown_v2(raw)
    for ch in r"_*[]()~`>#+-=|{}.!":
        idx = 0
        while True:
            i = esc.find(ch, idx)
            if i < 0:
                break
            assert i > 0 and esc[i - 1] == "\\", f"unescaped {ch!r} in {esc!r}"
            idx = i + 1


def test_split_long_message_preserves_content():
    tt = _load()
    body = ("فقرة واحدة عن البوت.\n\n" * 200) + ("سطر إضافي " * 100)
    assert len(body) > 4096
    parts = tt.split_telegram_text(body)
    assert len(parts) >= 2
    assert all(len(p) <= 4096 for p in parts)
    joined = "".join(parts)
    assert "فقرة واحدة" in joined


def test_no_legacy_markdown_parse_mode_in_bot():
    """Root invariant: ParseMode.MARKDOWN must not be used for outbound text."""
    bad = []
    for path in (ROOT / "lumen" / "bot").rglob("*.py"):
        if path.name == "telegram_text.py":
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for i, line in enumerate(text.splitlines(), 1):
            if "ParseMode.MARKDOWN" in line and "MARKDOWN_V2" not in line:
                if "SimpleNamespace" in line or "never used" in line:
                    continue
                bad.append(f"{path.relative_to(ROOT)}:{i}:{line.strip()}")
    assert not bad, "legacy MARKDOWN still present:\n" + "\n".join(bad)


def test_agent_and_delivery_use_safe_reply():
    mr = (ROOT / "lumen/bot/routers/message_router.py").read_text()
    assert "safe_reply_text(message, str(turn.reply))" in mr
    assert "safe_reply_text(message, reply)" in mr
    delivery = (ROOT / "lumen/bot/generation_steps/delivery.py").read_text()
    assert "safe_reply_text" in delivery
    assert "await message.reply_text(" not in delivery


def test_chat_hygiene_splits_not_only_truncates():
    src = (ROOT / "lumen/bot/ui/chat_hygiene.py").read_text()
    assert "split_telegram_text" in src
    assert "overflow follow-up" in src or "parts[1:]" in src
