"""Multi-tenant + white-label identity store."""
from __future__ import annotations

def _cm_default_output_dir() -> str:
    try:
        from lumen.platform.paths import default_output_dir
        return default_output_dir()
    except Exception:
        from pathlib import Path as _P
        p = _P.home() / '.lumen'
        p.mkdir(parents=True, exist_ok=True)
        return str(p)


import hashlib
import json
import os
import secrets
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .filelock import atomic_write_text, exclusive_lock


def _new_api_key(prefix: str = "sk_live") -> str:
    return f"{prefix}_{secrets.token_urlsafe(32)}"


def _production_signals_present() -> bool:
    """Heuristic: real deploy platforms set these — ENVIRONMENT=dev must not win."""
    markers = (
        "KUBERNETES_SERVICE_HOST",
        "K_SERVICE",  # Cloud Run
        "AWS_EXECUTION_ENV",
        "AWS_REGION",
        "RAILWAY_ENVIRONMENT",
        "RENDER_SERVICE_ID",
        "FLY_APP_NAME",
        "DYNO",  # Heroku
        "WEBSITE_INSTANCE_ID",  # Azure
    )
    for m in markers:
        if (os.getenv(m) or "").strip():
            return True
    # Explicit production force
    if (os.getenv("FORCE_PRODUCTION") or "").strip().lower() in {"1", "true", "yes", "on"}:
        return True
    return False


def _is_dev_environment() -> bool:
    """True only for explicit local/dev/test — never when deploy signals present.

    Prevents 'forgot to change ENVIRONMENT=dev' from opening hardcoded pepper
    on Railway/K8s/Render/Fly/etc.
    """
    if _production_signals_present():
        return False
    env = (os.getenv("ENVIRONMENT") or os.getenv("TBE_ENV") or "").strip().lower()
    return env in {"dev", "development", "local", "test"}


# Known-weak peppers — always rejected (even if set explicitly in env).
_WEAK_PEPPERS = frozenset({
    b"lumen_dev_only_pepper_change_me",
    b"change-me",
    b"changeme",
    b"secret",
    b"pepper",
    b"dev",
    b"test",
    b"password",
    b"123456",
})


def _pepper_is_strong(raw: bytes) -> bool:
    """Reject short / known-weak peppers (root auth hardening)."""
    if not raw or len(raw) < 32:
        return False
    if raw in _WEAK_PEPPERS:
        return False
    low = raw.lower()
    if low in _WEAK_PEPPERS:
        return False
    if low.startswith(b"change") or low.startswith(b"lumen_dev"):
        return False
    return True


def require_api_key_pepper() -> None:
    """Fail closed at process start if production lacks a strong API_KEY_PEPPER.

    Call from API create_app / worker boot. Unset ENVIRONMENT is production.
    """
    if _is_dev_environment():
        return
    for name in ("API_KEY_PEPPER", "PLATFORM_ADMIN_TOKEN", "TBE_TOKEN_SECRET"):
        v = (os.getenv(name) or "").strip()
        if v and _pepper_is_strong(v.encode("utf-8")):
            return
    raise RuntimeError(
        "Refusing to start: API_KEY_PEPPER is missing or too weak for production. "
        "Set API_KEY_PEPPER to a random secret >= 32 characters. "
        "Hardcoded / dev peppers are never accepted outside ENVIRONMENT=dev|local|test."
    )


def _dev_pepper_path() -> Path:
    """Local file that stores an auto-generated strong pepper for pure-dev runs."""
    base = Path(os.getenv("OUTPUT_DIR") or _cm_default_output_dir())
    return base / ".lumen_dev_pepper"


def _load_or_create_dev_pepper() -> bytes:
    """Generate a strong random pepper once and persist it (mode 0600).

    Used only when ENVIRONMENT is explicitly dev/local/test AND no env pepper
    is provided. Never used when production signals are present.
    """
    path = _dev_pepper_path()
    try:
        if path.is_file():
            data = path.read_bytes().strip()
            if _pepper_is_strong(data):
                return data
    except OSError:
        pass
    # Generate new strong pepper
    pepper = secrets.token_urlsafe(48).encode("utf-8")  # ~64 bytes
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(pepper)
        try:
            path.chmod(0o600)
        except OSError:
            pass
    except OSError as exc:
        raise RuntimeError(
            "Cannot create local dev pepper file. "
            "Set API_KEY_PEPPER explicitly or ensure OUTPUT_DIR is writable."
        ) from exc
    import logging
    logging.getLogger("lumen.platform.tenants").warning(
        "Generated and persisted a local dev API_KEY_PEPPER at %s (mode 0600). "
        "Set API_KEY_PEPPER in the environment for reproducible hashes across machines.",
        path,
    )
    return pepper


def _key_pepper() -> bytes:
    """Server-side pepper for API key hashes.

    Prefer dedicated API_KEY_PEPPER. Fall back to PLATFORM_ADMIN_TOKEN /
    TBE_TOKEN_SECRET so existing single-node deploys keep a non-empty pepper
    without a new secret.

    No hardcoded constant peppers remain. In pure dev (no production signals)
    a strong random pepper is generated once and stored locally with 0600 perms.
    Production / unset ENVIRONMENT must set a strong API_KEY_PEPPER (or equivalent).
    """
    for name in ("API_KEY_PEPPER", "PLATFORM_ADMIN_TOKEN", "TBE_TOKEN_SECRET"):
        v = (os.getenv(name) or "").strip()
        if not v:
            continue
        raw = v.encode("utf-8")
        if _pepper_is_strong(raw):
            return raw
        # FAIL-CLOSED: known-weak / short peppers are NEVER accepted, even in dev.
        # The only way a weak pepper can slip in is operator misconfiguration
        # (e.g. leaving ENVIRONMENT=dev on a real deploy). Reject unconditionally.
        raise RuntimeError(
            f"{name} is too weak or known-insecure (need >= 32 random chars, "
            "no hardcoded/dev/change-me values). Refusing to start regardless of "
            "ENVIRONMENT. Set API_KEY_PEPPER to `python -c \"import secrets;"
            "print(secrets.token_urlsafe(48))\"` output."
        )
    if _is_dev_environment():
        return _load_or_create_dev_pepper()
    raise RuntimeError(
        "API_KEY_PEPPER is required outside dev. "
        "Set API_KEY_PEPPER (preferred) or PLATFORM_ADMIN_TOKEN / TBE_TOKEN_SECRET. "
        "For local testing set ENVIRONMENT=dev|local|test."
    )


def _hash_key(raw: str) -> str:
    """HMAC-SHA256(api_key, pepper) — not plain SHA256.

    Plain SHA256 of API keys is offline-bruteforceable if the hash store leaks.
    HMAC with a server-side pepper binds hashes to this deployment.
    """
    import hmac
    return hmac.new(_key_pepper(), raw.encode("utf-8"), hashlib.sha256).hexdigest()


@dataclass
class Tenant:
    tenant_id: str
    name: str
    plan_id: str = "free"
    # White-label
    brand_name: str = ""
    brand_logo_url: str = ""
    primary_color: str = "#2563eb"
    support_email: str = ""
    custom_domain: str = ""
    # Auth
    api_key_hash: str = ""
    api_key_prefix: str = ""  # first 8 chars for display
    owner_telegram_id: int = 0
    # Status
    active: bool = True
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def public_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "name": self.name,
            "plan_id": self.plan_id,
            "brand_name": self.brand_name or self.name,
            "brand_logo_url": self.brand_logo_url,
            "primary_color": self.primary_color,
            "support_email": self.support_email,
            "custom_domain": self.custom_domain,
            "api_key_prefix": self.api_key_prefix,
            "active": self.active,
            "created_at": self.created_at,
            "white_label": bool(self.brand_name or self.custom_domain),
        }


class TenantStore:
    """File-backed tenant registry — **dev only**. Production must use MongoUserStore."""

    def __init__(self, root: str | Path | None = None) -> None:
        env = (os.getenv("ENVIRONMENT") or os.getenv("TBE_ENV") or "").strip().lower()
        if env not in {"dev", "development", "local", "test"}:
            raise RuntimeError(
                "File-backed TenantStore cannot be constructed outside ENVIRONMENT=dev|local|test. "
                "Use DATABASE_URL / PostgresTenantStore."
            )
        base = Path(root or os.getenv("OUTPUT_DIR") or _cm_default_output_dir())
        self.root = base / "platform" / "tenants"
        self.root.mkdir(parents=True, exist_ok=True)
        self.index_path = self.root / "index.json"
        self._by_id: dict[str, Tenant] = {}
        self._by_key_hash: dict[str, str] = {}
        self._load()

    def _ingest(self, data: dict) -> None:
        self._by_id = {}
        self._by_key_hash = {}
        for row in data.get("tenants", []):
            t = Tenant(**{k: v for k, v in row.items() if k in Tenant.__dataclass_fields__})
            self._by_id[t.tenant_id] = t
            if t.api_key_hash:
                self._by_key_hash[t.api_key_hash] = t.tenant_id

    def _load_unlocked(self) -> None:
        if not self.index_path.exists():
            self._by_id = {}
            self._by_key_hash = {}
            return
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
            self._ingest(data)
        except Exception:
            self._by_id = {}
            self._by_key_hash = {}

    def _load(self) -> None:
        try:
            with exclusive_lock(self.index_path):
                self._load_unlocked()
        except Exception:
            self._by_id = {}
            self._by_key_hash = {}

    def _save_unlocked(self) -> None:
        payload = {
            "tenants": [asdict(t) for t in self._by_id.values()],
            "updated_at": time.time(),
        }
        atomic_write_text(
            self.index_path,
            json.dumps(payload, ensure_ascii=False, indent=2),
        )

    def _save(self) -> None:
        with exclusive_lock(self.index_path):
            self._save_unlocked()

    def _mutate(self, fn):
        """Reload → apply fn → save under one exclusive lock (cross-process safe)."""
        with exclusive_lock(self.index_path):
            self._load_unlocked()
            result = fn()
            self._save_unlocked()
            return result

    def create(
        self,
        name: str,
        *,
        plan_id: str = "free",
        brand_name: str = "",
        owner_telegram_id: int = 0,
        **wl: Any,
    ) -> tuple[Tenant, str]:
        """Create tenant; returns (tenant, raw_api_key once)."""
        tid = f"ten_{secrets.token_hex(8)}"
        raw = _new_api_key()
        t = Tenant(
            tenant_id=tid,
            name=(name or "Tenant").strip()[:120],
            plan_id=_normalize_plan(plan_id),
            brand_name=(brand_name or name or "").strip()[:120],
            brand_logo_url=str(wl.get("brand_logo_url") or "")[:300],
            primary_color=str(wl.get("primary_color") or "#2563eb")[:20],
            support_email=str(wl.get("support_email") or "")[:120],
            custom_domain=str(wl.get("custom_domain") or "")[:200],
            api_key_hash=_hash_key(raw),
            api_key_prefix=raw[:12],
            owner_telegram_id=int(owner_telegram_id or 0),
        )
        def _do():
            self._by_id[tid] = t
            self._by_key_hash[t.api_key_hash] = tid
            return t, raw
        result = self._mutate(_do)
        # World-class onboarding: smart-trial promotional credits (idempotent)
        try:
            from lumen.platform.credits.onboarding import grant_welcome_credits
            grant_welcome_credits(tid)
        except Exception:
            pass
        return result

    def rotate_key(self, tenant_id: str) -> str | None:
        t = self._by_id.get(tenant_id)
        if not t:
            return None
        raw_box: dict = {}
        def _do():
            cur = self._by_id.get(tenant_id)
            if not cur:
                return None
            if cur.api_key_hash in self._by_key_hash:
                del self._by_key_hash[cur.api_key_hash]
            raw = _new_api_key()
            cur.api_key_hash = _hash_key(raw)
            cur.api_key_prefix = raw[:12]
            self._by_key_hash[cur.api_key_hash] = tenant_id
            raw_box["raw"] = raw
            return raw
        return self._mutate(_do)

    def authenticate(self, api_key: str) -> Tenant | None:
        if not api_key:
            return None
        key = api_key.strip()
        h = _hash_key(key)
        with exclusive_lock(self.index_path):
            self._load_unlocked()
            tid = self._by_key_hash.get(h)
            if not tid:
                return None
            t = self._by_id.get(tid)
            if not t or not t.active:
                return None
            return t

    def get(self, tenant_id: str) -> Tenant | None:
        with exclusive_lock(self.index_path):
            self._load_unlocked()
            return self._by_id.get(tenant_id)

    def update_white_label(self, tenant_id: str, **fields: Any) -> Tenant | None:
        """Brand/name fields only. Plan/active changes go through billing.apply_plan."""
        def _do():
            cur = self._by_id.get(tenant_id)
            if not cur:
                return None
            for k in (
                "brand_name",
                "brand_logo_url",
                "primary_color",
                "support_email",
                "custom_domain",
                "name",
            ):
                if k in fields and fields[k] is not None:
                    setattr(cur, k, str(fields[k])[:300])
            # Intentionally ignore plan_id / active / metadata / api_key from callers
            return cur
        return self._mutate(_do)

    def list_all(self) -> list[Tenant]:
        with exclusive_lock(self.index_path):
            self._load_unlocked()
            return list(self._by_id.values())

    def get_by_telegram(self, owner_telegram_id: int) -> Tenant | None:
        with exclusive_lock(self.index_path):
            self._load_unlocked()
            uid = int(owner_telegram_id or 0)
            for t in self._by_id.values():
                if int(t.owner_telegram_id or 0) == uid:
                    return t
            return None



def _normalize_plan(plan_id: str | None) -> str:
    try:
        from .mongo_users import normalize_plan_id
        return normalize_plan_id(plan_id)
    except Exception:
        key = (plan_id or "free").strip().lower()
        aliases = {
            "free": "free", "hobby": "free", "explorer": "free",
            "indie": "starter", "starter": "starter",
            "pro": "growth", "growth": "growth", "business": "growth",
            "unlimited": "growth", "enterprise": "growth",
        }
        return aliases.get(key, "free")


def set_plan(
    self,
    tenant_id: str,
    plan_id: str,
    *,
    metadata_updates: dict[str, Any] | None = None,
    active: bool = True,
) -> bool:
    """Update user plan (free|pro|unlimited). Used by billing."""
    def _do():
        cur = self._by_id.get(tenant_id)
        if not cur:
            return False
        meta = dict(cur.metadata or {})
        if metadata_updates:
            meta.update(metadata_updates)
        meta["last_plan_change"] = time.time()
        cur.metadata = meta
        cur.plan_id = _normalize_plan(plan_id)
        cur.active = bool(active)
        return True
    return bool(self._mutate(_do))


# Bind set_plan onto TenantStore class
TenantStore.set_plan = set_plan  # type: ignore[attr-defined]


_STORE = None


def _is_dev_env() -> bool:
    env = (os.getenv("ENVIRONMENT") or os.getenv("TBE_ENV") or "").strip().lower()
    return env in {"dev", "development", "local", "test"}


def get_tenant_store():  # -> TenantRepository
    """Return a TenantRepository.

    Production: PostgreSQL (PostgresTenantStore).
    Dev without DATABASE_URL: file TenantStore only.
    Callers must not depend on file locks or driver internals.
    """
    global _STORE
    if _STORE is not None:
        return _STORE
    from .runtime_config import database_url, is_dev, require_production_data_plane
    require_production_data_plane()
    pg = database_url()
    if pg:
        from .pg_store import PostgresTenantStore
        _STORE = PostgresTenantStore(pg)
        return _STORE
    if is_dev():
        import logging
        logging.getLogger(__name__).warning(
            "DEV ONLY: file TenantStore. Set DATABASE_URL for production parity."
        )
        _STORE = TenantStore()
        return _STORE
    raise RuntimeError("DATABASE_URL is required (PostgreSQL).")
