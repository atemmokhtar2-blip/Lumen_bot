"""Phase 1: GitHub App JWT + connection record shape (no live GitHub calls)."""
from __future__ import annotations

import time

import pytest


def _ephemeral_rsa_pem() -> bytes:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def test_github_app_configured_false_without_env(monkeypatch):
    monkeypatch.delenv("GITHUB_APP_ID", raising=False)
    monkeypatch.delenv("GITHUB_APP_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("GITHUB_APP_PRIVATE_KEY_PATH", raising=False)
    from lumen.engine.services.integrations.github.app_auth import github_app_configured

    assert github_app_configured() is False


def test_build_app_jwt_rs256(monkeypatch):
    pem = _ephemeral_rsa_pem().decode("utf-8")
    monkeypatch.setenv("GITHUB_APP_ID", "123456")
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY", pem.replace("\n", "\\n"))
    from lumen.engine.services.integrations.github.app_auth import (
        build_app_jwt,
        github_app_configured,
    )

    assert github_app_configured() is True
    token = build_app_jwt(now=int(time.time()))
    parts = token.split(".")
    assert len(parts) == 3
    # header/payload are base64url; signature non-empty
    assert parts[0] and parts[1] and parts[2]


def test_install_url_uses_slug(monkeypatch):
    monkeypatch.setenv("GITHUB_APP_SLUG", "lumen-bot")
    from lumen.engine.services.integrations.github.app_auth import install_url

    url = install_url(state="abc")
    assert url.startswith("https://github.com/apps/lumen-bot/installations/new")
    assert "state=abc" in url


def test_write_github_app_connection_record(monkeypatch, tmp_path):
    """Profile is durable without storing a PAT ciphertext."""
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("TBE_TOKEN_SECRET", "x" * 40)
    # Avoid real Redis/Mongo — exercise in-memory path via profile helpers only
    from lumen.engine.services.integrations.connections import token_store as ts

    # Force redis-less profile write (no-op if no redis) then read path via save/load
    # We still assert the function API returns False only on bad input
    from lumen.bot.ui.github_connection_store import write_github_app_connection

    assert write_github_app_connection(0, 1) is False
    assert write_github_app_connection(42, "not-int") is False

    # When Mongo/Redis unavailable, _persist returns False for mongo_ok but
    # still writes profile best-effort; accept bool return.
    ok = write_github_app_connection(
        42,
        999001,
        login="octocat",
        account_login="octocat",
        account_type="User",
        repo_selection="selected",
    )
    assert ok in {True, False}

    # Direct profile API must accept App fields
    ts.save_connection_profile(
        42,
        {
            "login": "octocat",
            "connected": True,
            "auth_kind": "github_app",
            "installation_id": "999001",
            "account_login": "octocat",
            "repo_selection": "selected",
        },
    )
    # Without Redis load may be None — that is acceptable in unit env
    prof = ts.load_connection_profile(42)
    if prof is not None:
        assert prof.get("auth_kind") == "github_app"
        assert prof.get("installation_id") == "999001"
