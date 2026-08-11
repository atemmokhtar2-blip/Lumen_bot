"""Phase 14 scaffolds + Phase 15 end-to-end integration scenarios."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from telegram_bot_engine.services.capability_detection.packs.loader import (
    load_all_packs,
    _LOADED_PACKS,
    _OVERLAY_KEYS,
    _KEYWORD_INDEX,
)
from telegram_bot_engine.services.capability_detection import (
    detect_capabilities,
    feature_keys,
    pipeline_trace,
    capability_system_health,
    smoke_generated_project,
    telegram_preflight,
)
from telegram_bot_engine.services.capability_detection.packs.emit_contract import assess_capability
from telegram_bot_engine.spec_core.registry import get_capability
from telegram_bot_engine import generate_bot


def _reload():
    _LOADED_PACKS.clear()
    _OVERLAY_KEYS.clear()
    _KEYWORD_INDEX.clear()
    load_all_packs()


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("CAPABILITY_RESEARCH_OFFLINE", "1")
    monkeypatch.setenv("CAPABILITY_OPS_REQUIRE_ADMIN", "0")
    _reload()


def test_phase14_caps_registered():
    assert get_capability("scaffold_voice") is not None
    assert get_capability("scaffold_payment_info") is not None
    assert get_capability("scaffold_faq_bot") is not None
    assert assess_capability("x", "utils", "voice_intake").safe is True
    assert assess_capability("x", "utils", "payment_info").safe is True
    assert assess_capability("x", "content", "faq").safe is True


def test_voice_request_matches_scaffold():
    rep = detect_capabilities("بوت يستقبل رسائل صوتية")
    keys = feature_keys(rep, include_core=False)
    assert "scaffold_voice" in keys


def test_payment_info_detection():
    rep = detect_capabilities("بوت فيه فودافون كاش وطرق الدفع")
    keys = feature_keys(rep, include_core=False)
    assert "scaffold_payment_info" in keys or any("payment" in k or "pay" in k for k in keys)


def test_generate_voice_scaffold_runtime():
    with tempfile.TemporaryDirectory() as d:
        r = generate_bot(
            "بوت صوت",
            work_dir=d,
            user_id=0,
            preferred_keys=["start", "help", "scaffold_voice"],
        )
        assert r.success
        gen = (Path(r.project_path) / "app" / "services" / "generic.py").read_text(encoding="utf-8")
        assert "def voice_intake" in gen


def test_generate_payment_info_env():
    with tempfile.TemporaryDirectory() as d:
        r = generate_bot(
            "بوت دفع يدوي",
            work_dir=d,
            user_id=0,
            preferred_keys=["start", "help", "scaffold_payment_info"],
        )
        assert r.success
        env = (Path(r.project_path) / ".env.example").read_text(encoding="utf-8")
        assert "PAYMENT_VODAFONE_CASH" in env or "PAYMENT_" in env


SCENARIOS = [
    ("welcome", "بوت ترحيب للمجموعة مع قوانين", ["welcome_set"]),
    ("translate", "بوت يترجم الرسائل تلقائياً", ["scaffold_translate"]),
    ("ocr", "بوت OCR يقرأ الصور", ["scaffold_ocr"]),
    ("schedule", "بوت تذكير مجدول", ["scaffold_schedule"]),
    ("voice", "بوت رسائل صوتية", ["scaffold_voice"]),
]


@pytest.mark.parametrize("name,request_ar,expect_keys", SCENARIOS)
def test_integration_detect_preflight_trace(name, request_ar, expect_keys):
    rep = detect_capabilities(request_ar)
    feats = feature_keys(rep, include_core=False)
    for k in expect_keys:
        assert k in feats or any(k in f for f in feats), f"{name}: missing {k} in {feats}"
    pre = telegram_preflight(request_ar)
    assert pre["should_block"] is False
    tr = pipeline_trace(request_ar, include_research=False)
    assert tr["ok"] is True
    assert tr["fail_safe"]["level"] in {"ok", "partial", "emit_risk"}


@pytest.mark.parametrize("name,request_ar,expect_keys", SCENARIOS[:3])
def test_integration_generate_and_smoke(name, request_ar, expect_keys):
    keys = ["start", "help"] + list(expect_keys)
    with tempfile.TemporaryDirectory() as d:
        r = generate_bot(request_ar, work_dir=d, user_id=0, preferred_keys=keys)
        assert r.success, (name, r.errors)
        smoke = smoke_generated_project(r.project_path, expected_keys=keys)
        assert smoke["critical_failed"] == 0, smoke.get("errors")
        diag = (r.metadata or {}).get("capability_diagnostics")
        assert diag is not None
        assert diag.get("system_health", {}).get("ok") is True


def test_integration_system_health_full():
    h = capability_system_health()
    assert h["ok"] is True
    assert h["critical_failed"] == 0


def test_integration_impossible_still_blocks():
    pre = telegram_preflight("بوت يتعلم من المحادثات ويدرب نموذج ذكاء اصطناعي")
    assert pre["should_block"] is True


def test_generate_faq_scaffold_emits_faq_fn():
    """FAQ scaffold must emit a real faq() implementation, not generic list-only."""
    with tempfile.TemporaryDirectory() as d:
        r = generate_bot(
            "بوت أسئلة شائعة",
            work_dir=d,
            user_id=0,
            preferred_keys=["start", "help", "scaffold_faq_bot"],
        )
        assert r.success, r.errors
        gen = (Path(r.project_path) / "app" / "services" / "generic.py").read_text(encoding="utf-8")
        assert "def faq(" in gen
        assert "_FAQ_SEED" in gen
        main = (Path(r.project_path) / "main.py").read_text(encoding="utf-8")
        assert "faq" in main.lower()
        handlers = (Path(r.project_path) / "app" / "handlers.py").read_text(encoding="utf-8")
        assert "generic_svc.faq" in handlers or "def faq" in gen


def test_generate_payment_extra_env_keys():
    with tempfile.TemporaryDirectory() as d:
        r = generate_bot(
            "بوت دفع يدوي",
            work_dir=d,
            user_id=0,
            preferred_keys=["start", "help", "scaffold_payment_info"],
        )
        assert r.success
        env = (Path(r.project_path) / ".env.example").read_text(encoding="utf-8")
        assert "PAYMENT_INSTAPAY" in env or "PAYMENT_VODAFONE_CASH" in env


def test_generate_voice_router_and_from_file():
    with tempfile.TemporaryDirectory() as d:
        r = generate_bot(
            "بوت رسائل صوتية",
            work_dir=d,
            user_id=0,
            preferred_keys=["start", "help", "scaffold_voice"],
        )
        assert r.success, r.errors
        gen = (Path(r.project_path) / "app" / "services" / "generic.py").read_text(encoding="utf-8")
        assert "def voice_from_file" in gen
        handlers = (Path(r.project_path) / "app" / "handlers.py").read_text(encoding="utf-8")
        main = (Path(r.project_path) / "main.py").read_text(encoding="utf-8")
        assert "voice_router" in handlers
        assert "filters.VOICE" in main or "VOICE" in main


def test_generate_faq_admin_add():
    with tempfile.TemporaryDirectory() as d:
        r = generate_bot(
            "بوت أسئلة شائعة",
            work_dir=d,
            user_id=0,
            preferred_keys=["start", "help", "scaffold_faq_bot"],
        )
        assert r.success
        gen = (Path(r.project_path) / "app" / "services" / "generic.py").read_text(encoding="utf-8")
        assert "_faq_is_admin" in gen
        assert "faq:" in gen  # title prefix for custom
        assert "add " in gen or "أضف" in gen
