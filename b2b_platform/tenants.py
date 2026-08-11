"""Multi-tenant + white-label identity store."""
from __future__ import annotations

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


def _hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


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
    """File-backed tenant registry (swap to Postgres later without API changes)."""

    def __init__(self, root: str | Path | None = None) -> None:
        base = Path(root or os.getenv("OUTPUT_DIR", "/tmp/generated"))
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
            plan_id=(plan_id or "free").lower(),
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
        return self._mutate(_do)

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
        h = _hash_key(api_key.strip())
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


_STORE: TenantStore | None = None


def get_tenant_store() -> TenantStore:
    global _STORE
    if _STORE is None:
        _STORE = TenantStore()
    return _STORE
