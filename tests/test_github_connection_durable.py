"""GitHub connection survives deploy: Mongo source of truth pattern."""
from __future__ import annotations


def test_github_connection_store_module():
    from lumen.bot.ui.github_connection_store import (
        write_github_connection,
        read_github_token,
        read_github_profile,
        recover_after_session_drop,
    )
    assert callable(write_github_connection)
    assert callable(read_github_token)
    assert callable(recover_after_session_drop)


def test_provider_uses_durable_read(monkeypatch, tmp_path):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("TBE_TOKEN_SECRET", "unit-test-secret-key-32b!!")
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    monkeypatch.delenv("REDIS_URL", raising=False)
    from lumen.engine.services.integrations.connections.github_provider import (
        store_github_connection_token,
        _token_for_user,
    )
    # Without Mongo, still works via Redis/inbox path
    assert store_github_connection_token(55, "ghp_durableTestToken1234567890", login="alice")
    assert _token_for_user(55) == "ghp_durableTestToken1234567890"


def test_ensure_account_links_exported():
    from lumen.bot.session_store import ensure_account_links
    ud = {}
    ensure_account_links(0, ud)  # no-op
    ensure_account_links(1, ud)


def test_drop_user_data_recovers_github_in_source():
    src = open("lumen/bot/ptb_redis_persistence.py", encoding="utf-8").read()
    assert "recover_after_session_drop" in src
    assert "github_connection" in src
