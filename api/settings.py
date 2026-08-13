"""Central API / platform settings — Pydantic foundation.

All security-sensitive and operational knobs for the B2B API surface are
declared here. Callers should prefer `get_settings()` over scattered
`os.getenv` so misconfiguration fails fast at startup.
"""
from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class APISettings(BaseSettings):
    """Validated environment for the B2B API and shared platform services."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── Surface exposure ──────────────────────────────────────────────
    enable_api: bool = Field(default=False, alias="ENABLE_API")
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8080, alias="API_PORT")
    api_client_max_size: int = Field(default=262144, alias="API_CLIENT_MAX_SIZE")

    # ── CORS ──────────────────────────────────────────────────────────
    api_cors_origin: str = Field(default="", alias="API_CORS_ORIGIN")
    api_cors_allow_wildcard: bool = Field(default=False, alias="API_CORS_ALLOW_WILDCARD")

    # ── Rate limits ───────────────────────────────────────────────────
    redis_url: str = Field(default="", alias="REDIS_URL")
    api_ip_rpm: int = Field(default=120, alias="API_IP_RPM")
    api_tenant_create_rpm: int = Field(default=5, alias="API_TENANT_CREATE_RPM")
    generate_rpm: int = Field(default=10, alias="GENERATE_RPM")
    generate_max_description_chars: int = Field(default=20000, alias="GENERATE_MAX_DESCRIPTION_CHARS")
    generate_max_body_bytes: int = Field(default=65536, alias="GENERATE_MAX_BODY_BYTES")

    # ── Isolation ─────────────────────────────────────────────────────
    tbe_multi_tenant: bool = Field(default=True, alias="TBE_MULTI_TENANT")
    tbe_require_docker: bool = Field(default=True, alias="TBE_REQUIRE_DOCKER")
    tbe_allow_local_process: bool = Field(default=False, alias="TBE_ALLOW_LOCAL_PROCESS")
    tbe_docker_network: str = Field(default="", alias="TBE_DOCKER_NETWORK")
    output_dir: str = Field(default="/tmp/generated", alias="OUTPUT_DIR")

    # ── Trusted proxies (for real client IP) ──────────────────────────
    trusted_proxy_ips: str = Field(default="", alias="TRUSTED_PROXY_IPS")

    # ── Admin / secrets presence (not values logged) ──────────────────
    platform_admin_token: str = Field(default="", alias="PLATFORM_ADMIN_TOKEN")

    @field_validator(
        "enable_api",
        "api_cors_allow_wildcard",
        "tbe_multi_tenant",
        "tbe_require_docker",
        "tbe_allow_local_process",
        mode="before",
    )
    @classmethod
    def _parse_bool(cls, v):  # noqa: ANN001
        if isinstance(v, bool):
            return v
        if v is None or v == "":
            return False
        return str(v).strip().lower() in {"1", "true", "yes", "on"}

    def cors_allowed_origins(self) -> List[str]:
        raw = (self.api_cors_origin or "").strip()
        if not raw or raw == "*":
            return []
        return [o.strip() for o in raw.split(",") if o.strip()]

    def cors_allows_wildcard(self) -> bool:
        raw = (self.api_cors_origin or "").strip()
        return raw == "*" and self.api_cors_allow_wildcard


@lru_cache(maxsize=1)
def get_settings() -> APISettings:
    """Singleton settings instance (cached)."""
    return APISettings()
