"""Project context packer — real workspace snapshot for Worker/Planner.

Uses official cline agent_fs tools (tree/list_dir/read_file), not ad-hoc scripts.
Phase-3: parallel inspect/read via run_tools_parallel (max 3).
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
    """Snapshot tree + key file heads via agent_fs parallel tools when possible."""
    root = Path(project_path)
    out: dict[str, Any] = {
        "ok": False,
        "path": str(root),
        "tree": "",
        "files": {},
        "errors": [],
        "parallel": False,
    }
    if not root.is_dir():
        out["errors"].append("not_a_dir")
        return out

    try:
        from lumen.engine.services.cline_runtime.agent_fs import run_tool, run_tools_parallel
    except Exception as exc:
        out["errors"].append(f"agent_fs_import:{type(exc).__name__}")
        return out

    # Parallel batch 1: tree + list_dir + glob py (independent inspect)
    try:
        batch1 = run_tools_parallel(
            str(root),
            [
                {"tool": "tree", "args": {"path": ".", "max_depth": 4}},
                {"tool": "list_dir", "args": {"path": "."}},
                {"tool": "glob_files", "args": {"pattern": "*.py"}},
            ],
            max_parallel=3,
        )
        out["parallel"] = True
        tree_res = batch1[0] if batch1 else {}
        if tree_res.get("ok"):
            out["tree"] = str(tree_res.get("tree") or "")[:3000]
        else:
            out["errors"].append(str(tree_res.get("error") or "tree_failed"))
    except Exception as exc:
        tree_res = run_tool(str(root), "tree", {"path": ".", "max_depth": 4})
        if tree_res.get("ok"):
            out["tree"] = str(tree_res.get("tree") or "")[:3000]
        else:
            out["errors"].append(str(tree_res.get("error") or "tree_failed"))
        out["errors"].append(f"parallel_fallback:{type(exc).__name__}")

    candidates: list[str] = []
    for name in ("main.py", "bot.py", "requirements.txt", "README.md", ".env.example"):
        if (root / name).is_file():
            candidates.append(name)
    for mod in sorted((root / "modules").glob("*.py")) if (root / "modules").is_dir() else []:
        candidates.append(str(mod.relative_to(root)))
        if len(candidates) >= max_files:
            break

    files: dict[str, str] = {}
    rels = candidates[:max_files]
    if rels:
        try:
            read_calls = [{"tool": "read_file", "args": {"path": rel}} for rel in rels]
            # process in chunks of 3
            read_results: list[dict[str, Any]] = []
            for i in range(0, len(read_calls), 3):
                chunk = read_calls[i:i+3]
                read_results.extend(run_tools_parallel(str(root), chunk, max_parallel=3))
            out["parallel"] = True
            for rel, res in zip(rels, read_results):
                if not isinstance(res, dict) or not res.get("ok"):
                    out["errors"].append(f"read_fail:{rel}")
                    continue
                content = str(res.get("content") or "")
                if len(content) > max_bytes_per_file:
                    content = content[:max_bytes_per_file] + f"\n...[truncated {len(content)} chars]"
                files[rel] = content
        except Exception as exc:
            out["errors"].append(f"parallel_read_fallback:{type(exc).__name__}")
            for rel in rels:
                res = run_tool(str(root), "read_file", {"path": rel})
                if not res.get("ok"):
                    out["errors"].append(f"read_fail:{rel}")
                    continue
                content = str(res.get("content") or "")
                if len(content) > max_bytes_per_file:
                    content = content[:max_bytes_per_file] + f"\n...[truncated {len(content)} chars]"
                files[rel] = content

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
