"""Phase 0–1: template catalog, policy caps, in-memory store."""
from __future__ import annotations

import time

from lumen.templates.catalog import get_template, list_templates
from lumen.templates.models import TemplateInstanceStatus, TemplateLaunchMode
from lumen.templates.policy import (
    FREE_MAX_RUNNING_TEMPLATES,
    TRIAL_MAX_MINUTES,
    can_launch,
    clamp_trial_minutes,
    count_active,
)
from lumen.templates.store import (
    clear_user_for_tests,
    list_instances,
    mark_expired,
    reserve_instance,
    update_instance,
)


def test_catalog_has_enabled_templates():
    specs = list_templates(enabled_only=True)
    assert len(specs) >= 3
    ids = {s.id for s in specs}
    assert "group_moderator" in ids
    assert get_template("shop_assistant") is not None
    assert get_template("missing_x") is None


def test_clamp_trial_minutes():
    assert clamp_trial_minutes(0) == 0
    assert clamp_trial_minutes(-1) == 0
    assert clamp_trial_minutes(1) == 1
    assert clamp_trial_minutes(50) == 50
    assert clamp_trial_minutes(51) == TRIAL_MAX_MINUTES
    assert clamp_trial_minutes(999) == 50


def test_policy_rejects_over_quota():
    from lumen.templates.models import TemplateInstance

    now = time.time()
    insts = [
        TemplateInstance(
            instance_id=f"i{i}",
            user_id=1,
            template_id="group_moderator",
            mode=TemplateLaunchMode.TRIAL,
            status=TemplateInstanceStatus.RUNNING,
            started_at=now,
            expires_at=now + 3600,
        )
        for i in range(FREE_MAX_RUNNING_TEMPLATES)
    ]
    assert count_active(insts) == 3
    d = can_launch(mode=TemplateLaunchMode.TRIAL, instances=insts, trial_minutes=10, now=now)
    assert d.allowed is False
    assert "max_running" in d.reason


def test_policy_trial_and_permanent_expiry():
    now = 1_700_000_000.0
    d = can_launch(mode="trial", instances=[], trial_minutes=30, now=now)
    assert d.allowed is True
    assert d.trial_minutes == 30
    assert d.expires_at == now + 30 * 60

    d2 = can_launch(mode=TemplateLaunchMode.PERMANENT, instances=[], now=now)
    assert d2.allowed is True
    assert d2.expires_at == now + 30 * 86400


def test_store_reserve_and_expire():
    uid = 424242
    clear_user_for_tests(uid)
    now = time.time()
    inst, reason = reserve_instance(
        uid, template_id="faq_helper", mode=TemplateLaunchMode.TRIAL, trial_minutes=5, now=now
    )
    assert reason == "ok"
    assert inst is not None
    assert inst.status == TemplateInstanceStatus.PREPARING
    assert inst.expires_at == now + 300

    listed = list_instances(uid)
    assert len(listed) == 1

    # Fill quota to 3
    for i in range(2):
        inst_i, r = reserve_instance(
            uid, template_id="shop_assistant", mode="trial", trial_minutes=10, now=now
        )
        assert r == "ok", r

    blocked, reason_b = reserve_instance(
        uid, template_id="group_moderator", mode="trial", trial_minutes=10, now=now
    )
    assert blocked is None
    assert "max_running" in reason_b

    # Expire all by clock
    past = now + 10_000
    mark_expired(uid, now=past)
    after = list_instances(uid)
    assert all(x.status == TemplateInstanceStatus.EXPIRED for x in after)

    # Quota frees after expiry
    inst2, r2 = reserve_instance(
        uid, template_id="group_moderator", mode=TemplateLaunchMode.PERMANENT, now=past
    )
    assert r2 == "ok"
    assert inst2 is not None
    assert inst2.mode == TemplateLaunchMode.PERMANENT

    updated = update_instance(uid, inst2.instance_id, status=TemplateInstanceStatus.RUNNING, host_instance_id="h1")
    assert updated is not None
    assert updated.status == TemplateInstanceStatus.RUNNING
    assert updated.host_instance_id == "h1"

    clear_user_for_tests(uid)
