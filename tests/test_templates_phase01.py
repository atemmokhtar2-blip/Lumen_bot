"""Phase 0–1 hardened: hexagonal templates plane."""
from __future__ import annotations

import time

import pytest

from lumen.templates.catalog import JsonTemplateCatalog, list_templates, get_template
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
        validate_template_id("x")


def test_catalog_port_and_specs():
    cat = JsonTemplateCatalog()
    enabled = list(cat.list_enabled())
    assert len(enabled) >= 3
    assert all(isinstance(s, TemplateSpec) for s in enabled)
    assert get_template("shop_assistant") is not None
    assert get_template("nope") is None
    assert len(list_templates()) >= 3


def test_policy_pure_caps():
    now = 1_700_000_000.0
    assert clamp_trial_minutes(51) == TRIAL_MAX_MINUTES
    assert clamp_trial_minutes(0) == 0

    d = evaluate_launch(mode="trial", instances=[], now=now, trial_minutes=30)
    assert d.allowed and d.plan is not None
    assert d.plan.expires_at == now + 1800

    d2 = evaluate_launch(mode=TemplateLaunchMode.PERMANENT, instances=[], now=now)
    assert d2.allowed and d2.plan is not None
    assert d2.plan.expires_at == now + 30 * 86400

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
    denied = evaluate_launch(mode="trial", instances=full, now=now, trial_minutes=10)
    assert denied.allowed is False
    assert "max_running" in denied.reason


def test_service_reserve_atomic_quota():
    store = MemoryTemplateStore()
    svc = TemplateService(store=store)
    uid = 900001
    now = time.time()

    r1 = svc.reserve(uid, template_id="faq_helper", mode="trial", trial_minutes=5, now=now)
    assert r1.ok and r1.instance is not None
    assert r1.instance.trial_minutes == 5

    for _ in range(2):
        r = svc.reserve(uid, template_id="shop_assistant", mode="trial", trial_minutes=10, now=now)
        assert r.ok, r.reason

    blocked = svc.reserve(uid, template_id="group_moderator", mode="trial", trial_minutes=10, now=now)
    assert blocked.ok is False
    assert "max_running" in blocked.reason

    # Expire via past now + re-reserve permanent
    past = now + 10_000
    # force expiry by rewriting store
    insts = store.list_for_user(uid)
    for i in insts:
        i.status = TemplateInstanceStatus.EXPIRED
    store.save_for_user(uid, insts)

    r_perm = svc.reserve(uid, template_id="group_moderator", mode="permanent", now=past)
    assert r_perm.ok and r_perm.instance is not None
    assert r_perm.instance.mode == TemplateLaunchMode.PERMANENT

    running = svc.mark_running(uid, r_perm.instance.instance_id, host_instance_id="host_abc")
    assert running is not None
    assert running.status == TemplateInstanceStatus.RUNNING
    assert running.host_instance_id == "host_abc"


def test_architecture_templates_isolation():
    """templates package must not import bot or hosting implementation."""
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "lumen" / "templates"
    offenders = []
    for p in root.rglob("*.py"):
        src = p.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("lumen.bot") or alias.name.startswith("lumen.hosting"):
                        offenders.append(f"{p.name}:import {alias.name}")
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith("lumen.bot") or node.module.startswith("lumen.hosting"):
                    offenders.append(f"{p.name}:from {node.module}")
                if node.module.startswith("lumen.engine.services.hosting"):
                    offenders.append(f"{p.name}:from {node.module}")
    assert not offenders, offenders
