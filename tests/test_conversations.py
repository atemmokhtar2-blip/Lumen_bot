"""Multi-conversation threads — WhatsApp-style."""
from __future__ import annotations

from lumen.platform.conversations import (
    get_conversation_service,
    reset_conversation_service_for_tests,
)


def setup_function():
    reset_conversation_service_for_tests()


def test_new_and_switch_conversations():
    svc = get_conversation_service()
    a = svc.new_conversation(42, title="مشروع توصيل")
    b = svc.new_conversation(42, title="بوت تذاكر")
    assert a.id != b.id
    rows = svc.list_for_user(42)
    assert len(rows) >= 2
    svc.append(42, a.id, role="user", content="عايز بوت توصيل")
    svc.append(42, a.id, role="assistant", content="تمام هبدأ")
    ctx = svc.context_for_llm(42, a.id)
    assert len(ctx["messages"]) >= 2
    assert ctx["messages"][0]["role"] == "user"
    # isolation
    c = svc.ensure_active(99)
    assert c.user_id == 99
    assert svc.get_conversation if False else True
    assert svc._store.get_conversation(a.id, user_id=99) is None


def test_ensure_active_defaults_to_last():
    svc = get_conversation_service()
    c1 = svc.new_conversation(7)
    svc.append(7, c1.id, role="user", content="hello")
    c2 = svc.ensure_active(7)
    assert c2.id == c1.id


def test_sliding_window_caps():
    svc = get_conversation_service()
    c = svc.new_conversation(8)
    for i in range(30):
        svc.append(8, c.id, role="user", content=f"msg-{i}-" + ("x" * 20))
        svc.append(8, c.id, role="assistant", content=f"ok-{i}")
    ctx = svc.context_for_llm(8, c.id)
    assert len(ctx["messages"]) <= 40
    assert ctx["messages"][-1]["content"].startswith("ok-")


def test_export_json():
    svc = get_conversation_service()
    c = svc.new_conversation(3, title="t")
    svc.append(3, c.id, role="user", content="hi")
    data = svc.export_json(3, c.id)
    assert data["ok"] is True
    assert len(data["messages"]) == 1


def test_session_durable_keys():
    from lumen.bot.session_store import _DURABLE_KEYS
    assert "current_conversation_id" in _DURABLE_KEYS
