"""Foundation identity — Lumen only; packages live under lumen.*."""
from __future__ import annotations

from pathlib import Path

from lumen.identity import (
    PRODUCT_NAME,
    PRODUCT_ID,
    REPO_NAME,
    WATERMARK_TEXT,
    system_identity_line,
)

ROOT = Path(__file__).resolve().parents[1]


def test_product_name_is_lumen():
    assert PRODUCT_NAME == "Lumen"
    assert PRODUCT_ID == "lumen"
    assert REPO_NAME == "Lumen_bot"
    assert "Lumen" in system_identity_line()
    assert "Lumen" in WATERMARK_TEXT


def test_system_prompts_use_foundation():
    groq = (ROOT / "lumen/engine/services/llm/groq_chat.py").read_text(encoding="utf-8")
    assert "system_identity_line" in groq
    assert "from lumen.identity import" in groq
    gem = (ROOT / "lumen/engine/services/gemini_client.py").read_text(encoding="utf-8")
    assert "system_identity_line" in gem
    assert "from lumen.identity import" in gem


def test_surfaces_read_identity_module():
    """Entry and brand surfaces must import from lumen.identity, not hardcode product identity."""
    checks = [
        (ROOT / "lumen/api/routes/health.py", "from lumen.identity import"),
        (ROOT / "lumen/platform/plans.py", "from lumen.identity import"),
        (ROOT / "lumen/__init__.py", "from lumen.identity import"),
        (ROOT / "README.md", "Lumen"),
        (ROOT / "lumen/identity.py", 'PRODUCT_NAME: str = "Lumen"'),
    ]
    for path, needle in checks:
        assert path.is_file(), f"missing {path}"
        text = path.read_text(encoding="utf-8")
        assert needle in text, f"{path} must contain {needle!r}"


def test_packages_live_under_lumen_namespace():
    assert (ROOT / "lumen" / "engine").is_dir()
    assert (ROOT / "lumen" / "platform").is_dir()
    assert (ROOT / "lumen" / "bot").is_dir()
    assert (ROOT / "lumen" / "api").is_dir()
    assert not (ROOT / "telegram_bot_engine").exists()
    assert not (ROOT / "b2b_platform").exists()
    assert not (ROOT / "bot_interface").exists()
    assert not (ROOT / "api").exists() or (ROOT / "api").is_file()


def test_no_old_import_strings_in_entrypoints():
    for rel in ("main.py", "api_main.py"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "telegram_bot_engine" not in text
        assert "b2b_platform" not in text
        assert "bot_interface" not in text
        assert "from api." not in text
