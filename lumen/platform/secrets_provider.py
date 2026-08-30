"""Process-memory secrets — root fix for .env / environ leakage.

ROOT SECURITY MODEL
-------------------
Managed secrets (bot tokens, LLM keys, Stripe, DB URLs, peppers…) are held in an
in-process dict only. In production they are NOT left in os.environ, so they do
not appear in /proc/self/environ dumps, accidental dict(os.environ) logging, or
naive /debug handlers.

Boot:
  1) load_dotenv_if_dev()     — filesystem .env NEVER in production
  2) load_secrets()           — Doppler → Vault → AWS SM → GCP SM → (dev) environ
  3) In production: copy managed keys into memory, then scrub them from os.environ
  4) Application code MUST use get_secret("NAME") for managed keys

Providers (production requires one unless SECRETS_ALLOW_PLATFORM_ENV=1):
  - Doppler, HashiCorp Vault, AWS Secrets Manager, GCP Secret Manager
"""
from __future__ import annotations

import json
import logging
import os
import threading
import urllib.parse
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

_MANAGED_KEYS = (
    "TELEGRAM_BOT_TOKEN",
    "GEMINI_API_KEY",
    "GEMINI_API_KEYS",
    "GROQ_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "XAI_API_KEY",
    "REDIS_URL",
    "JOB_REDIS_URL",
    "MONGODB_URI",
    "DATABASE_URL",
    "POSTGRES_URL",
    "API_KEY_PEPPER",
    "TBE_TOKEN_SECRET",
    "PLATFORM_ADMIN_TOKEN",
    "STRIPE_SECRET_KEY",
    "STRIPE_WEBHOOK_SECRET",
    "LANGCHAIN_API_KEY",
    "LANGSMITH_API_KEY",
)

_LOCK = threading.RLock()
# In-process secret store — never logged, never returned wholesale
_STORE: dict[str, str] = {}
_BOOTSTRAPPED = False


def _is_dev_environment() -> bool:
    try:
        from lumen.platform.tenants import _is_dev_environment as _tenants_dev
        return _tenants_dev()
    except Exception:  # noqa: BLE001
        markers = (
            "KUBERNETES_SERVICE_HOST", "K_SERVICE", "AWS_EXECUTION_ENV", "AWS_REGION",
            "RAILWAY_ENVIRONMENT", "RENDER_SERVICE_ID", "FLY_APP_NAME", "DYNO",
            "WEBSITE_INSTANCE_ID",
        )
        if any((os.getenv(m) or "").strip() for m in markers):
            return False
        if (os.getenv("FORCE_PRODUCTION") or "").strip().lower() in {"1", "true", "yes", "on"}:
            return False
        env = (os.getenv("ENVIRONMENT") or os.getenv("TBE_ENV") or "").strip().lower()
        return env in {"dev", "development", "local", "test"}


def is_production() -> bool:
    return not _is_dev_environment()


def _truthy(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _required() -> bool:
    raw = (os.getenv("SECRETS_REQUIRED") or "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return not _is_dev_environment()
    return not _is_dev_environment()


def _allow_platform_env_fallback() -> bool:
    if _is_dev_environment():
        return True
    return _truthy("SECRETS_ALLOW_PLATFORM_ENV")


def load_dotenv_if_dev() -> bool:
    """Filesystem .env is DEV ONLY. Always skipped in production."""
    if is_production():
        logger.info("secrets: dotenv disabled in production")
        return False
    try:
        from dotenv import load_dotenv
        from pathlib import Path
        root = Path(__file__).resolve().parents[2]
        load_dotenv(root / ".env", override=False)
        load_dotenv(override=False)
        logger.info("secrets: dotenv loaded (dev only)")
        return True
    except Exception as exc:
        logger.debug("secrets: dotenv skipped: %s", type(exc).__name__)
        return False


def _fetch_doppler() -> dict[str, str] | None:
    token = (os.getenv("DOPPLER_TOKEN") or "").strip()
    project = (os.getenv("DOPPLER_PROJECT") or "").strip()
    config = (os.getenv("DOPPLER_CONFIG") or "").strip()
    if not token or not project or not config:
        return None
    url = (
        "https://api.doppler.com/v3/configs/config/secrets/download"
        f"?format=json&project={urllib.parse.quote(project)}&config={urllib.parse.quote(config)}"
    )
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if not isinstance(data, dict):
            return None
        return {str(k): str(v) for k, v in data.items() if v is not None}
    except Exception as exc:
        logger.error("doppler_fetch_failed: %s", type(exc).__name__)
        return None


def _fetch_vault() -> dict[str, str] | None:
    addr = (os.getenv("VAULT_ADDR") or "").strip().rstrip("/")
    token = (os.getenv("VAULT_TOKEN") or "").strip()
    path = (os.getenv("VAULT_KV_PATH") or "secret/data/lumen").strip().lstrip("/")
    if not addr or not token:
        return None
    url = f"{addr}/v1/{path}"
    req = urllib.request.Request(
        url,
        headers={"X-Vault-Token": token, "Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        data = ((body or {}).get("data") or {}).get("data") or (body or {}).get("data") or {}
        if not isinstance(data, dict):
            return None
        return {str(k): str(v) for k, v in data.items() if v is not None}
    except Exception as exc:
        logger.error("vault_fetch_failed: %s", type(exc).__name__)
        return None


def _fetch_aws_secrets_manager() -> dict[str, str] | None:
    name = (os.getenv("AWS_SECRET_NAME") or "").strip()
    if not name:
        return None
    try:
        import boto3  # type: ignore
    except Exception:
        logger.error("aws_secrets_manager: boto3_not_installed")
        return None
    region = (os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-east-1").strip()
    try:
        client = boto3.client("secretsmanager", region_name=region)
        resp = client.get_secret_value(SecretId=name)
        raw = resp.get("SecretString") or ""
        if not raw and resp.get("SecretBinary"):
            raw = resp["SecretBinary"].decode("utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            return None
        return {str(k): str(v) for k, v in data.items() if v is not None}
    except Exception as exc:
        logger.error("aws_secrets_manager_failed: %s", type(exc).__name__)
        return None


def _fetch_gcp_secret_manager() -> dict[str, str] | None:
    name = (os.getenv("GCP_SECRET_NAME") or "").strip()
    if not name:
        return None
    try:
        from google.cloud import secretmanager  # type: ignore
    except Exception:
        logger.error("gcp_secret_manager: library_not_installed")
        return None
    project = (os.getenv("GCP_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT") or "").strip()
    if not project:
        return None
    if name.startswith("projects/"):
        resource = name
    else:
        version = (os.getenv("GCP_SECRET_VERSION") or "latest").strip()
        resource = f"projects/{project}/secrets/{name}/versions/{version}"
    try:
        client = secretmanager.SecretManagerServiceClient()
        resp = client.access_secret_version(request={"name": resource})
        data = json.loads(resp.payload.data.decode("utf-8"))
        if not isinstance(data, dict):
            return None
        return {str(k): str(v) for k, v in data.items() if v is not None}
    except Exception as exc:
        logger.error("gcp_secret_manager_failed: %s", type(exc).__name__)
        return None


def _provider_configured() -> list[str]:
    found: list[str] = []
    if (os.getenv("DOPPLER_TOKEN") or "").strip():
        found.append("doppler")
    if (os.getenv("VAULT_ADDR") or "").strip():
        found.append("vault")
    if (os.getenv("AWS_SECRET_NAME") or "").strip():
        found.append("aws")
    if (os.getenv("GCP_SECRET_NAME") or "").strip():
        found.append("gcp")
    return found


def _store_put(data: dict[str, str]) -> list[str]:
    """Write managed keys into process memory."""
    written: list[str] = []
    with _LOCK:
        for key in _MANAGED_KEYS:
            if key not in data:
                continue
            val = str(data[key] or "").strip()
            if not val:
                continue
            _STORE[key] = val
            written.append(key)
        if _truthy("SECRETS_INJECT_ALL"):
            for key, val in data.items():
                if key in _MANAGED_KEYS:
                    continue
                v = str(val or "").strip()
                if v:
                    _STORE[str(key)] = v
                    written.append(str(key))
    return written


def _scrub_environ(keys: list[str]) -> int:
    """Remove managed secrets from os.environ (production root mitigation)."""
    if _is_dev_environment() and not _truthy("SECRETS_SCRUB_ENV_IN_DEV"):
        return 0
    # Always scrub in production
    if not is_production() and not _truthy("SECRETS_SCRUB_ENV_IN_DEV"):
        return 0
    n = 0
    for key in keys:
        if key in os.environ:
            try:
                del os.environ[key]
                n += 1
            except Exception:
                pass
    # Also scrub any managed key still present from platform injection
    for key in _MANAGED_KEYS:
        if key in os.environ and key in _STORE:
            try:
                del os.environ[key]
                n += 1
            except Exception:
                pass
    return n


def get_secret(key: str, default: str = "") -> str:
    """Read a secret from process memory first, then (dev only) os.environ."""
    k = (key or "").strip()
    if not k:
        return default
    with _LOCK:
        if k in _STORE and _STORE[k]:
            return _STORE[k]
    # Production: do not fall back to environ for managed keys (already scrubbed).
    # Dev: allow environ / dotenv ergonomics.
    if k in _MANAGED_KEYS and is_production():
        return default
    return (os.getenv(k) or default).strip() or default


def require_secret(key: str) -> str:
    val = get_secret(key, "")
    if not val:
        raise RuntimeError(f"secret_missing:{key}")
    return val


def secret_names_present() -> list[str]:
    """Return names only (never values) — safe for diagnostics."""
    with _LOCK:
        return sorted(k for k, v in _STORE.items() if v)


def load_secrets(*, only_missing: bool = True) -> dict[str, Any]:
    """Load secrets into process memory; scrub os.environ in production.

    ``only_missing`` applies when merging into the in-memory store.
    """
    global _BOOTSTRAPPED
    meta: dict[str, Any] = {
        "source": "none",
        "stored": 0,
        "scrubbed_environ": 0,
        "keys": [],
        "production": is_production(),
    }

    remote: dict[str, str] | None = None
    source = "none"

    if (os.getenv("DOPPLER_TOKEN") or "").strip():
        remote = _fetch_doppler()
        if remote is not None:
            source = "doppler"
    if remote is None and (os.getenv("VAULT_ADDR") or "").strip():
        remote = _fetch_vault()
        if remote is not None:
            source = "vault"
    if remote is None and (os.getenv("AWS_SECRET_NAME") or "").strip():
        remote = _fetch_aws_secrets_manager()
        if remote is not None:
            source = "aws_secrets_manager"
    if remote is None and (os.getenv("GCP_SECRET_NAME") or "").strip():
        remote = _fetch_gcp_secret_manager()
        if remote is not None:
            source = "gcp_secret_manager"

    # Platform / existing environ snapshot for managed keys (before scrub)
    env_snapshot = {
        k: (os.environ.get(k) or "").strip()
        for k in _MANAGED_KEYS
        if (os.environ.get(k) or "").strip()
    }

    if remote is None:
        configured = _provider_configured()
        if is_production() and _required():
            if configured:
                raise RuntimeError(
                    "secrets_required_but_provider_failed:" + ",".join(configured)
                )
            if not _allow_platform_env_fallback():
                raise RuntimeError(
                    "secrets_provider_required_in_production:"
                    "set DOPPLER_* or VAULT_* or AWS_SECRET_NAME or GCP_SECRET_NAME "
                    "(or SECRETS_ALLOW_PLATFORM_ENV=1 if host injects secrets)"
                )
            source = "platform_env"
            remote = env_snapshot
        else:
            source = "env"
            remote = env_snapshot

    meta["source"] = source

    # Merge into store
    to_write = dict(remote or {})
    if only_missing:
        with _LOCK:
            to_write = {k: v for k, v in to_write.items() if k not in _STORE or not _STORE.get(k)}

    written = _store_put(to_write)
    # Ensure platform snapshot also lands if remote was partial
    if env_snapshot and source in {"doppler", "vault", "aws_secrets_manager", "gcp_secret_manager"}:
        # Prefer remote; fill gaps from platform snapshot into memory only
        gaps = {k: v for k, v in env_snapshot.items() if k not in (remote or {})}
        written += _store_put(gaps)

    meta["stored"] = len(written)
    meta["keys"] = list(dict.fromkeys(written))  # names only

    # ROOT FIX: strip managed secrets from process environment in production
    scrubbed = _scrub_environ(list(_MANAGED_KEYS))
    meta["scrubbed_environ"] = scrubbed
    _BOOTSTRAPPED = True

    logger.info(
        "secrets_provider source=%s stored=%s scrubbed_environ=%s keys=%s",
        meta["source"],
        meta["stored"],
        meta["scrubbed_environ"],
        ",".join(meta["keys"][:24]),
    )
    return meta


# Backward-compatible name used by main.py / api_main.py
def load_secrets_into_environ(*, only_missing: bool = True) -> dict[str, Any]:
    """Deprecated name — loads into MEMORY and scrubs environ in production."""
    return load_secrets(only_missing=only_missing)


def assert_critical_secrets_present() -> None:
    if not is_production() or not _required():
        return
    missing: list[str] = []
    hard = ["API_KEY_PEPPER", "TBE_TOKEN_SECRET"]
    if _truthy("ENABLE_API"):
        hard.append("REDIS_URL")
    for key in hard:
        if not get_secret(key):
            missing.append(key)
    if missing:
        raise RuntimeError("critical_secrets_missing:" + ",".join(missing))


def install_secret_access_bridge() -> None:
    """Route os.getenv / environ.get for managed keys through in-memory store.

    After production scrub, plain os.environ no longer holds secrets; this bridge
    keeps legitimate application reads working without re-exposing /proc/self/environ.
    """
    global _BOOTSTRAPPED
    import os as _os

    _orig_getenv = _os.getenv

    def _getenv(key, default=None):
        k = str(key) if key is not None else ""
        if k in _MANAGED_KEYS:
            with _LOCK:
                if k in _STORE and _STORE[k]:
                    return _STORE[k]
            if is_production():
                return default
        return _orig_getenv(key, default)

    _os.getenv = _getenv  # type: ignore[assignment]

    try:
        _orig_env_get = _os.environ.get

        def _env_get(key, default=None):
            k = str(key) if key is not None else ""
            if k in _MANAGED_KEYS:
                with _LOCK:
                    if k in _STORE and _STORE[k]:
                        return _STORE[k]
                if is_production():
                    return default
            return _orig_env_get(key, default)

        _os.environ.get = _env_get  # type: ignore[assignment]
    except Exception:
        logger.debug("secrets: could not patch os.environ.get")

    logger.info("secrets: access bridge installed (managed keys via memory)")
