"""Project context packer — real workspace snapshot for Worker/Planner.

Uses official cline agent_fs tools (tree/list_dir/read_file), not ad-hoc scripts.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


def pack_project_context(
    project_path: str | Path,
    *,
    max_files: int = 12,
    max_bytes_per_file: int = 2500,
) -> dict[str, Any]:
    """Snapshot tree + key file heads via agent_fs.run_tool."""
    root = Path(project_path)
    out: dict[str, Any] = {
        "ok": False,
        "path": str(root),
        "tree": "",
        "files": {},
        "errors": [],
    }
    if not root.is_dir():
        out["errors"].append("not_a_dir")
        return out

    try:
        from lumen.engine.services.cline_runtime.agent_fs import run_tool
    except Exception as exc:
        out["errors"].append(f"agent_fs_import:{type(exc).__name__}")
        return out

    tree_res = run_tool(str(root), "tree", {"path": ".", "max_depth": 4})
    if tree_res.get("ok"):
        out["tree"] = str(tree_res.get("tree") or "")[:3000]
    else:
        out["errors"].append(str(tree_res.get("error") or "tree_failed"))

    # Prefer entry + requirements + modules
    candidates: list[str] = []
    for name in ("main.py", "bot.py", "requirements.txt", "README.md", ".env.example"):
        if (root / name).is_file():
            candidates.append(name)
    for mod in sorted((root / "modules").glob("*.py")) if (root / "modules").is_dir() else []:
        candidates.append(str(mod.relative_to(root)))
        if len(candidates) >= max_files:
            break

    files: dict[str, str] = {}
    for rel in candidates[:max_files]:
        res = run_tool(str(root), "read_file", {"path": rel})
        if not res.get("ok"):
            out["errors"].append(f"read_fail:{rel}")
            continue
        content = str(res.get("content") or "")
        if len(content) > max_bytes_per_file:
            content = content[:max_bytes_per_file] + f"\n...[truncated {len(content)} chars]"
        files[rel] = content
        # mark as read for repair policy if agent_loop shares metadata later

    out["files"] = files
    out["ok"] = bool(out["tree"] or files)
    return out


def context_to_prompt_block(ctx: dict[str, Any]) -> str:
    if not ctx or not ctx.get("ok"):
        return ""
    lines = ["--- WORKSPACE_SNAPSHOT ---", "TREE:", str(ctx.get("tree") or "")[:2000]]
    for path, body in list((ctx.get("files") or {}).items())[:12]:
        lines.append(f"\nFILE {path}:\n{body}")
    lines.append("--- END_SNAPSHOT ---")
    return "\n".join(lines)


__all__ = ["pack_project_context", "context_to_prompt_block"]
