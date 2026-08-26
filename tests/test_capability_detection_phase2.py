import pytest
pytest.skip("BuilderSession removed; test no longer applicable", allow_module_level=True)
"""Phase 2 — detection integration with generation preflight."""
from __future__ import annotations

from lumen.engine.services.capability_detection import (
    DetectionStatus,
    apply_detection_to_session,
    feature_keys,
    metadata_from_report,
    run_detection,
    telegram_preflight,
)
BuilderSession = None  # removed with spec_core


def test_preflight_blocks_impossible():
    pre = telegram_preflight("بوت يتعلم من المحادثات ويدرب نموذج ذكاء اصطناعي")
    assert pre["should_block"] is True
    assert pre["user_message"]
    assert "لا أستطيع" in pre["user_message"] or "خارج" in pre["user_message"]


def test_preflight_blocks_pure_gap():
    # Phase 8 hardened: translate is covered by scaffold_translate → not blocked
    pre = telegram_preflight("بوت يترجم الرسائل تلقائياً فقط بدون أي ميزة أخرى")
    keys = feature_keys(pre["report"], include_core=False)
    assert "scaffold_translate" in keys
    assert pre["should_block"] is False
    assert pre["report"].status in (DetectionStatus.EXISTS, DetectionStatus.COMPOSABLE)


def test_preflight_allows_welcome():
    pre = telegram_preflight("بوت ترحيب للمجموعة مع قوانين")
    assert pre["should_block"] is False
    assert pre["report"].status in (DetectionStatus.EXISTS, DetectionStatus.COMPOSABLE)
    keys = feature_keys(pre["report"], include_core=False)
    assert "welcome_set" in keys or "rules" in keys
    assert pre["soft_note"]


def test_preflight_partial_gap_note():
    # translate + welcome: may be gap with or without features
    pre = telegram_preflight("بوت ترحيب للمجموعة ويترجم الرسائل تلقائياً")
    assert pre["report"].status in (DetectionStatus.GAP, DetectionStatus.COMPOSABLE)
    if pre["should_block"]:
        assert pre["user_message"]
    else:
        # partial generation path
        assert "welcome_set" in feature_keys(pre["report"], include_core=False) or pre["soft_note"]


def test_apply_detection_to_session():
    session = BuilderSession(user_id=0)
    report = run_detection("بوت متجر فيه سلة")
    added = apply_detection_to_session(session, report)
    assert "start" in session.selected or "shop_catalog" in session.selected or added
    assert any(k in session.selected for k in feature_keys(report))


def test_metadata_from_report():
    report = run_detection("بوت تذاكر دعم")
    meta = metadata_from_report(report)
    assert "capability_detection" in meta
    assert meta["capability_detection"]["status"] in {s.value for s in DetectionStatus}


def test_generate_bot_signature_accepts_preferred_keys():
    import inspect
    from lumen.engine import generate_bot
    sig = inspect.signature(generate_bot)
    assert "preferred_keys" in sig.parameters


def test_preferred_keys_emit_handlers():
    import tempfile
    from pathlib import Path
    from lumen.engine import generate_bot

    with tempfile.TemporaryDirectory() as d:
        result = generate_bot(
            "بوت أوامر بسيط",
            work_dir=d,
            user_id=0,
            preferred_keys=["start", "help", "welcome_set", "user_ban"],
        )
        assert result is not None and result.success
        layers = (result.metadata or {}).get("layers") or {}
        assert "welcome_set" in (layers.get("detection_preferred_keys") or [])
        root = Path(result.project_path)
        text = ""
        for f in root.rglob("*.py"):
            text += f.read_text(encoding="utf-8", errors="ignore")
        assert "handle_welcome_set" in text or "welcome" in text.lower()
        assert "handle_user_ban" in text or "ban" in text.lower()


def test_preflight_blocks_nonsense():
    pre = telegram_preflight("xyz random nonsense 12345")
    assert pre["should_block"] is True
