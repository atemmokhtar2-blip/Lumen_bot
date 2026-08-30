"""Prove standalone chat layer is gone — engine/agents own every NL message path."""
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "lumen/bot/routers/message_router.py"


def test_message_router_never_calls_chat_request():
    src = ROUTER.read_text(encoding="utf-8")
    # Allow comments only
    for i, line in enumerate(src.splitlines(), 1):
        stripped = line.strip()
        if "chat_request" in stripped and not stripped.startswith("#"):
            raise AssertionError(
                f"message_router.py:{i} still references chat_request outside a comment: {stripped[:120]}"
            )


def test_message_router_does_not_import_translator_chat():
    src = ROUTER.read_text(encoding="utf-8")
    assert "from lumen.engine.services.translator_client import chat_request" not in src
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            names = {a.name for a in (node.names or [])}
            if "translator_client" in mod and "chat_request" in names:
                raise AssertionError("Import of chat_request from translator_client still present")


def test_standalone_chat_block_removed_marker_present():
    src = ROUTER.read_text(encoding="utf-8")
    assert "STANDALONE CHAT REMOVED" in src
    assert "engine / agents own every NL message" in src
    # Old policy string must be gone
    assert "Every natural-language message goes to the standalone chat model first" not in src


def test_engine_routing_still_present():
    src = ROUTER.read_text(encoding="utf-8")
    # Agents own the path via engine_turn + generation + HITL
    assert "handle_user_turn" in src
    assert "execute_bot_generation" in src
    assert "force_generate_once" in src
    assert "try_handle_hitl_message" in src
    assert "try_handle_token" in src


def test_no_gemini_chat_outage_user_messages():
    """User must never see standalone-chat outage prompts."""
    src = ROUTER.read_text(encoding="utf-8")
    forbidden = [
        "طبقة المحادثة غير مفعّلة",
        "طبقة المحادثة معطّلة",
        "تعذر تشغيل طبقة المحادثة الآن",
    ]
    for phrase in forbidden:
        assert phrase not in src, f"standalone chat outage message still present: {phrase}"


def test_chat_route_is_capability_router_not_llm():
    """chat_route helper must only call chat_router.route_message (phrase routing)."""
    helpers = (ROOT / "lumen/bot/helpers.py").read_text(encoding="utf-8")
    assert "from lumen.engine.services.chat_router import route_message" in helpers
    assert "chat_request" not in helpers
