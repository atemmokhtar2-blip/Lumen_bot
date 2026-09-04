
from lumen.platform.conversations import get_conversation_service, reset_conversation_service_for_tests
from lumen.platform.conversations.inject import merge_history_into_messages


def setup_function():
    reset_conversation_service_for_tests()


def test_merge_history_into_messages():
    svc = get_conversation_service()
    c = svc.new_conversation(101, title="t")
    svc.append(101, c.id, role="user", content="عايز بوت توصيل")
    svc.append(101, c.id, role="assistant", content="هبدأ")
    msgs = [
        {"role": "system", "content": "You are agent"},
        {"role": "user", "content": "كمل"},
    ]
    merged = merge_history_into_messages(msgs, user_id=101, conversation_id=c.id)
    assert merged[0]["role"] == "system"
    assert any("توصيل" in m.get("content", "") for m in merged)
    # no double inject
    merged2 = merge_history_into_messages(merged, user_id=101, conversation_id=c.id)
    assert merged2 == merged


def test_decide_accepts_user_id_kwarg():
    import inspect
    from lumen.engine.services.cline_runtime.agent_brain import decide
    sig = inspect.signature(decide)
    assert "user_id" in sig.parameters
    assert "conversation_id" in sig.parameters
