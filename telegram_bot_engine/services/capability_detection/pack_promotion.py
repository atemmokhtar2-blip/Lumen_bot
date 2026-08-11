"""Phase 7 — Pack Promotion (hardened).

draft/learned → emit-safe install → registry + extractor + verify.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any

from .learning_loop import list_draft_packs, load_learned_kb
from .packs.emit_contract import assess_capability, assess_pack_capabilities
from .packs.loader import load_all_packs, register_pack
from .packs.schema import CapabilityPack, PackCapability, validate_pack


_SAFE_SERVICES = frozenset({
    "generic", "content", "utils", "core", "shop", "reminders", "notes", "tasks",
    "translate", "ocr", "scheduler",
})
_SAFE_METHODS = frozenset({
    "echo", "announce", "start", "help", "rules", "faq", "about",
    "translate", "translate_toggle", "ocr_image", "ocr_hint",
    "schedule_note", "job_list", "job_cancel",
})


def _packs_install_dir() -> Path:
    base = os.getenv("OUTPUT_DIR") or "/tmp/generated"
    p = Path(base) / "platform" / "capability_packs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _safe_filename(pack_id: str) -> str:
    raw = (pack_id or "pack").strip()
    ascii_part = re.sub(r"[^a-zA-Z0-9_\-]+", "", raw)[:40]
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]
    if ascii_part:
        return f"{ascii_part}_{digest}"
    return f"pack_{digest}"


def _force_safe_capability(c: PackCapability) -> PackCapability:
    svc = c.service if c.service in _SAFE_SERVICES else "generic"
    meth = c.method if c.method in _SAFE_METHODS else "echo"
    # still verify
    a = assess_capability(c.key, svc, meth)
    if not a.safe:
        svc, meth = "generic", "echo"
    kws = list(dict.fromkeys(
        [str(k).strip() for k in (c.keywords or []) if str(k).strip()]
        + [c.key.replace("_", " ")]
        + [c.description_ar[:40] if c.description_ar else ""]
    ))
    kws = [k for k in kws if len(k) >= 2][:16]
    return PackCapability(
        key=c.key if re.match(r"^[a-z][a-z0-9_]*$", c.key or "") else (
            "pack_" + hashlib.sha1((c.key or "x").encode()).hexdigest()[:12]
        ),
        service=svc,
        method=meth,
        description_ar=(c.description_ar or c.key or "قدرة")[:200],
        description_en=(c.description_en or c.description_ar or c.key or "capability")[:200],
        category=c.category if c.category and c.category != "general" else "utils",
        default_actor=c.default_actor or "user",
        keywords=kws,
        dependencies=list(c.dependencies or []),
    )


def verify_installed(keys: list[str]) -> dict[str, Any]:
    """Confirm keys live in registry + extractor patterns + command map."""
    from ...spec_core.registry import get_capability
    from ...spec_core import capability_extractor as ce
    try:
        from ...spec_core.builder import DEFAULT_COMMANDS
    except Exception:
        DEFAULT_COMMANDS = {}

    details = []
    ok_all = True
    for key in keys:
        cap = get_capability(key)
        in_patterns = isinstance(getattr(ce, "_PATTERNS", None), dict) and key in ce._PATTERNS
        in_cmds = key in DEFAULT_COMMANDS if isinstance(DEFAULT_COMMANDS, dict) else False
        row = {
            "key": key,
            "in_registry": cap is not None,
            "in_extractor": bool(in_patterns),
            "in_commands": bool(in_cmds),
            "service": getattr(cap, "service", None),
            "method": getattr(cap, "method", None),
        }
        if not (row["in_registry"] and row["in_extractor"]):
            ok_all = False
        details.append(row)
    return {"ok": ok_all, "keys": details}


def install_pack(
    pack: CapabilityPack,
    *,
    require_safe_emit: bool = True,
    overwrite: bool = False,
    sanitize: bool = True,
) -> dict[str, Any]:
    """Validate, sanitize to emit-safe, register, persist, verify."""
    errors = validate_pack(pack)
    if errors:
        return {"ok": False, "errors": errors}

    original_assessments = assess_pack_capabilities(pack.capabilities)
    sanitized = False
    if sanitize:
        pack.capabilities = [_force_safe_capability(c) for c in pack.capabilities]
        sanitized = True
        # re-validate keys after sanitize
        errors = validate_pack(pack)
        if errors:
            return {"ok": False, "errors": errors, "sanitized": True}

    assessments = assess_pack_capabilities(pack.capabilities)
    if require_safe_emit:
        unsafe = [a for a in assessments if not a.safe]
        if unsafe:
            return {
                "ok": False,
                "errors": [f"{a.key}: {a.level} — {', '.join(a.notes)}" for a in unsafe],
                "emit_assessments": [a.to_dict() for a in assessments],
            }

    pack.enabled = True
    if not pack.source or pack.source == "local":
        pack.source = "promoted"

    reg = register_pack(pack, overwrite=overwrite)
    if not reg.get("ok"):
        return reg

    dest = _packs_install_dir() / f"{_safe_filename(pack.id)}.json"
    payload = pack.to_dict()
    payload["promoted_at"] = time.time()
    payload["sanitized"] = sanitized
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    registered = list(reg.get("registered") or [])
    verification = verify_installed(registered)

    return {
        "ok": True,
        "pack_id": pack.id,
        "registered": registered,
        "path": str(dest),
        "sanitized": sanitized,
        "emit_assessments": [a.to_dict() for a in assessments],
        "original_emit_assessments": [a.to_dict() for a in original_assessments],
        "verification": verification,
    }


def promote_draft_file(
    path: str | Path,
    *,
    require_safe_emit: bool = True,
    overwrite: bool = True,
) -> dict[str, Any]:
    path = Path(path)
    if not path.is_file():
        return {"ok": False, "errors": [f"missing: {path}"]}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"ok": False, "errors": [f"json: {exc}"]}
    pack = CapabilityPack.from_dict(data)
    result = install_pack(
        pack, require_safe_emit=require_safe_emit, overwrite=overwrite, sanitize=True
    )
    if result.get("ok"):
        result["source_draft"] = str(path)
    return result


def promote_latest_drafts(
    *,
    limit: int = 5,
    require_safe_emit: bool = True,
) -> dict[str, Any]:
    installed: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for item in list_draft_packs()[:limit]:
        res = promote_draft_file(
            item["path"], require_safe_emit=require_safe_emit, overwrite=True
        )
        (installed if res.get("ok") else failed).append(
            res if res.get("ok") else {"path": item["path"], "result": res}
        )
    return {
        "ok": True,
        "installed": len(installed),
        "failed": len(failed),
        "items": installed,
        "failed_items": failed,
    }


def promote_learned_entry(
    entry_id: str,
    *,
    require_safe_emit: bool = True,
) -> dict[str, Any]:
    entries = {e.id: e for e in load_learned_kb()}
    entry = entries.get(entry_id)
    if not entry:
        draft = _learning_dir_draft(entry_id)
        if draft:
            return promote_draft_file(draft, require_safe_emit=require_safe_emit)
        return {"ok": False, "errors": [f"unknown entry: {entry_id}"]}

    digest = hashlib.sha1(entry_id.encode("utf-8")).hexdigest()[:12]
    key = f"pack_learned_{digest}"

    # Rich bilingual descriptions
    desc_ar = (entry.title or entry.phrases[0] if entry.phrases else key)[:200]
    desc_en = (entry.summary or entry.title or "Learned capability")[:200]
    if len(desc_en) < 8:
        desc_en = f"Learned capability: {desc_ar}"[:200]

    keywords = list(dict.fromkeys(
        list(entry.keywords or [])
        + list(entry.phrases or [])
        + [desc_ar]
    ))
    keywords = [k for k in keywords if len(str(k).strip()) >= 2][:16]

    svc = entry.suggested_service if entry.suggested_service in _SAFE_SERVICES else "generic"
    meth = entry.suggested_method if entry.suggested_method in _SAFE_METHODS else "echo"

    cap = PackCapability(
        key=key,
        service=svc,
        method=meth,
        description_ar=desc_ar,
        description_en=desc_en,
        category="utils",
        keywords=keywords,
    )
    pack = CapabilityPack(
        id=f"promoted_{digest}",
        version="1.0.0",
        name=desc_ar,
        description=desc_en,
        capabilities=[cap],
        source="learning_promoted",
        enabled=True,
    )
    result = install_pack(pack, require_safe_emit=require_safe_emit, overwrite=True, sanitize=True)
    if result.get("ok"):
        try:
            from .gap_journal import mark_gap_status, list_open_gaps
            for g in list_open_gaps(limit=50):
                if g.phrase in (entry.phrases or []) or g.phrase == entry.title:
                    mark_gap_status(g.phrase, g.reason, "resolved")
        except Exception:
            pass
    return result


def _learning_dir_draft(entry_id: str) -> Path | None:
    base = os.getenv("OUTPUT_DIR") or "/tmp/generated"
    p = Path(base) / "platform" / "learning" / f"draft_{entry_id}.json"
    return p if p.is_file() else None


def promotion_status() -> dict[str, Any]:
    install_dir = _packs_install_dir()
    installed = list(install_dir.glob("*.json"))
    return {
        "install_dir": str(install_dir),
        "installed_packs": len(installed),
        "drafts": len(list_draft_packs()),
        "learned_entries": len(load_learned_kb()),
        "installed_files": [p.name for p in installed[:30]],
    }


def auto_promote_ready(
    *,
    min_hit_count: int = 2,
    limit: int = 3,
) -> dict[str, Any]:
    """Promote learned entries that look ready (hit_count threshold).

    Env gate: CAPABILITY_AUTO_PROMOTE=1
    """
    enabled = os.getenv("CAPABILITY_AUTO_PROMOTE", "0").strip().lower() in {
        "1", "true", "yes",
    }
    if not enabled:
        return {"ok": True, "skipped": True, "reason": "auto_promote_disabled"}

    promoted: list[dict[str, Any]] = []
    for entry in load_learned_kb():
        if entry.status != "active":
            continue
        if entry.hit_count < min_hit_count:
            continue
        res = promote_learned_entry(entry.id, require_safe_emit=True)
        if res.get("ok"):
            promoted.append(res)
        if len(promoted) >= limit:
            break
    return {
        "ok": True,
        "promoted": len(promoted),
        "items": promoted,
    }


__all__ = [
    "install_pack",
    "promote_draft_file",
    "promote_latest_drafts",
    "promote_learned_entry",
    "promotion_status",
    "verify_installed",
    "auto_promote_ready",
]
