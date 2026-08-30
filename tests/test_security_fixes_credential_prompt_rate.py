"""Root-cause security fixes: credential URL, Gemini split, Redis-only rate limit."""
from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest


def test_pr_agent_never_embeds_token_in_clone_url():
    src = Path("lumen/engine/services/integrations/github/pr_agent.py").read_text()
    assert "x-access-token:{token}" not in src
    assert "https://x-access-token:" not in src
    assert "GIT_ASKPASS" in src
    assert "LUMEN_GIT_TOKEN" in src
    assert "_git_clone_authenticated" in src


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
    assert u == "https://github.com/org/repo.git"
    assert "@" not in u


def test_gemini_system_prompt_has_no_user_message_slot():
    src = Path("lumen/engine/services/gemini_client.py").read_text()
    assert "def _system_prompt(" in src
    assert "system_instruction" in src
    assert "fence_user_input" in src
    assert "responseSchema" in src
    # User text must not be interpolated into system prompt builder
    assert "{_wrap_user_payload(text)}" not in src
    assert "text[:20000]" not in src


def test_rate_limiter_requires_redis_even_in_dev(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "dev")
    monkeypatch.setenv("ALLOW_INSECURE_LOCAL_RATE_LIMIT", "1")
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("JOB_REDIS_URL", raising=False)
    monkeypatch.delenv("TBE_REDIS_URL", raising=False)
    import lumen.platform.rate_limit as rl
    rl._LIMITER = None
    with pytest.raises(RuntimeError, match="REDIS_URL"):
        rl.RateLimiter._select_backend()


def test_rate_limiter_no_memory_path_in_select_source():
    src = Path("lumen/platform/rate_limit.py").read_text()
    # Selection path must not return Memory/SQLite
    select = src.split("def _select_backend")[1].split("def allow")[0]
    assert "MemoryRateLimiter()" not in select
    assert "SqliteRateLimiter()" not in select
    assert "RedisRateLimiter" in select


def test_smart_clone_inject_token_never_embeds():
    from lumen.engine.services.git_operations.smart_clone import _inject_token
    u = "https://github.com/org/repo.git"
    out = _inject_token(u, "ghp_secret_with:colon@and")
    assert out == u or "@" not in urlparse_netloc(out)
    assert "ghp_secret" not in out
    assert "x-access-token:" not in out


def urlparse_netloc(url: str) -> str:
    from urllib.parse import urlparse
    return urlparse(url).netloc


def test_smart_clone_strips_existing_userinfo():
    from lumen.engine.services.git_operations.smart_clone import _inject_token
    dirty = "https://x-access-token:oldtok@github.com/org/repo.git"
    out = _inject_token(dirty, "newtok")
    assert "oldtok" not in out
    assert "newtok" not in out
    assert "x-access-token" not in out


def test_no_token_interpolation_left_in_git_ops():
    from pathlib import Path
    root = Path("lumen/engine/services/git_operations")
    bad = []
    for p in root.rglob("*.py"):
        text = p.read_text(encoding="utf-8", errors="ignore")
        if "x-access-token:{token}" in text or "oauth2:{token}" in text:
            bad.append(str(p))
    assert bad == [], bad
