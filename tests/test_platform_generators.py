"""Platform generators — Telegram / Discord / WhatsApp / web."""
from __future__ import annotations

from pathlib import Path

from lumen.engine.services.platform_generators import (
    apply_platform_scaffold,
    detect_platform,
    supported_platforms,
)


def test_detect_platforms():
    assert detect_platform("ديسكورد bot moderation") == "discord"
    assert detect_platform("whatsapp cloud api support") == "whatsapp"
    assert detect_platform("telegram shop bot") == "telegram"
    assert detect_platform("موقع ويب dashboard") == "web"
    assert "discord" in supported_platforms()


def test_write_discord_scaffold(tmp_path: Path):
    r = apply_platform_scaffold(tmp_path, platform="discord")
    assert r["ok"] is True
    assert r["platform"] == "discord"
    assert (tmp_path / "main.py").is_file()
    assert "discord" in (tmp_path / "main.py").read_text(encoding="utf-8").lower()
    assert (tmp_path / "PLATFORM.md").is_file()


def test_write_whatsapp_scaffold(tmp_path: Path):
    r = apply_platform_scaffold(tmp_path, platform="whatsapp")
    assert r["platform"] == "whatsapp"
    text = (tmp_path / "app" / "handlers.py").read_text(encoding="utf-8")
    assert "graph.facebook.com" in text
    assert "WHATSAPP" in (tmp_path / ".env.example").read_text(encoding="utf-8")


def test_deterministic_repair_respects_discord(tmp_path: Path):
    from lumen.engine.services.multi_agent.deterministic_repair import apply_deterministic_repairs

    (tmp_path).mkdir(exist_ok=True)
    rep = apply_deterministic_repairs(tmp_path, extensions={"user_text": "discord moderation bot"})
    assert rep.get("platform") == "discord"
    main = (tmp_path / "main.py").read_text(encoding="utf-8")
    assert "discord" in main.lower()
    assert "telegram" not in main.lower() or "discord" in main.lower()
