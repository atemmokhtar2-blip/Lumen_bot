"""GitHub App authentication — JWT + installation access tokens.

Phase 1 foundation for replacing user-submitted PATs with GitHub App installs.

Env (required for App path):
  GITHUB_APP_ID              — numeric App ID
  GITHUB_APP_PRIVATE_KEY     — PEM private key (or path via GITHUB_APP_PRIVATE_KEY_PATH)
  GITHUB_APP_CLIENT_ID       — optional (user-to-server OAuth later)
  GITHUB_APP_CLIENT_SECRET   — optional
  GITHUB_APP_SLUG            — optional, for install URL in phase 2

Tokens issued here are short-lived (GitHub max ~1h). Never persist installation
access tokens as long-lived secrets; cache in-process / Redis with TTL only.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import threading
import time
from typing import Any
from lumen.platform.redis_client import connect_redis_url

logger = logging.getLogger("lumen.github.app_auth")

_API = (os.getenv("GITHUB_API_BASE") or "https://api.github.com").rstrip("/")
_TOKEN_SKEW_SEC = 60  # refresh before real expiry
_JWT_TTL_SEC = 9 * 60  # GitHub allows max 10 minutes

_lock = threading.Lock()
# installation_id -> {token, expires_at}
_install_token_cache: dict[str, dict[str, Any]] = {}


def github_app_configured() -> bool:
    """True when App ID + private key material are present."""
    app_id = (os.getenv("GITHUB_APP_ID") or "").strip()
    if not app_id:
        return False
    try:
        _load_private_key_pem()
        return True
    except Exception:
        return False


def _load_private_key_pem() -> bytes:
    # Prefer in-process secrets store (Phase B managed keys), then environ / path.
    raw = ""
    try:
        from lumen.platform.secrets_provider import get_secret

        raw = (get_secret("GITHUB_APP_PRIVATE_KEY", "") or "").strip()
    except Exception:
        raw = ""
    if not raw:
        raw = (os.getenv("GITHUB_APP_PRIVATE_KEY") or "").strip()
    if raw:
        # Support escaped newlines from env managers
        pem = raw.replace("\\n", "\n").encode("utf-8")
        if b"BEGIN" in pem:
            return pem
    path = (os.getenv("GITHUB_APP_PRIVATE_KEY_PATH") or "").strip()
    if path:
        with open(path, "rb") as fh:
            return fh.read()
    raise RuntimeError("GITHUB_APP_PRIVATE_KEY or GITHUB_APP_PRIVATE_KEY_PATH required")


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def build_app_jwt(*, now: int | None = None) -> str:
    """RS256 JWT for GitHub App authentication (max 10 min lifetime)."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    app_id = (os.getenv("GITHUB_APP_ID") or "").strip()
    if not app_id:
        raise RuntimeError("GITHUB_APP_ID required")

    pem = _load_private_key_pem()
    key = serialization.load_pem_private_key(pem, password=None)

    ts = int(now if now is not None else time.time())
    header = {"alg": "RS256", "typ": "JWT"}
    payload = {
        "iat": ts - 60,  # clock skew tolerance
        "exp": ts + _JWT_TTL_SEC,
        "iss": app_id,
    }
    segments = (
        _b64url(json.dumps(header, separators=(",", ":")).encode("utf-8"))
        + "."
        + _b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    )
    signature = key.sign(  # type: ignore[union-attr]
        segments.encode("ascii"),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    return segments + "." + _b64url(signature)


def _app_headers(jwt: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {jwt}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Lumen-GitHub-App",
    }


def create_installation_access_token(
    installation_id: int | str,
    *,
    repositories: list[str] | None = None,
    permissions: dict[str, str] | None = None,
) -> dict[str, Any]:
    """POST /app/installations/{id}/access_tokens — returns token + expires_at.

    Does not use the in-process cache; callers that want caching should use
    get_installation_token().
    """
    import requests

    iid = str(int(installation_id))
    jwt = build_app_jwt()
    body: dict[str, Any] = {}
    if repositories:
        body["repositories"] = list(repositories)[:100]
    if permissions:
        body["permissions"] = dict(permissions)

    resp = requests.post(
        f"{_API}/app/installations/{iid}/access_tokens",
        headers=_app_headers(jwt),
        json=body or None,
        timeout=float(os.getenv("GITHUB_HTTP_TIMEOUT") or "30"),
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"github_app_token_{resp.status_code}:{resp.text[:400]}")
    data = resp.json() if resp.content else {}
    token = str(data.get("token") or "").strip()
    if not token:
        raise RuntimeError("github_app_token_empty")
    return {
        "token": token,
        "expires_at": str(data.get("expires_at") or ""),
        "permissions": data.get("permissions") or {},
        "repository_selection": data.get("repository_selection") or "",
        "installation_id": iid,
    }


def _parse_expires_at(expires_at: str) -> float:
    """GitHub returns ISO8601 UTC, e.g. 2026-09-10T10:00:00Z."""
    s = (expires_at or "").strip()
    if not s:
        return time.time() + 3600
    try:
        # Prefer stdlib fromisoformat (3.11+ handles Z)
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        from datetime import datetime

        return datetime.fromisoformat(s).timestamp()
    except Exception:
        return time.time() + 3600


def _redis_token_key(iid: str) -> str:
    return f"lumen:ghapp:install_token:{iid}"


def _redis_client():
    try:
        from lumen.platform.runtime_config import redis_url as _ru

        url = (_ru() or "").strip()
    except Exception:
        url = (os.getenv("REDIS_URL") or os.getenv("JOB_REDIS_URL") or "").strip()
    if not url:
        return None
    try:
        import redis

        r = connect_redis_url(
            url,
            decode_responses=True,
            socket_connect_timeout=float(os.getenv("REDIS_CONNECT_TIMEOUT") or "2"),
            socket_timeout=float(os.getenv("REDIS_SOCKET_TIMEOUT") or "3"),
        )
        r.ping()
        return r
    except Exception:
        return None


def get_installation_token(installation_id: int | str) -> str:
    """Cached installation access token (process + Redis, refresh ~60s early)."""
    iid = str(int(installation_id))
    now = time.time()
    with _lock:
        hit = _install_token_cache.get(iid)
        if hit and float(hit.get("expires_at") or 0) - _TOKEN_SKEW_SEC > now:
            return str(hit["token"])

    # Cross-worker cache (short TTL — never treat as durable secret store)
    r = _redis_client()
    if r is not None:
        try:
            raw = r.get(_redis_token_key(iid))
            if raw:
                data = json.loads(raw)
                exp = float(data.get("expires_at") or 0)
                tok = str(data.get("token") or "")
                if tok and exp - _TOKEN_SKEW_SEC > now:
                    with _lock:
                        _install_token_cache[iid] = {"token": tok, "expires_at": exp}
                    return tok
        except Exception:
            logger.debug("redis install token read failed install=%s", iid, exc_info=True)

    issued = create_installation_access_token(iid)
    exp = _parse_expires_at(str(issued.get("expires_at") or ""))
    tok = str(issued["token"])
    with _lock:
        _install_token_cache[iid] = {"token": tok, "expires_at": exp}
    if r is not None:
        try:
            ttl = max(30, int(exp - now - _TOKEN_SKEW_SEC))
            r.set(
                _redis_token_key(iid),
                json.dumps({"token": tok, "expires_at": exp}),
                ex=ttl,
            )
        except Exception:
            logger.debug("redis install token write failed install=%s", iid, exc_info=True)
    return tok


def clear_installation_token_cache(installation_id: int | str | None = None) -> None:
    with _lock:
        if installation_id is None:
            keys = list(_install_token_cache.keys())
            _install_token_cache.clear()
        else:
            keys = [str(int(installation_id))]
            _install_token_cache.pop(keys[0], None)
    r = _redis_client()
    if r is not None:
        for k in keys:
            try:
                r.delete(_redis_token_key(k))
            except Exception:
                pass


def get_installation(installation_id: int | str) -> dict[str, Any]:
    """GET /app/installations/{id} — account login, repo selection, etc."""
    import requests

    iid = str(int(installation_id))
    jwt = build_app_jwt()
    resp = requests.get(
        f"{_API}/app/installations/{iid}",
        headers=_app_headers(jwt),
        timeout=float(os.getenv("GITHUB_HTTP_TIMEOUT") or "30"),
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"github_app_install_{resp.status_code}:{resp.text[:400]}")
    return dict(resp.json() or {})


def list_installation_repos(
    installation_id: int | str,
    *,
    page: int = 1,
    per_page: int = 30,
) -> list[dict[str, Any]]:
    """GET /installation/repositories using an installation token."""
    import requests

    token = get_installation_token(installation_id)
    resp = requests.get(
        f"{_API}/installation/repositories",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Lumen-GitHub-App",
        },
        params={"page": max(1, int(page)), "per_page": max(1, min(100, int(per_page)))},
        timeout=float(os.getenv("GITHUB_HTTP_TIMEOUT") or "30"),
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"github_app_repos_{resp.status_code}:{resp.text[:400]}")
    data = resp.json() if resp.content else {}
    repos = data.get("repositories") if isinstance(data, dict) else data
    out: list[dict[str, Any]] = []
    for row in list(repos or []):
        if not isinstance(row, dict):
            continue
        out.append(
            {
                "id": row.get("id"),
                "full_name": row.get("full_name") or "",
                "name": row.get("name") or "",
                "private": bool(row.get("private")),
                "html_url": row.get("html_url") or "",
                "default_branch": row.get("default_branch") or "main",
                "language": row.get("language") or "",
            }
        )
    return out



def get_repo_installation(owner: str, repo: str) -> dict[str, Any]:
    """GET /repos/{owner}/{repo}/installation — requires App JWT."""
    import requests

    own = (owner or "").strip()
    name = (repo or "").strip()
    if not own or not name:
        raise ValueError("owner_repo_required")
    jwt = build_app_jwt()
    resp = requests.get(
        f"{_API}/repos/{own}/{name}/installation",
        headers=_app_headers(jwt),
        timeout=float(os.getenv("GITHUB_HTTP_TIMEOUT") or "30"),
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"github_repo_install_{resp.status_code}:{resp.text[:400]}")
    return dict(resp.json() or {})


def get_token_for_repo(owner: str, repo: str) -> str:
    """Installation access token with rights on this repository (App path)."""
    inst = get_repo_installation(owner, repo)
    iid = inst.get("id")
    if not iid:
        raise RuntimeError("github_repo_installation_id_missing")
    return get_installation_token(iid)


def install_url(*, state: str = "") -> str:
    """Public install URL for phase 2 Telegram deep-link."""
    slug = (os.getenv("GITHUB_APP_SLUG") or "").strip()
    if not slug:
        app_id = (os.getenv("GITHUB_APP_ID") or "").strip()
        if not app_id:
            raise RuntimeError("GITHUB_APP_SLUG or GITHUB_APP_ID required for install URL")
        base = f"https://github.com/apps/{app_id}/installations/new"
    else:
        base = f"https://github.com/apps/{slug}/installations/new"
    if state:
        from urllib.parse import urlencode

        return base + "?" + urlencode({"state": state})
    return base


def fingerprint_installation(installation_id: int | str) -> str:
    """Non-secret short id for logs / UI (never the access token)."""
    raw = f"install:{installation_id}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:12]


__all__ = [
    "github_app_configured",
    "build_app_jwt",
    "create_installation_access_token",
    "get_installation_token",
    "clear_installation_token_cache",
    "get_installation",
    "list_installation_repos",
    "get_repo_installation",
    "get_token_for_repo",
    "install_url",
    "fingerprint_installation",
]
