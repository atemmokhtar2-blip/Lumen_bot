"""Tests against architecture-plan DynamicBotSpec atoms EXACTLY."""
from __future__ import annotations

import pytest

# Exact atoms from the plan
SAMPLE = {
    "bot_name": "support_bot",
    "language": "ar",
    "description": "simple support",
    "version": "infinite_v1",
    "nodes": [
        {
            "id": "start_node",
            "trigger": {"type": "on_command", "config": {"command": "start"}},
            "conditions": [],
            "actions": [
                {"type": "send_message", "config": {"text": "مرحباً — كيف أساعدك؟"}}
            ],
        },
        {
            "id": "help_node",
            "trigger": {"type": "on_command", "config": {"command": "help"}},
            "actions": [
                {"type": "send_message", "config": {"text": "الأوامر: /start /help"}}
            ],
        },
    ],
}


def test_plan_model_in_schema_py():
    from telegram_bot_engine.spec_core.schema import (
        DynamicBotSpec,
        FlowNode,
        run_rule_engine,
        INFINITE_ALLOWED_ACTIONS,
    )

    assert DynamicBotSpec is not None
    assert FlowNode is not None
    assert run_rule_engine is not None
    assert INFINITE_ALLOWED_ACTIONS == frozenset(
        {"send_message", "update_db", "call_api", "change_state"}
    )


def test_validate_ok():
    from telegram_bot_engine.spec_core.dynamic_bot_spec import parse_dynamic_spec

    dyn = parse_dynamic_spec(SAMPLE)
    assert dyn.bot_name == "support_bot"
    assert len(dyn.nodes) == 2


def test_reject_unknown_action():
    from telegram_bot_engine.spec_core.dynamic_bot_spec import parse_dynamic_spec

    bad = {
        **SAMPLE,
        "nodes": [
            {
                "id": "x",
                "trigger": {"type": "on_message", "config": {}},
                "actions": [{"type": "exec_shell", "config": {}}],
            }
        ],
    }
    with pytest.raises(Exception):
        parse_dynamic_spec(bad)


def test_reject_cycle():
    from telegram_bot_engine.spec_core.dynamic_bot_spec import parse_dynamic_spec

    cyc = {
        "bot_name": "loop",
        "nodes": [
            {
                "id": "a",
                "trigger": {"type": "on_message", "config": {}},
                "actions": [{"type": "send_message", "config": {"text": "a"}}],
                "next_node_id": "b",
            },
            {
                "id": "b",
                "trigger": {"type": "on_message", "config": {}},
                "actions": [{"type": "send_message", "config": {"text": "b"}}],
                "next_node_id": "a",
            },
        ],
    }
    with pytest.raises(Exception) as ei:
        parse_dynamic_spec(cyc)
    assert "loop" in str(ei.value).lower() or "Infinite" in str(ei.value)


def test_rule_engine_send_message():
    from telegram_bot_engine.spec_core.rule_engine import run_rule_engine

    out = run_rule_engine(
        SAMPLE,
        {"type": "on_command", "command": "help", "text": ""},
    )
    assert out["ok"]
    assert out["results"]
    assert out["results"][0]["type"] == "send_message"


def test_rule_engine_update_db_and_change_state():
    from telegram_bot_engine.spec_core.rule_engine import run_rule_engine

    spec = {
        "bot_name": "dbbot",
        "nodes": [
            {
                "id": "n1",
                "trigger": {"type": "on_command", "config": {"command": "set"}},
                "conditions": [
                    {"type": "state_equals", "config": {"key": "ready", "value": True}}
                ],
                "actions": [
                    {"type": "update_db", "config": {"key": "k", "value": 1}},
                    {"type": "change_state", "config": {"key": "ready", "value": False}},
                ],
            }
        ],
    }
    out = run_rule_engine(
        spec,
        {"type": "on_command", "command": "set"},
        state={"ready": True},
    )
    assert out["state"]["k"] == 1
    assert out["state"]["ready"] is False


def test_call_api_ssrf_blocked():
    from telegram_bot_engine.spec_core.rule_engine import run_rule_engine

    spec = {
        "bot_name": "api",
        "nodes": [
            {
                "id": "n1",
                "trigger": {"type": "on_command", "config": {"command": "x"}},
                "actions": [
                    {"type": "call_api", "config": {"url": "http://127.0.0.1/secret"}}
                ],
            }
        ],
    }
    out = run_rule_engine(spec, {"type": "on_command", "command": "x"})
    # should not succeed against localhost
    assert out["results"]
    r = out["results"][0]
    assert r.get("error") or not (r.get("result") or {}).get("ok", True)


def test_compose_and_route():
    from telegram_bot_engine.spec_core.infinite.compose import compose_infinite_from_payload
    from telegram_bot_engine.spec_core.infinite.engine_router import route_and_execute

    bot, dyn = compose_infinite_from_payload(SAMPLE)
    assert "engine:infinite_v1" in bot.hard_constraints
    out = route_and_execute(dyn, {"type": "on_command", "command": "start"})
    assert out["ok"]


def test_macro_promote(tmp_path, monkeypatch):
    monkeypatch.setenv("TBE_MACRO_REGISTRY_DIR", str(tmp_path))
    from telegram_bot_engine.spec_core.infinite.macro_registry import MacroRegistry

    reg = MacroRegistry(root=tmp_path)
    mid = reg.promote(SAMPLE, macro_id="support_v1")
    assert reg.get("support_v1") is not None


def test_command_does_not_fire_on_message():
    from telegram_bot_engine.spec_core.rule_engine import run_rule_engine

    spec = {
        "bot_name": "x",
        "nodes": [
            {
                "id": "m",
                "trigger": {"type": "on_message", "config": {}},
                "actions": [{"type": "send_message", "config": {"text": "msg"}}],
            }
        ],
    }
    out = run_rule_engine(spec, {"type": "on_message", "command": "start", "text": "x"})
    assert out["results"] == []


def test_template_text_after_regex():
    from telegram_bot_engine.spec_core.rule_engine import run_rule_engine

    spec = {
        "bot_name": "x",
        "nodes": [
            {
                "id": "m",
                "trigger": {"type": "on_message", "config": {}},
                "transformers": [
                    {"type": "extract_regex", "config": {"pattern": "id=([0-9]+)"}}
                ],
                "actions": [
                    {"type": "send_message", "config": {"text": "got {{text}}"}}
                ],
            }
        ],
    }
    out = run_rule_engine(spec, {"type": "on_message", "text": "user id=99 here"})
    assert out["results"] and "99" in out["results"][0]["text"]


def test_invalid_state_key_rejected():
    from telegram_bot_engine.spec_core.rule_engine import run_rule_engine

    spec = {
        "bot_name": "x",
        "nodes": [
            {
                "id": "m",
                "trigger": {"type": "on_command", "config": {"command": "x"}},
                "actions": [
                    {"type": "update_db", "config": {"key": "__proto__", "value": 1}}
                ],
            }
        ],
    }
    out = run_rule_engine(spec, {"type": "on_command", "command": "x"})
    assert out["results"][0].get("error") == "invalid_key"
    assert "__proto__" not in out["state"]


def test_dag_walk_follows_next_node_id():
    """Core plan behavior: atoms form a graph; engine walks next_node_id."""
    from telegram_bot_engine.spec_core.rule_engine import run_rule_engine

    spec = {
        "bot_name": "chain",
        "nodes": [
            {
                "id": "entry",
                "trigger": {"type": "on_command", "config": {"command": "go"}},
                "actions": [
                    {"type": "change_state", "config": {"key": "step", "value": 1}},
                    {"type": "send_message", "config": {"text": "one"}},
                ],
                "next_node_id": "second",
            },
            {
                "id": "second",
                "trigger": {"type": "on_message", "config": {}},  # not matching event
                "conditions": [
                    {"type": "state_equals", "config": {"key": "step", "value": 1}}
                ],
                "actions": [
                    {"type": "send_message", "config": {"text": "two"}},
                    {"type": "change_state", "config": {"key": "step", "value": 2}},
                ],
                "next_node_id": "third",
            },
            {
                "id": "third",
                "trigger": {"type": "on_schedule", "config": {}},
                "actions": [{"type": "send_message", "config": {"text": "three"}}],
            },
        ],
    }
    out = run_rule_engine(spec, {"type": "on_command", "command": "go"})
    assert out["dag"] is True
    assert out["entry_nodes"] == ["entry"]
    assert out["graph_paths"] == [["entry", "second", "third"]]
    texts = [r["text"] for r in out["results"] if r.get("type") == "send_message"]
    assert texts == ["one", "two", "three"]
    assert out["state"]["step"] == 2


def test_dag_stops_when_condition_fails_mid_chain():
    from telegram_bot_engine.spec_core.rule_engine import run_rule_engine

    spec = {
        "bot_name": "stop",
        "nodes": [
            {
                "id": "a",
                "trigger": {"type": "on_command", "config": {"command": "x"}},
                "actions": [{"type": "send_message", "config": {"text": "a"}}],
                "next_node_id": "b",
            },
            {
                "id": "b",
                "trigger": {"type": "on_message", "config": {}},
                "conditions": [
                    {"type": "user_is_admin", "config": {}}
                ],
                "actions": [{"type": "send_message", "config": {"text": "b"}}],
            },
        ],
    }
    out = run_rule_engine(
        spec, {"type": "on_command", "command": "x", "is_admin": False}
    )
    texts = [r["text"] for r in out["results"] if r.get("type") == "send_message"]
    assert texts == ["a"]  # chain stops — b requires admin
