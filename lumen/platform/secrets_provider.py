"""Secrets provider — managed stores only in production.

Resolution order:
  1) Doppler           (DOPPLER_TOKEN + DOPPLER_PROJECT + DOPPLER_CONFIG)
  2) HashiCorp Vault   (VAULT_ADDR + VAULT_TOKEN + VAULT_KV_PATH)
  3) AWS Secrets Manager (AWS_SECRET_NAME, optional AWS_REGION) via boto3
  4) GCP Secret Manager  (GCP_SECRET_NAME, optional GCP_PROJECT) via google-cloud-secret-manager
  5) Platform-injected environ (Railway/Render/K8s) — ONLY if SECRETS_ALLOW_PLATFORM_ENV=1
     or ENVIRONMENT is dev/local/test

Hard rules:
  - Never load a filesystem .env in production (callers must use load_dotenv_if_dev).
  - Production fail-closed: a managed provider MUST succeed unless
    SECRETS_ALLOW_PLATFORM_ENV=1 is set explicitly.
  - Never log secret values.
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
    "STRIPE_WEBHOOK_SECRET",
    "LANGCHAIN_API_KEY",
    "LANGSMITH_API_KEY",
)


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
    """Fail-closed secrets policy for production."""
    raw = (os.getenv("SECRETS_REQUIRED") or "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        # Only honored in verified dev — ignored on real deploy platforms.
        return not _is_dev_environment()
    return not _is_dev_environment()


def _allow_platform_env_fallback() -> bool:
    """Platform-injected env (not .env file) allowed only when explicit or dev."""
    if _is_dev_environment():
        return True
    return _truthy("SECRETS_ALLOW_PLATFORM_ENV")


def load_dotenv_if_dev() -> bool:
    """Load filesystem .env ONLY in dev/local/test. Always no-op in production.

    Returns True if dotenv was applied.
    """
    if is_production():
        logger.info("secrets: dotenv disabled in production (use Doppler/Vault/AWS/GCP)")
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
    """Optional AWS Secrets Manager (requires boto3). Secret string = JSON object."""
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
            logger.error("aws_secrets_manager: secret_not_json_object")
            return None
        return {str(k): str(v) for k, v in data.items() if v is not None}
    except Exception as exc:
        logger.error("aws_secrets_manager_failed: %s", type(exc).__name__)
        return None


def _fetch_gcp_secret_manager() -> dict[str, str] | None:
    """Optional GCP Secret Manager. Payload must be JSON object of key/value secrets."""
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
        logger.error("gcp_secret_manager: GCP_PROJECT missing")
        return None
    # Accept short name or full resource path
    if name.startswith("projects/"):
        resource = name
    else:
        version = (os.getenv("GCP_SECRET_VERSION") or "latest").strip()
        resource = f"projects/{project}/secrets/{name}/versions/{version}"
    try:
        client = secretmanager.SecretManagerServiceClient()
        resp = client.access_secret_version(request={"name": resource})
        raw = resp.payload.data.decode("utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            logger.error("gcp_secret_manager: secret_not_json_object")
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


def load_secrets_into_environ(*, only_missing: bool = True) -> dict[str, Any]:
    """Fetch from managed providers and inject into os.environ.

    Production: requires a successful managed provider response unless
    SECRETS_ALLOW_PLATFORM_ENV=1 (explicit escape for K8s/Railway secret injection).
    Never reads filesystem .env (use load_dotenv_if_dev before this in entrypoints).
    """
    meta: dict[str, Any] = {
        "source": "none",
        "injected": 0,
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

    meta["source"] = source

    if remote is None:
        configured = _provider_configured()
        if is_production() and _required():
            if configured:
                raise RuntimeError(
                    "secrets_required_but_provider_failed:"
                    + ",".join(configured)
                )
            if not _allow_platform_env_fallback():
                raise RuntimeError(
                    "secrets_provider_required_in_production:"
                    "set DOPPLER_* or VAULT_* or AWS_SECRET_NAME or GCP_SECRET_NAME "
                    "(or SECRETS_ALLOW_PLATFORM_ENV=1 only if the host injects secrets)"
                )
            meta["source"] = "platform_env"
            logger.warning(
                "secrets: production using platform-injected environ "
                "(SECRETS_ALLOW_PLATFORM_ENV=1) — prefer Doppler/Vault/AWS/GCP"
            )
            return meta
        meta["source"] = "env" if _is_dev_environment() else "platform_env"
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

    if _truthy("SECRETS_INJECT_ALL"):
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
    # Log key NAMES only — never values
    logger.info(
        "secrets_provider source=%s injected=%s keys=%s",
        meta["source"],
        injected,
        ",".join(keys[:24]),
    )
    return meta


def assert_critical_secrets_present() -> None:
    """Fail boot if mandatory secrets are empty in production."""
    if not is_production() or not _required():
        return
    missing: list[str] = []
    # Token may be bot-only or api-only deploy — check soft
    soft = {"TELEGRAM_BOT_TOKEN", "STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET"}
    hard = {
        "API_KEY_PEPPER",
        "TBE_TOKEN_SECRET",
        "REDIS_URL",
    }
    for key in hard:
        if not (os.getenv(key) or "").strip():
            # REDIS may be optional if API off — still recommended
            if key == "REDIS_URL" and not _truthy("ENABLE_API"):
                continue
            missing.append(key)
    if missing:
        raise RuntimeError("critical_secrets_missing:" + ",".join(missing))
