"""Dynamic secrets provider — Doppler / HashiCorp Vault preferred over static .env.

Resolution order at process boot (inject into os.environ only if key missing):
  1) Doppler API  (DOPPLER_TOKEN + DOPPLER_PROJECT + DOPPLER_CONFIG)
  2) Vault KV v2  (VAULT_ADDR + VAULT_TOKEN + VAULT_KV_PATH)
  3) Existing environment (Railway / .env) — last resort

Never logs secret values. Fail-open in dev; fail-closed when SECRETS_REQUIRED=1.
"""
from __future__ import annotations

import json
import logging
import os
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
    "LANGCHAIN_API_KEY",
    "LANGSMITH_API_KEY",
)


def _is_dev_environment() -> bool:
    """Reuse the canonical production detection from the tenants module.

    Falls back to an inline heuristic if the import fails (e.g. unit-test
    isolation). Never invents a weaker check.
    """
    try:
        from lumen.platform.tenants import _is_dev_environment as _tenants_dev
        return _tenants_dev()
    except Exception:  # noqa: BLE001 — keep fail-closed semantics in isolation
        # Inline mirror of lumen.platform.tenants._production_signals_present
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


def _required() -> bool:
    """Whether secrets must be present at boot.

    SECURITY (Vuln #6): fail-closed by default in production. ``SECRETS_REQUIRED=0``
    is ONLY honored in a verified dev/local/test environment — it is silently
    ignored on real deploy platforms (K8s/Railway/Render/Fly/etc.) so that a
    stale ``ENVIRONMENT=dev`` cannot disable secret enforcement in prod.
    """
    raw = (os.getenv("SECRETS_REQUIRED") or "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        # Only honored in dev — production always fail-closed regardless.
        return not _is_dev_environment()
    # Unset: fail-closed in production, fail-open in dev (for local ergonomics).
    return not _is_dev_environment()


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


def load_secrets_into_environ(*, only_missing: bool = True) -> dict[str, Any]:
    """Fetch from Doppler/Vault and inject managed keys into os.environ."""
    meta: dict[str, Any] = {"source": "env", "injected": 0, "keys": []}
    remote: dict[str, str] | None = None
    if (os.getenv("DOPPLER_TOKEN") or "").strip():
        remote = _fetch_doppler()
        if remote is not None:
            meta["source"] = "doppler"
    if remote is None and (os.getenv("VAULT_ADDR") or "").strip():
        remote = _fetch_vault()
        if remote is not None:
            meta["source"] = "vault"

    if remote is None:
        if _required() and (
            (os.getenv("DOPPLER_TOKEN") or "").strip()
            or (os.getenv("VAULT_ADDR") or "").strip()
        ):
            raise RuntimeError("secrets_required_but_provider_failed")
        return meta

    injected = 0
    keys: list[str] = []
    for key in _MANAGED_KEYS:
        if key not in remote:
            continue
        if only_missing and (os.environ.get(key) or "").strip():
            continue
        os.environ[key] = remote[key]
        injected += 1
        keys.append(key)
    if (os.getenv("SECRETS_INJECT_ALL") or "").strip().lower() in {"1", "true", "yes", "on"}:
        for key, val in remote.items():
            if only_missing and (os.environ.get(key) or "").strip():
                continue
            if key in keys:
                continue
            os.environ[str(key)] = str(val)
            injected += 1
            keys.append(str(key))
    meta["injected"] = injected
    meta["keys"] = keys
    logger.info(
        "secrets_provider source=%s injected=%s keys=%s",
        meta["source"],
        injected,
        ",".join(keys[:20]),
    )
    return meta
