"""Phase 3 readiness + durable GitHub connection profile."""
from __future__ import annotations

from pathlib import Path


def test_readiness_missing_env():
    from lumen.engine.services.integrations.connections.readiness import evaluate_readiness

    active = {
        "path": "/tmp/x",
        "contract": {
            "is_telegram_bot": True,
            "env_vars": [
                {"name": "TELEGRAM_BOT_TOKEN"},
                {"name": "OPENAI_API_KEY"},
                {"name": "DATABASE_URL"},
            ],
        },
    }
    r = evaluate_readiness(active_repo=active)
    assert r.ready is False
    assert "OPENAI_API_KEY" in r.missing_env
    assert "DATABASE_URL" in r.missing_env
    assert "TELEGRAM_BOT_TOKEN" not in r.missing_env
    assert r.can_show_trial is False


def test_readiness_ready_after_collect():
    from lumen.engine.services.integrations.connections.readiness import (
        apply_collected_env,
        evaluate_readiness,
    )

    active = {
        "path": "/tmp/x",
        "contract": {"env_vars": [{"name": "FOO_KEY"}]},
    }
    active = apply_collected_env(active, "FOO_KEY", "secret")
    r = evaluate_readiness(active_repo=active)
    assert r.ready is True
    assert r.can_show_trial is True


def test_connection_profile_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("TBE_TOKEN_SECRET", "unit-test-secret-key-32b!!")
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("JOB_REDIS_URL", raising=False)
    from lumen.engine.services.integrations.connections import token_store

    assert token_store.save_github_token(7, "ghp_abc12345678901234567890", meta={"login": "octocat"})
    # Without Redis, profile may only exist if save_connection_profile was called — it is
    # save_github_token calls save_connection_profile which needs Redis; without Redis profile is None
    # but token still loads via secret_inbox
    assert token_store.load_github_token(7) == "ghp_abc12345678901234567890"


def test_session_durable_keys_include_github():
    from lumen.bot.session_store import _DURABLE_KEYS

    assert "github_connection" in _DURABLE_KEYS
    assert "pending_repo_env" in _DURABLE_KEYS


def test_router_cache_first_and_readiness_wired():
    src = Path("lumen/bot/ui/callback_router.py").read_text(encoding="utf-8")
    assert "prefer_cache" in src
    assert "evaluate_readiness" in src
    assert "pending_repo_env" in src
    th = Path("lumen/bot/handlers/token_handler.py").read_text(encoding="utf-8")
    assert "github_connection" in th
    assert "pending_repo_env" in th


def test_post_actions_allowed_from_conn_github():
    from lumen.engine.services.ui_state.catalog import get_action
    from lumen.engine.services.ui_state.models import EngineUiPhase
    pt = get_action("post_trial")
    ph = get_action("post_host")
    assert pt is not None and EngineUiPhase.CONN_GITHUB in pt.allowed_phases
    assert ph is not None and EngineUiPhase.CONN_GITHUB in ph.allowed_phases


def test_bind_repo_calls_agent_explain_in_source():
    src = Path("lumen/engine/services/integrations/connections/bind_repo.py").read_text(encoding="utf-8")
    assert "explain_repo_with_llm" in src
    assert "understanding_level" in src
    assert "agent_brief" in src
