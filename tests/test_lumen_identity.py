"""Foundation identity — Lumen only; packages live under lumen.*."""
from __future__ import annotations

from pathlib import Path

from lumen.identity import (
    FORBIDDEN_BRAND_TOKENS,
    PRODUCT_NAME,
    contains_forbidden_brand,
    system_identity_line,
)

ROOT = Path(__file__).resolve().parents[1]

CRITICAL = [
    ROOT / "README.md",
    ROOT / "lumen/api/openapi.yaml",
    ROOT / "lumen/api/routes/health.py",
    ROOT / "lumen/platform/plans.py",
    ROOT / "lumen/engine/services/llm/groq_chat.py",
    ROOT / "lumen/engine/services/gemini_client.py",
    ROOT / "lumen/identity.py",
    ROOT / "lumen/__init__.py",
]


def test_product_name_is_lumen():
    assert PRODUCT_NAME == "Lumen"
    assert "Lumen" in system_identity_line()


def test_forbidden_detector():
    assert contains_forbidden_brand("Powered by Maestro")
    assert contains_forbidden_brand("ميسترو")
    assert not contains_forbidden_brand("Powered by Lumen")


def test_critical_files_have_no_forbidden_brands():
    for path in CRITICAL:
        assert path.is_file(), f"missing {path}"
        if path.name == "identity.py":
            continue
        low = path.read_text(encoding="utf-8").lower()
        for tok in FORBIDDEN_BRAND_TOKENS:
            assert tok.lower() not in low, f"{path} contains forbidden brand {tok!r}"


def test_system_prompts_use_foundation():
    groq = (ROOT / "lumen/engine/services/llm/groq_chat.py").read_text(encoding="utf-8")
    assert "system_identity_line" in groq
    gem = (ROOT / "lumen/engine/services/gemini_client.py").read_text(encoding="utf-8")
    assert "system_identity_line" in gem


def test_packages_live_under_lumen_namespace():
    assert (ROOT / "lumen" / "engine").is_dir()
    assert (ROOT / "lumen" / "platform").is_dir()
    assert (ROOT / "lumen" / "bot").is_dir()
    assert (ROOT / "lumen" / "api").is_dir()
    # Old top-level package dirs must not exist
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
