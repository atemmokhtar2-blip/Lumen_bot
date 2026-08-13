"""Capability Pack schema — expandable registry units (Phase 4).

Packs are pure data. They never embed executable code blobs.
Codegen continues to use deterministic emitters keyed by service/method.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class PackCapability:
    key: str
    service: str
    method: str
    description_ar: str
    description_en: str
    category: str = "general"
    default_actor: str = "user"
    permissions: list[str] = field(default_factory=list)
    needs_target_user: bool = False
    keywords: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PackCapability":
        return cls(
            key=str(data.get("key") or "").strip().lower(),
            service=str(data.get("service") or "").strip().lower(),
            method=str(data.get("method") or "").strip().lower(),
            description_ar=str(data.get("description_ar") or data.get("ar") or ""),
            description_en=str(data.get("description_en") or data.get("en") or ""),
            category=str(data.get("category") or "general").strip().lower(),
            default_actor=str(data.get("default_actor") or "user").strip().lower(),
            permissions=[str(p) for p in (data.get("permissions") or [])],
            needs_target_user=bool(data.get("needs_target_user") or False),
            keywords=[str(k) for k in (data.get("keywords") or [])],
            dependencies=[str(d).strip().lower() for d in (data.get("dependencies") or [])],
        )


@dataclass
class CapabilityPack:
    id: str
    version: str = "1.0.0"
    name: str = ""
    description: str = ""
    capabilities: list[PackCapability] = field(default_factory=list)
    source: str = "local"  # local | research | manual
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "version": self.version,
            "name": self.name,
            "description": self.description,
            "source": self.source,
            "enabled": self.enabled,
            "capabilities": [c.to_dict() for c in self.capabilities],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CapabilityPack":
        caps = [
            PackCapability.from_dict(c)
            for c in (data.get("capabilities") or [])
            if isinstance(c, dict)
        ]
        return cls(
            id=str(data.get("id") or data.get("pack_id") or "unnamed").strip(),
            version=str(data.get("version") or "1.0.0"),
            name=str(data.get("name") or ""),
            description=str(data.get("description") or ""),
            capabilities=caps,
            source=str(data.get("source") or "local"),
            enabled=bool(data.get("enabled", True)),
        )


def validate_pack(pack: CapabilityPack) -> list[str]:
    """Return list of structural errors (empty = ok)."""
    errors: list[str] = []
    if not pack.id:
        errors.append("pack.id required")
    seen: set[str] = set()
    for c in pack.capabilities:
        if not c.key or not c.service or not c.method:
            errors.append(f"incomplete capability in pack {pack.id}: {c.key!r}")
            continue
        if c.key in seen:
            errors.append(f"duplicate key in pack {pack.id}: {c.key}")
        seen.add(c.key)
        if not c.description_ar or not c.description_en:
            errors.append(f"missing descriptions on {c.key}")
    return errors


__all__ = [
    "PackCapability",
    "CapabilityPack",
    "validate_pack",
]
