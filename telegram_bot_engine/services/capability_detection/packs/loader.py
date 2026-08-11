"""Load capability packs from disk and register into the live registry."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from ....spec_core.registry import CAPABILITIES, Capability
from .schema import CapabilityPack, PackCapability, validate_pack

logger = logging.getLogger("ai_agent_7h_bot.capability_packs")

# Track what overlay registered (for debugging / unload)
_OVERLAY_KEYS: set[str] = set()
_LOADED_PACKS: dict[str, CapabilityPack] = {}
_KEYWORD_INDEX: dict[str, list[str]] = {}  # keyword → capability keys


def _default_pack_dirs() -> list[Path]:
    roots: list[Path] = []
    # Ship-with-repo packs
    here = Path(__file__).resolve()
    roots.append(here.parents[3] / "spec_core" / "capability_packs")
    # Runtime overlay under OUTPUT_DIR
    out = os.getenv("OUTPUT_DIR") or "/tmp/generated"
    roots.append(Path(out) / "platform" / "capability_packs")
    # Explicit override
    extra = os.getenv("CAPABILITY_PACK_DIRS") or ""
    for part in extra.split(os.pathsep):
        part = part.strip()
        if part:
            roots.append(Path(part))
    return roots


def _to_capability(pc: PackCapability) -> Capability:
    return Capability(
        key=pc.key,
        service=pc.service,
        method=pc.method,
        description_ar=pc.description_ar,
        description_en=pc.description_en,
        default_actor=pc.default_actor or "user",
        permissions=tuple(pc.permissions or ()),
        needs_target_user=bool(pc.needs_target_user),
        category=pc.category or "general",
    )


def register_pack(
    pack: CapabilityPack,
    *,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Register pack capabilities into CAPABILITIES.

    By default does not overwrite built-in keys (safer).
    """
    errors = validate_pack(pack)
    if errors:
        return {"ok": False, "errors": errors, "registered": []}
    if not pack.enabled:
        return {"ok": True, "skipped": True, "reason": "disabled", "registered": []}

    registered: list[str] = []
    skipped: list[str] = []
    for pc in pack.capabilities:
        if not pc.key:
            continue
        exists = pc.key in CAPABILITIES
        if exists and not overwrite and pc.key not in _OVERLAY_KEYS:
            skipped.append(pc.key)
            continue
        CAPABILITIES[pc.key] = _to_capability(pc)
        _OVERLAY_KEYS.add(pc.key)
        registered.append(pc.key)
        for kw in pc.keywords:
            k = (kw or "").strip().lower()
            if not k:
                continue
            _KEYWORD_INDEX.setdefault(k, [])
            if pc.key not in _KEYWORD_INDEX[k]:
                _KEYWORD_INDEX[k].append(pc.key)

    _LOADED_PACKS[pack.id] = pack
    return {
        "ok": True,
        "pack_id": pack.id,
        "version": pack.version,
        "registered": registered,
        "skipped_existing": skipped,
    }


def load_pack_file(path: Path, *, overwrite: bool = False) -> dict[str, Any]:
    path = Path(path)
    if not path.is_file():
        return {"ok": False, "errors": [f"missing file: {path}"]}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"ok": False, "errors": [f"json error: {exc}"]}
    if not isinstance(data, dict):
        return {"ok": False, "errors": ["pack root must be object"]}
    pack = CapabilityPack.from_dict(data)
    result = register_pack(pack, overwrite=overwrite)
    result["path"] = str(path)
    return result


def load_all_packs(
    dirs: list[Path] | None = None,
    *,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Scan directories for *.json packs and register them."""
    dirs = dirs or _default_pack_dirs()
    loaded: list[dict[str, Any]] = []
    for d in dirs:
        d = Path(d)
        if not d.is_dir():
            continue
        for path in sorted(d.glob("*.json")):
            res = load_pack_file(path, overwrite=overwrite)
            loaded.append(res)
            if res.get("ok"):
                logger.info(
                    "capability pack loaded %s (%s keys)",
                    res.get("pack_id"),
                    len(res.get("registered") or []),
                )
            else:
                logger.warning("capability pack failed %s: %s", path, res.get("errors"))
    return {
        "ok": True,
        "packs": loaded,
        "overlay_keys": sorted(_OVERLAY_KEYS),
        "loaded_pack_ids": sorted(_LOADED_PACKS.keys()),
    }


def overlay_keys() -> set[str]:
    return set(_OVERLAY_KEYS)


def loaded_packs() -> dict[str, CapabilityPack]:
    return dict(_LOADED_PACKS)


def keyword_hits(text: str) -> list[str]:
    """Return capability keys matched via pack keywords."""
    t = (text or "").lower()
    if not t or not _KEYWORD_INDEX:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for kw, keys in _KEYWORD_INDEX.items():
        if kw and kw in t:
            for k in keys:
                if k not in seen:
                    seen.add(k)
                    out.append(k)
    return out


def ensure_packs_loaded() -> dict[str, Any]:
    """Idempotent load on first use."""
    if _LOADED_PACKS or os.getenv("CAPABILITY_PACKS_SKIP"):
        return {"ok": True, "already": True, "loaded_pack_ids": sorted(_LOADED_PACKS.keys())}
    return load_all_packs()


__all__ = [
    "register_pack",
    "load_pack_file",
    "load_all_packs",
    "overlay_keys",
    "loaded_packs",
    "keyword_hits",
    "ensure_packs_loaded",
]
