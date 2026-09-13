"""Build OWNER_* env from materialized project / pending payload."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


def owner_env_from_project(project_path: str | Path, *, user_id: int = 0) -> dict[str, str]:
    out: dict[str, str] = {}
    uid = int(user_id or 0)
    if uid > 0:
        out["OWNER_ADMIN_ID"] = str(uid)
        out["LUMEN_OWNER_ID"] = str(uid)
        out["LUMEN_OWNER_ADMIN_ID"] = str(uid)
    root = Path(project_path or "")
    if root.is_dir():
        for name in ("lumen_owner.json", ".lumen_owner.json"):
            p = root / name
            if not p.is_file():
                continue
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                v = data.get("owner_admin_id") or data.get("owner_user_id") or data.get("user_id")
                if v is not None and str(v).strip().isdigit():
                    oid = str(int(str(v).strip()))
                    out.setdefault("OWNER_ADMIN_ID", oid)
                    out.setdefault("LUMEN_OWNER_ID", oid)
                    out.setdefault("LUMEN_OWNER_ADMIN_ID", oid)
            except Exception:
                pass
    return out


def merge_owner_into_env(
    env: Mapping[str, Any] | None,
    *,
    project_path: str | Path = "",
    user_id: int = 0,
) -> dict[str, str]:
    base = {str(k): str(v) for k, v in dict(env or {}).items() if k and v is not None}
    base.update(owner_env_from_project(project_path, user_id=user_id))
    return base


__all__ = ["owner_env_from_project", "merge_owner_into_env"]
