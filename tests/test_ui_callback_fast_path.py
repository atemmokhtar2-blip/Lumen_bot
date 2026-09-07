"""Verify UI callback fast path: no LLM budget on clicks; security gates intact."""
from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_rate_limit_ui_ok_source_has_no_llm_budget():
    src = (ROOT / "lumen/bot/middlewares/auth.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    ui_fn = None
    full_fn = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "rate_limit_ui_ok":
            ui_fn = node
        if isinstance(node, ast.FunctionDef) and node.name == "rate_limit_ok":
            full_fn = node
    assert ui_fn is not None, "rate_limit_ui_ok missing"
    assert full_fn is not None, "rate_limit_ok missing"
    ui_src = ast.get_source_segment(src, ui_fn) or ""
    full_src = ast.get_source_segment(src, full_fn) or ""
    assert "check_tenant_llm_budget" not in ui_src
    assert "check_tenant_llm_budget" in full_src
    assert "get_rate_limiter" in ui_src


def test_callback_router_uses_ui_rate_limit_not_full():
    src = (ROOT / "lumen/bot/ui/callback_router.py").read_text(encoding="utf-8")
    # handle_ui_callback must use rate_limit_ui_ok
    assert "rate_limit_ui_ok" in src
    # Must not call full rate_limit_ok on the UI handler path
    # (rate_limit_ok string may appear only in comments — forbid import of it in router)
    assert "from lumen.bot.middlewares.auth import rate_limit_ok" not in src
    assert "cache_time" in src
    assert "_UI_CACHEABLE_ACTIONS" in src


def test_sensitive_actions_not_cacheable():
    os.environ.setdefault("ENVIRONMENT", "development")
    os.environ.setdefault("SESSION_ALLOW_MEMORY", "1")
    # Parse set from source without importing bot package (secrets gate).
    src = (ROOT / "lumen/bot/ui/callback_router.py").read_text(encoding="utf-8")
    sensitive = {
        "buy_pro_plan",
        "confirm_generate",
        "cancel_generate",
        "dash_stop",
        "dash_diagnose",
        "hitl_confirm",
        "hitl_reject",
        "post_host",
    }
    # Extract frozenset literal contents roughly
    assert "_UI_CACHEABLE_ACTIONS" in src
    for a in sensitive:
        # sensitive must not appear inside the cacheable frozenset block
        pass
    start = src.index("_UI_CACHEABLE_ACTIONS")
    end = src.index(")", start)
    block = src[start:end]
    for a in sensitive:
        assert f'"{a}"' not in block, f"{a} must not be client-cacheable"


def test_subscription_write_invalidates_facts_cache():
    src = (ROOT / "lumen/bot/ui/subscription_store.py").read_text(encoding="utf-8")
    assert "invalidate_facts_cache" in src
    assert "write_subscription" in src


def test_answer_order_rate_limit_before_answer():
    """Rate-limit check must precede the success answer so reject toast works."""
    src = (ROOT / "lumen/bot/ui/callback_router.py").read_text(encoding="utf-8")
    # Find handle_ui_callback body
    i = src.index("async def handle_ui_callback")
    body = src[i : src.index("async def _handle_ui_callback_body")]
    assert body.index("rate_limit_ui_ok") < body.index("await q.answer(cache_time=")
    assert "rate_blocked" in body
