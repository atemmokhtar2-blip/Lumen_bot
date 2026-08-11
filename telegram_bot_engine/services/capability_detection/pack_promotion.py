"""Phase 7 — Pack Promotion: draft → installed capability pack (emit-safe only).

Closes the loop: Gap → Research → Learn → Draft → **Promote** → Registry → Generate.
Never installs packs that fail the emit contract.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

from .learning_loop import list_draft_packs, load_learned_kb
from .packs.emit_contract import assess_pack_capabilities
from .packs.loader import load_pack_file, register_pack
from .packs.pipeline import approve_and_register
from .packs.schema import CapabilityPack, PackCapability, validate_pack


def _packs_install_dir() -> Path:
    """Runtime-writable pack dir (also scanned by load_all_packs)."""
    base = os.getenv("OUTPUT_DIR") or "/tmp/generated"
    p = Path(base) / "platform" / "capability_packs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _repo_packs_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "spec_core" / "capability_packs"


def _safe_filename(pack_id: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_\-]+", "_", (pack_id or "pack").strip())
    return (s or "pack")[:64]


def install_pack(
    pack: CapabilityPack,
    *,
    require_safe_emit: bool = True,
    overwrite: bool = False,
    write_repo_copy: bool = False,
) -> dict[str, Any]:
    """Validate, emit-assess, register, and persist pack JSON to install dir."""
    errors = validate_pack(pack)
    if errors:
        return {"ok": False, "errors": errors}

    assessments = assess_pack_capabilities(pack.capabilities)
    if require_safe_emit:
        unsafe = [a for a in assessments if not a.safe]
        if unsafe:
            return {
                "ok": False,
                "errors": [f"{a.key}: {a.level} — {', '.join(a.notes)}" for a in unsafe],
                "emit_assessments": [a.to_dict() for a in assessments],
            }

    # Force enabled
    pack.enabled = True
    pack.source = pack.source or "promoted"

    reg = register_pack(pack, overwrite=overwrite)
    if not reg.get("ok"):
        return reg

    # Persist for future process loads
    dest = _packs_install_dir() / f"{_safe_filename(pack.id)}.json"
    payload = pack.to_dict()
    payload["promoted_at"] = time.time()
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    repo_path = None
    if write_repo_copy:
        try:
            rp = _repo_packs_dir()
            rp.mkdir(parents=True, exist_ok=True)
            repo_path = rp / f"{_safe_filename(pack.id)}.json"
            repo_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            repo_path = None

    return {
        "ok": True,
        "pack_id": pack.id,
        "registered": reg.get("registered"),
        "path": str(dest),
        "repo_path": str(repo_path) if repo_path else None,
        "emit_assessments": [a.to_dict() for a in assessments],
    }


def promote_draft_file(
    path: str | Path,
    *,
    require_safe_emit: bool = True,
    overwrite: bool = True,
) -> dict[str, Any]:
    """Load a draft_*.json pack and install it."""
    path = Path(path)
    if not path.is_file():
        return {"ok": False, "errors": [f"missing: {path}"]}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"ok": False, "errors": [f"json: {exc}"]}
    pack = CapabilityPack.from_dict(data)
    # Prefer generic.echo if unsafe
    result = install_pack(pack, require_safe_emit=require_safe_emit, overwrite=overwrite)
    if not result.get("ok") and require_safe_emit:
        # rewrite capabilities to safe echo and retry once
        safe_caps = []
        for c in pack.capabilities:
            safe_caps.append(
                PackCapability(
                    key=c.key,
                    service="generic",
                    method="echo",
                    description_ar=c.description_ar or c.key,
                    description_en=c.description_en or c.key,
                    category=c.category or "utils",
                    default_actor=c.default_actor or "user",
                    keywords=list(c.keywords or []),
                    dependencies=list(c.dependencies or []),
                )
            )
        pack.capabilities = safe_caps
        pack.id = (pack.id or "pack") + "_safe"
        result = install_pack(pack, require_safe_emit=True, overwrite=overwrite)
        result["fallback_to_echo"] = True
    return result


def promote_latest_drafts(
    *,
    limit: int = 5,
    require_safe_emit: bool = True,
) -> dict[str, Any]:
    """Install up to `limit` draft packs from the learning directory."""
    installed: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for item in list_draft_packs()[:limit]:
        res = promote_draft_file(
            item["path"], require_safe_emit=require_safe_emit, overwrite=True
        )
        if res.get("ok"):
            installed.append(res)
        else:
            failed.append({"path": item["path"], "result": res})
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
    """Build pack from a learned KB entry and install."""
    entries = {e.id: e for e in load_learned_kb()}
    entry = entries.get(entry_id)
    if not entry:
        # try draft file
        draft = _learning_dir_draft(entry_id)
        if draft:
            return promote_draft_file(draft, require_safe_emit=require_safe_emit)
        return {"ok": False, "errors": [f"unknown entry: {entry_id}"]}

    # Prefer stable ascii key from entry id hash segment
    import hashlib
    digest = hashlib.sha1(entry_id.encode("utf-8")).hexdigest()[:12]
    key = f"pack_learned_{digest}"
    cap = PackCapability(
        key=key,
        service=entry.suggested_service if entry.suggested_service in {
            "generic", "content", "utils", "core", "shop", "reminders"
        } else "generic",
        method=entry.suggested_method if entry.suggested_method in {
            "echo", "announce", "start", "help"
        } else "echo",
        description_ar=entry.title or key,
        description_en=entry.summary or entry.title or key,
        category="utils",
        keywords=list(entry.keywords or entry.phrases or [])[:16],
    )
    pack = CapabilityPack(
        id=f"promoted_{entry.id}"[:80],
        version="1.0.0",
        name=entry.title,
        description=entry.summary,
        capabilities=[cap],
        source="learning_promoted",
        enabled=True,
    )
    return install_pack(pack, require_safe_emit=require_safe_emit, overwrite=True)


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
        "installed_files": [p.name for p in installed[:20]],
    }


__all__ = [
    "install_pack",
    "promote_draft_file",
    "promote_latest_drafts",
    "promote_learned_entry",
    "promotion_status",
]
