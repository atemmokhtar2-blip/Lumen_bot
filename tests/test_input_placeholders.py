"""Placeholders & Hints — ForceReply + input_field_placeholder."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    path = ROOT / "lumen/bot/ui/input_prompt.py"
    spec = importlib.util.spec_from_file_location("input_prompt_test", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_placeholders_within_telegram_limit():
    mod = _load()
    for kind, (body, ph) in mod._PROMPTS.items():
        assert len(ph) <= 64, f"{kind} placeholder too long: {len(ph)}"
        assert body.strip()


def test_prompt_spec_known_kinds():
    mod = _load()
    body, ph = mod.prompt_spec("bot_description")
    assert "وصف" in body or "اكتب" in body
    assert "متجر" in ph or "مثال" in ph
    body2, ph2 = mod.prompt_spec("bot_token")
    assert "توكن" in body2 or "BotFather" in body2
    assert len(ph2) <= 64


def test_callback_router_asks_force_reply_on_gen_type():
    src = (ROOT / "lumen/bot/ui/callback_router.py").read_text()
    assert "ask_after_ui" in src
    assert "bot_description" in src


def test_secret_prompt_uses_force_reply():
    src = (ROOT / "lumen/bot/ui/secret_prompt.py").read_text()
    assert "ask_text_input" in src


def test_render_gen_type_has_example():
    src = (ROOT / "lumen/engine/services/ui_state/render.py").read_text()
    assert "مثال" in src
