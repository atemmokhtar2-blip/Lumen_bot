"""Phase 3: unified token resolution priority."""
from __future__ import annotations

import pytest


def test_resolve_access_token_explicit_wins(monkeypatch):
    from lumen.engine.services.integrations.github.client import resolve_access_token

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    assert resolve_access_token(token="explicit_tok") == "explicit_tok"


def test_resolve_access_token_user_before_platform(monkeypatch):
    from lumen.engine.services.integrations.github.client import resolve_access_token

    monkeypatch.setenv("GITHUB_TOKEN", "platform_should_not_win")
    monkeypatch.setattr(
        "lumen.engine.services.integrations.connections.credentials.resolve_github_token",
        lambda uid: f"user-{uid}",
    )
    assert resolve_access_token(user_id=5, allow_platform=True) == "user-5"


def test_resolve_access_token_platform_fallback(monkeypatch):
    from lumen.engine.services.integrations.github.client import resolve_access_token

    monkeypatch.setenv("GITHUB_TOKEN", "plat_tok")
    monkeypatch.setattr(
        "lumen.engine.services.integrations.connections.credentials.resolve_github_token",
        lambda uid: None,
    )
    monkeypatch.setattr(
        "lumen.engine.services.integrations.github.app_auth.github_app_configured",
        lambda: False,
    )
    assert resolve_access_token(user_id=1, allow_platform=True) == "plat_tok"


def test_resolve_access_token_raises_when_nothing(monkeypatch):
    from lumen.engine.services.integrations.github.client import resolve_access_token

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setattr(
        "lumen.engine.services.integrations.connections.credentials.resolve_github_token",
        lambda uid: None,
    )
    monkeypatch.setattr(
        "lumen.engine.services.integrations.github.app_auth.github_app_configured",
        lambda: False,
    )
    with pytest.raises(ValueError, match="github_token_unavailable"):
        resolve_access_token(user_id=1, allow_platform=True)


def test_pr_agent_token_uses_resolver(monkeypatch):
    from lumen.engine.services.integrations.github import pr_agent as pa

    monkeypatch.setattr(
        "lumen.engine.services.integrations.github.client.resolve_access_token",
        lambda **kw: "resolved-from-repo",
    )
    assert pa._token(owner="o", repo="r") == "resolved-from-repo"
