"""Security fixes: no token-in-URL, Gemini system/user split, rate-limit deploy gate."""
from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest


def test_pr_agent_never_embeds_token_in_clone_url():
    src = Path("lumen/engine/services/integrations/github/pr_agent.py").read_text()
    assert "x-access-token:{token}" not in src
    assert "GIT_ASKPASS" in src
    assert "LUMEN_GIT_TOKEN" in src
    assert "_safe_https_github_clone_url" in src


def test_safe_clone_url_rejects_credentials_and_non_github():
    from lumen.engine.services.integrations.github.pr_agent import (
        _safe_https_github_clone_url,
    )
    with pytest.raises(ValueError, match="credentials"):
        _safe_https_github_clone_url("https://user:tok@github.com/a/b.git")
    with pytest.raises(ValueError, match="not_github"):
        _safe_https_github_clone_url("https://evil.example/a/b.git")
    with pytest.raises(ValueError, match="https"):
        _safe_https_github_clone_url("http://github.com/a/b.git")
    u = _safe_https_github_clone_url("https://github.com/org/repo")
    assert u.startswith("https://github.com/")
    assert "@" not in u


def test_gemini_uses_system_instruction_split():
    src = Path("lumen/engine/services/gemini_client.py").read_text()
    assert "system_instruction" in src
    assert "fence_user_input" in src
    assert "responseSchema" in src
    assert "responseMimeType" in src


def test_rate_limiter_rejects_local_on_railway_marker(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "dev")
    monkeypatch.setenv("ALLOW_INSECURE_LOCAL_RATE_LIMIT", "1")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("TBE_REDIS_URL", raising=False)
    from lumen.platform.rate_limit import RateLimiter
    # reset singleton if any
    import lumen.platform.rate_limit as rl
    rl._LIMITER = None
    with pytest.raises(RuntimeError, match="REDIS_URL"):
        RateLimiter._select_backend()


def test_rate_limiter_allows_lab_only(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "dev")
    monkeypatch.setenv("ALLOW_INSECURE_LOCAL_RATE_LIMIT", "1")
    for m in (
        "RAILWAY_ENVIRONMENT", "KUBERNETES_SERVICE_HOST", "FORCE_PRODUCTION",
        "RENDER_SERVICE_ID", "FLY_APP_NAME", "DYNO",
    ):
        monkeypatch.delenv(m, raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    import lumen.platform.rate_limit as rl
    rl._LIMITER = None
    backend = rl.RateLimiter._select_backend()
    assert type(backend).__name__ in {"SqliteRateLimiter", "MemoryRateLimiter"}
