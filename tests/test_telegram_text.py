"""Markdown Hell root fix — MDV2 escape, split long text, plain default."""
from __future__ import annotations

import importlib.util
from pathlib import Path


def _load():
    path = Path(__file__).resolve().parents[1] / "lumen" / "bot" / "telegram_text.py"
    spec = importlib.util.spec_from_file_location("tg_text_test", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_escape_markdown_v2_covers_agent_noise():
    tt = _load()
    raw = r"file_name *bold* [link](x) code`x` a.b ! # + - = | { } ~ >"
    esc = tt.escape_markdown_v2(raw)
    # Every special must be escaped
    for ch in r"_*[]()~`>#+-=|{}.!":
        # either not present or preceded by backslash
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
    # No silent truncation of whole body
    joined = "".join(parts)
    assert "فقرة واحدة" in joined
    assert len(joined) >= len(body) * 0.9


def test_helpers_default_is_plain_not_legacy_markdown():
    src = (Path(__file__).resolve().parents[1] / "lumen/bot/helpers.py").read_text()
    assert "telegram_text" in src
    assert "ParseMode.MARKDOWN)" not in src or "ParseMode.MARKDOWN_V2" in open(
        Path(__file__).resolve().parents[1] / "lumen/bot/telegram_text.py"
    ).read()
    # safe_edit default use_markdown=False in telegram_text
    tg = (Path(__file__).resolve().parents[1] / "lumen/bot/telegram_text.py").read_text()
    assert "use_markdown: bool = False" in tg
    assert "ParseMode.MARKDOWN_V2" in tg
    assert "ParseMode.MARKDOWN)" not in tg  # no legacy


def test_agent_reply_uses_safe_reply():
    src = (Path(__file__).resolve().parents[1] / "lumen/bot/routers/message_router.py").read_text()
    assert "safe_reply_text(message, str(turn.reply))" in src
    assert "safe_reply_text(message, reply)" in src
