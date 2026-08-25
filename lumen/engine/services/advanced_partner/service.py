"""
Phase 6 — Advanced Partner Level

Provides:
  - Dynamic brief for the AI (architecture/planning context from real files)
  - Lightweight version snapshots of a user's project after meaningful edits
  - Intent signals for planning / architecture / release discussion

No fixed user-facing scripts. No domain bot templates.
Everything is derived from this user's projects, memory, and message.
"""

from __future__ import annotations

import json
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..user_memory.service import get_user_memory
from ..user_sandbox.service import get_user_sandbox
from ..context_engine.service import resolve_context


_SKIP_DIRS = {
    ".git", "__pycache__", ".venv", "venv", "node_modules",
    ".mypy_cache", ".tbe_venv", "versions",
}

_PLAN_CUES = re.compile(
    r"(?:"
    r"خط[ةه]\s*تطوير|تخطيط|معمار|architecture|roadmap|plan\b|"
    r"اقتراح|حسّن|تحسين|performance|أمان|security|"
    r"إصدار|اصدار|version|release|نسخة|"
    r"كيف\s*نطور|ازاي\s*نطور|next\s*steps|ماذا\s*بعد|ايه\s*بعد"
    r")",
    re.I,
)


@dataclass
class AdvancedBrief:
    """Machine + AI context only — not a canned chat reply."""

    intent_advanced: bool = False
    target_path: str = ""
    project_summary: str = ""
    file_tree_sample: list[str] = field(default_factory=list)
    memory_snippet: str = ""
    versions_count: int = 0
    signals: list[str] = field(default_factory=list)

    def to_ai_context(self) -> str:
        parts: list[str] = []
        if self.intent_advanced:
            parts.append("advanced_partner_intent=true")
        if self.target_path:
            parts.append(f"focus_project={self.target_path}")
        if self.versions_count:
            parts.append(f"snapshots_available={self.versions_count}")
        if self.project_summary:
            parts.append("project_summary:\n" + self.project_summary[:1200])
        if self.file_tree_sample:
            parts.append(
                "files_sample:\n" + "\n".join(f"- {x}" for x in self.file_tree_sample[:40])
            )
        if self.memory_snippet:
            parts.append("memory:\n" + self.memory_snippet[:1500])
        if self.signals:
            parts.append("signals=" + ",".join(self.signals[:12]))
        return "\n\n".join(parts)[:3500]

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent_advanced": self.intent_advanced,
            "target_path": self.target_path,
            "versions_count": self.versions_count,
            "signals": list(self.signals)[:12],
            "files_sample_n": len(self.file_tree_sample),
        }


def detect_advanced_intent(text: str) -> bool:
    return bool(_PLAN_CUES.search(text or ""))


def _sample_tree(root: Path, limit: int = 40) -> list[str]:
    out: list[str] = []
    if not root.is_dir():
        return out
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if any(part in _SKIP_DIRS for part in p.parts):
            continue
        try:
            rel = str(p.relative_to(root))
        except Exception:
            rel = p.name
        out.append(rel)
        if len(out) >= limit:
            break
    return out


def _summarize_project(root: Path) -> str:
    """Cheap structural summary from the filesystem — not a template bot."""
    files = _sample_tree(root, limit=80)
    py = [f for f in files if f.endswith(".py")]
    has_req = any(f == "requirements.txt" or f.endswith("/requirements.txt") for f in files)
    has_main = any(Path(f).name in ("main.py", "bot.py", "app.py") for f in files)
    lines = [
        f"path={root}",
        f"file_count_sample={len(files)}",
        f"python_files={len(py)}",
        f"has_requirements={has_req}",
        f"has_entry_hint={has_main}",
    ]
    # command-like tokens in python filenames / paths only
    cmdish = [f for f in py if "handler" in f.lower() or "command" in f.lower()]
    if cmdish:
        lines.append("handler_paths=" + ",".join(cmdish[:8]))
    return "\n".join(lines)


def build_advanced_brief(
    user_id: int,
    text: str,
    *,
    base_dir: str | Path | None = None,
    active_path: str = "",
) -> AdvancedBrief:
    uid = int(user_id or 0)
    brief = AdvancedBrief()
    brief.intent_advanced = detect_advanced_intent(text)

    ctx = resolve_context(
        uid, text or "", base_dir=base_dir, active_path=active_path
    )
    path = (ctx.target_path or active_path or "").strip()
    if path and Path(path).exists():
        brief.target_path = str(Path(path).resolve())
        brief.signals.extend(ctx.signals[:8])
        if ctx.refers_to_prior:
            brief.signals.append("prior_project")
    elif active_path and Path(active_path).exists():
        brief.target_path = str(Path(active_path).resolve())
        brief.signals.append("session_active")

    mem = get_user_memory(uid, base_dir)
    brief.memory_snippet = mem.context_for_ai(max_turns=8)

    if brief.target_path:
        root = Path(brief.target_path)
        brief.file_tree_sample = _sample_tree(root)
        brief.project_summary = _summarize_project(root)
        vdir = root / "versions"
        if vdir.is_dir():
            brief.versions_count = sum(1 for _ in vdir.iterdir() if _.is_dir())

    if brief.intent_advanced:
        brief.signals.append("plan_or_architecture_cue")

    return brief


def maybe_snapshot_version(
    user_id: int,
    project_path: str | Path,
    *,
    label: str = "",
    reason: str = "",
    base_dir: str | Path | None = None,
) -> dict[str, Any] | None:
    """
    Copy a lightweight snapshot under project/versions/<timestamp>/.
    Stores only metadata about why — no canned bot packs.
    """
    root = Path(project_path).resolve()
    if not root.is_dir():
        return None
    # Only snapshot projects under this user's sandbox when possible
    try:
        sb = get_user_sandbox(int(user_id or 0), base_dir)
        if not sb.is_under_sandbox(root):
            # still allow if path exists; isolation preferred
            pass
    except Exception:
        pass

    stamp = time.strftime("%Y%m%d_%H%M%S")
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", (label or "snap")[:40]) or "snap"
    dest = root / "versions" / f"{stamp}_{safe}"
    try:
        dest.mkdir(parents=True, exist_ok=False)
        # copy tree excluding heavy/meta dirs
        for item in root.iterdir():
            if item.name in _SKIP_DIRS or item.name == "versions":
                continue
            target = dest / item.name
            if item.is_dir():
                shutil.copytree(
                    item,
                    target,
                    ignore=shutil.ignore_patterns(
                        ".git", "__pycache__", ".venv", "venv", "node_modules", "*.pyc"
                    ),
                )
            else:
                shutil.copy2(item, target)
        meta = {
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "reason": (reason or "")[:300],
            "label": safe,
            "source": str(root),
        }
        (dest / "snapshot_meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return {"path": str(dest), "meta": meta}
    except Exception:
        return None


__all__ = [
    "AdvancedBrief",
    "build_advanced_brief",
    "maybe_snapshot_version",
    "detect_advanced_intent",
]
