"""Phase 0–1 hardened + Phase 2 UI wiring tests."""
from __future__ import annotations

import threading
import time

import pytest

from lumen.templates.catalog import JsonTemplateCatalog, get_template, list_templates
from lumen.templates.models import (
    TemplateInstance,
    TemplateInstanceStatus,
    TemplateLaunchMode,
    TemplateSpec,
    validate_template_id,
)
from lumen.templates.policy import (
    FREE_MAX_RUNNING,
    TRIAL_MAX_MINUTES,
    clamp_trial_minutes,
    count_active,
    evaluate_launch,
)
from lumen.templates.service import TemplateService
from lumen.templates.store_memory import MemoryTemplateStore


def test_template_id_validation():
    assert validate_template_id("group_moderator") == "group_moderator"
    with pytest.raises(ValueError):
        validate_template_id("Bad-Id")
    with pytest.raises(ValueError):
        validate_template_id("")


def test_catalog_real_json():
    cat = JsonTemplateCatalog()
    enabled = list(cat.list_enabled())
    assert len(enabled) >= 3
    assert all(isinstance(s, TemplateSpec) and s.description for s in enabled)
    assert get_template("shop_assistant") is not None
    assert get_template("missing") is None


def test_policy_caps_precise():
    now = 1_700_000_000.0
    assert clamp_trial_minutes(50) == 50
    assert clamp_trial_minutes(51) == TRIAL_MAX_MINUTES
    d = evaluate_launch(mode="trial", instances=[], now=now, trial_minutes=30)
    assert d.allowed and d.plan and d.plan.expires_at == now + 1800
    full = [
        TemplateInstance(
            instance_id=f"tpl_{i:016x}",
            user_id=1,
            template_id="group_moderator",
            mode=TemplateLaunchMode.TRIAL,
            status=TemplateInstanceStatus.RUNNING,
            started_at=now,
            expires_at=now + 9999,
        )
        for i in range(FREE_MAX_RUNNING)
    ]
    assert count_active(full, now) == 3
    assert evaluate_launch(mode="trial", instances=full, now=now, trial_minutes=10).allowed is False


def test_atomic_reserve_concurrent_respects_cap():
    store = MemoryTemplateStore()
    svc = TemplateService(store=store)
    uid = 700001
    now = time.time()
    results = []
    lock = threading.Lock()

    def worker(i: int) -> None:
        r = svc.reserve(
            uid,
            template_id="faq_helper",
            mode="trial",
            trial_minutes=10,
            now=now,
        )
        with lock:
            results.append(r.ok)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert sum(1 for ok in results if ok) == FREE_MAX_RUNNING
    assert sum(1 for ok in results if not ok) == 8 - FREE_MAX_RUNNING
    assert len(store.list_for_user(uid)) == FREE_MAX_RUNNING


def test_service_expire_and_rereserve():
    store = MemoryTemplateStore()
    svc = TemplateService(store=store)
    uid = 700002
    now = time.time()
    for _ in range(3):
        assert svc.reserve(uid, template_id="shop_assistant", mode="trial", trial_minutes=5, now=now).ok
    past = now + 10_000
    insts = store.list_for_user(uid)
    for i in insts:
        i.status = TemplateInstanceStatus.EXPIRED
    store.save_for_user(uid, insts)
    r = svc.reserve(uid, template_id="group_moderator", mode="permanent", now=past)
    assert r.ok and r.instance and r.instance.mode is TemplateLaunchMode.PERMANENT


def test_architecture_templates_isolation():
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "lumen" / "templates"
    offenders = []
    for p in root.rglob("*.py"):
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith(("lumen.bot", "lumen.hosting", "lumen.engine.services.hosting")):
                    offenders.append(f"{p.name}:{node.module}")
    assert not offenders


def test_phase2_ui_open_templates_and_reserve_effect():
    from lumen.engine.services.ui_state.controller import apply_action, _home_buttons
    from lumen.engine.services.ui_state.models import EngineUiPhase, EngineUiState
    from lumen.engine.services.ui_state.catalog import is_known_action

    assert is_known_action("open_templates")
    assert is_known_action("tpl_minutes")
    labels = [b.text for row in _home_buttons() for b in row]
    assert "القوالب" in labels

    st = EngineUiState(phase=EngineUiPhase.HOME)
    r = apply_action(st, "open_templates")
    assert r.ok and r.state.phase == EngineUiPhase.TEMPLATES

    r2 = apply_action(r.state, "tpl_select", "group_moderator")
    assert r2.ok and r2.state.phase == EngineUiPhase.TEMPLATE_DETAIL
    assert r2.state.slots.get("template_id") == "group_moderator"

    r3 = apply_action(r2.state, "tpl_trial", "group_moderator")
    assert r3.state.phase == EngineUiPhase.TEMPLATE_TRIAL_MINUTES

    r4 = apply_action(r3.state, "tpl_minutes", "group_moderator:30")
    assert r4.ok
    assert r4.post_side_effect == "tpl_reserve_trial"
    assert r4.state.slots.get("trial_minutes") == "30"

    r5 = apply_action(r2.state, "tpl_permanent", "group_moderator")
    assert r5.post_side_effect == "tpl_reserve_permanent"


def test_phase2_reserve_side_effect_real_service():
    import asyncio
    from lumen.bot.ui.callbacks.templates_actions import execute_template_reserve

    ud = {
        "engine_ui": {
            "phase": "template_detail",
            "slots": {"template_id": "faq_helper", "trial_minutes": "15"},
        }
    }
    note = asyncio.run(
        execute_template_reserve(
            effect="tpl_reserve_trial", user_id=800001, user_data=ud
        )
    )
    assert "تجربة" in note or "15" in note
    assert "تعذر تحديد" not in note
