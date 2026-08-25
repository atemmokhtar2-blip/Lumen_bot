"""Phase 11 hardened — optional reqs file, API key, backend status, config snapshot."""
from __future__ import annotations

import tempfile
from pathlib import Path

from lumen.engine.services.capability_detection.packs.loader import (
    load_all_packs,
    _LOADED_PACKS,
    _OVERLAY_KEYS,
    _KEYWORD_INDEX,
)
from lumen.engine import generate_bot


def _reload():
    _LOADED_PACKS.clear()
    _OVERLAY_KEYS.clear()
    _KEYWORD_INDEX.clear()
    load_all_packs()


def test_generate_translate_optional_stack():
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
        opt = root / "requirements-optional.txt"
        assert opt.is_file()
        opt_txt = opt.read_text(encoding="utf-8")
        assert "deep-translator" in opt_txt
        assert "TRANSLATE_BACKEND" in env
        assert "TRANSLATE_API_KEY" in env
        assert "requirements-optional" in req
        generic = (root / "app" / "services" / "generic.py").read_text(encoding="utf-8")
        assert "def backend_status" in generic
        assert "TRANSLATE_API_KEY" in generic
        assert "api-key" in generic
        cfg = (root / "app" / "config.py").read_text(encoding="utf-8")
        assert "backend_env_snapshot" in cfg
        readme = (root / "README.md").read_text(encoding="utf-8")
        assert "translate status" in readme.lower() or "TRANSLATE_BACKEND" in readme


def test_generate_ocr_optional_stack():
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
        opt = (root / "requirements-optional.txt").read_text(encoding="utf-8")
        assert "pytesseract" in opt
        assert "Pillow" in opt
        env = (root / ".env.example").read_text(encoding="utf-8")
        assert "OCR_ENABLED" in env
        assert "OCR_LANG" in env


def test_bootstrap_install_optional_hook():
    _reload()
    with tempfile.TemporaryDirectory() as d:
        r = generate_bot(
            "بوت ترجمة",
            work_dir=d,
            user_id=0,
            preferred_keys=["start", "help", "scaffold_translate"],
        )
        assert r.success
        boot = (Path(r.project_path) / "bootstrap.sh").read_text(encoding="utf-8")
        assert "INSTALL_OPTIONAL" in boot
        assert "requirements-optional.txt" in boot
