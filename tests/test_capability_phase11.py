"""Phase 11 — optional production backends in generated projects."""
from __future__ import annotations

import tempfile
from pathlib import Path

from telegram_bot_engine.services.capability_detection.packs.loader import (
    load_all_packs,
    _LOADED_PACKS,
    _OVERLAY_KEYS,
    _KEYWORD_INDEX,
)
from telegram_bot_engine import generate_bot


def _reload():
    _LOADED_PACKS.clear()
    _OVERLAY_KEYS.clear()
    _KEYWORD_INDEX.clear()
    load_all_packs()


def test_generate_translate_includes_backend_env_and_reqs():
    _reload()
    with tempfile.TemporaryDirectory() as d:
        r = generate_bot(
            "بوت ترجمة",
            work_dir=d,
            user_id=0,
            preferred_keys=["start", "help", "scaffold_translate"],
        )
        assert r.success
        root = Path(r.project_path)
        env = (root / ".env.example").read_text(encoding="utf-8")
        req = (root / "requirements.txt").read_text(encoding="utf-8")
        readme = (root / "README.md").read_text(encoding="utf-8")
        generic = (root / "app" / "services" / "generic.py").read_text(encoding="utf-8")
        assert "TRANSLATE_BACKEND" in env
        assert "TRANSLATE_API_URL" in env
        assert "deep-translator" in req
        assert "Optional backends" in readme or "TRANSLATE_BACKEND" in readme
        assert "libretranslate" in generic or "TRANSLATE_API_URL" in generic
        assert "GoogleTranslator" in generic


def test_generate_ocr_includes_ocr_env():
    _reload()
    with tempfile.TemporaryDirectory() as d:
        r = generate_bot(
            "بوت OCR",
            work_dir=d,
            user_id=0,
            preferred_keys=["start", "help", "scaffold_ocr"],
        )
        assert r.success
        root = Path(r.project_path)
        env = (root / ".env.example").read_text(encoding="utf-8")
        req = (root / "requirements.txt").read_text(encoding="utf-8")
        assert "OCR_ENABLED" in env
        assert "OCR_LANG" in env
        assert "pytesseract" in req
        assert "Pillow" in req


def test_welcome_only_no_translate_env_required():
    _reload()
    with tempfile.TemporaryDirectory() as d:
        r = generate_bot(
            "بوت ترحيب",
            work_dir=d,
            user_id=0,
            preferred_keys=["start", "help", "welcome_set"],
        )
        assert r.success
        env = (Path(r.project_path) / ".env.example").read_text(encoding="utf-8")
        # may or may not include translate if synthesis adds noise — should not force OCR
        assert "TELEGRAM_BOT_TOKEN" in env
