"""Project memory — durable, editable record of each user's built projects.

For every project a user generates or clones, we keep a structured "project
card" the engine can read to apply precise edits later:

  - identity: id, label, kind (generated|clone), path, source_request
  - structure: file tree snapshot (key files)
  - ui_elements: buttons / commands / keyboards the user added or removed
  - edit_history: ordered list of edits the user requested (so we can reason
    about "remove the help button" → "add a settings button" → ... with full
    continuity, even across sessions)

This is the substrate that makes "the engine remembers the project so the user
can edit anything later" real — not a mock, not a placeholder.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _default_db_path() -> Path:
    try:
        from lumen.platform.paths import durable_data_dir
        root = Path(durable_data_dir())
    except Exception:
        root = Path(os.getenv("OUTPUT_DIR") or (Path.home() / ".lumen"))
    root.mkdir(parents=True, exist_ok=True)
    return root / "project_memory.sqlite3"


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@dataclass
class ProjectCard:
    project_id: str
    user_id: int
    label: str = ""
    kind: str = "generated"  # generated | clone
    path: str = ""
    url: str = ""
    source_request: str = ""
    structure: dict[str, Any] = field(default_factory=dict)
    ui_elements: dict[str, Any] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    edit_history: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "user_id": self.user_id,
            "label": self.label,
            "kind": self.kind,
            "path": self.path,
            "url": self.url,
            "source_request": self.source_request,
            "structure": dict(self.structure),
            "ui_elements": dict(self.ui_elements),
            "meta": dict(self.meta),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "edit_history": list(self.edit_history),
        }


class ProjectMemoryStore:
    """SQLite-backed project cards with ordered edit history."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or _default_db_path())
        self._lock = threading.RLock()
        self._init()

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(str(self.path), timeout=30, check_same_thread=False)
        c.row_factory = sqlite3.Row
        try:
            c.execute("PRAGMA journal_mode=WAL")
        except Exception:
            pass
        return c

    def _init(self) -> None:
        with self._lock:
            with self._conn() as conn:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS project_cards (
                        project_id TEXT PRIMARY KEY,
                        user_id INTEGER NOT NULL,
                        label TEXT NOT NULL DEFAULT '',
                        kind TEXT NOT NULL DEFAULT 'generated',
                        path TEXT NOT NULL DEFAULT '',
                        url TEXT NOT NULL DEFAULT '',
                        source_request TEXT NOT NULL DEFAULT '',
                        structure_json TEXT NOT NULL DEFAULT '{}',
                        ui_elements_json TEXT NOT NULL DEFAULT '{}',
                        meta_json TEXT NOT NULL DEFAULT '{}',
                        edit_history_json TEXT NOT NULL DEFAULT '[]',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_pc_user
                        ON project_cards(user_id);
                    """
                )
                conn.commit()

    def _row_to_card(self, row: sqlite3.Row) -> ProjectCard:
        def _loads(s: str, default):
            try:
                return json.loads(s) if s else default
            except Exception:
                return default
        return ProjectCard(
            project_id=row["project_id"],
            user_id=int(row["user_id"]),
            label=row["label"] or "",
            kind=row["kind"] or "generated",
            path=row["path"] or "",
            url=row["url"] or "",
            source_request=row["source_request"] or "",
            structure=_loads(row["structure_json"], {}),
            ui_elements=_loads(row["ui_elements_json"], {}),
            meta=_loads(row["meta_json"], {}),
            edit_history=_loads(row["edit_history_json"], []),
            created_at=row["created_at"] or "",
            updated_at=row["updated_at"] or "",
        )

    def upsert_card(self, card: ProjectCard) -> ProjectCard:
        now = _now()
        if not card.created_at:
            card.created_at = now
        card.updated_at = now
        with self._lock:
            with self._conn() as conn:
                conn.execute(
                    """
                    INSERT INTO project_cards(
                        project_id, user_id, label, kind, path, url,
                        source_request, structure_json, ui_elements_json,
                        meta_json, edit_history_json, created_at, updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(project_id) DO UPDATE SET
                        label=excluded.label, kind=excluded.kind, path=excluded.path,
                        url=excluded.url, source_request=excluded.source_request,
                        structure_json=excluded.structure_json,
                        ui_elements_json=excluded.ui_elements_json,
                        meta_json=excluded.meta_json,
                        edit_history_json=excluded.edit_history_json,
                        updated_at=excluded.updated_at
                    """,
                    (card.project_id, card.user_id, card.label, card.kind,
                     card.path, card.url, card.source_request[:500],
                     json.dumps(card.structure, ensure_ascii=False)[:8000],
                     json.dumps(card.ui_elements, ensure_ascii=False)[:8000],
                     json.dumps(card.meta, ensure_ascii=False)[:4000],
                     json.dumps(card.edit_history, ensure_ascii=False)[:16000],
                     card.created_at, card.updated_at),
                )
                conn.commit()
        return card

    def get_card(self, project_id: str) -> ProjectCard | None:
        with self._lock:
            with self._conn() as conn:
                row = conn.execute(
                    "SELECT * FROM project_cards WHERE project_id=?",
                    (project_id,),
                ).fetchone()
        return self._row_to_card(row) if row else None

    def list_cards(self, user_id: int) -> list[ProjectCard]:
        with self._lock:
            with self._conn() as conn:
                rows = conn.execute(
                    "SELECT * FROM project_cards WHERE user_id=? "
                    "ORDER BY updated_at DESC",
                    (int(user_id or 0),),
                ).fetchall()
        return [self._row_to_card(r) for r in rows]

    def register_project(
        self,
        *,
        user_id: int,
        project_id: str | None,
        label: str,
        kind: str,
        path: str,
        url: str = "",
        source_request: str = "",
        structure: dict[str, Any] | None = None,
        ui_elements: dict[str, Any] | None = None,
        meta: dict[str, Any] | None = None,
    ) -> ProjectCard:
        pid = (project_id or str(uuid.uuid4())).strip()
        card = self.get_card(pid) or ProjectCard(
            project_id=pid, user_id=int(user_id or 0)
        )
        card.user_id = int(user_id or 0)
        card.label = (label or card.label or Path(path).name)[:120]
        card.kind = (kind or card.kind or "generated")[:30]
        card.path = str(path or card.path)
        card.url = (url or card.url)[:300]
        if source_request:
            card.source_request = source_request[:500]
        if structure:
            card.structure = {**card.structure, **structure}
        if ui_elements:
            card.ui_elements = {**card.ui_elements, **ui_elements}
        if meta:
            card.meta = {**card.meta, **meta}
        return self.upsert_card(card)

    def record_edit(
        self,
        project_id: str,
        *,
        edit_type: str,
        description: str,
        target: str = "",
        applied: bool = True,
        extra: dict[str, Any] | None = None,
    ) -> ProjectCard | None:
        """Append an edit to the ordered history (button add/remove, file change...)."""
        card = self.get_card(project_id)
        if not card:
            return None
        entry = {
            "id": str(uuid.uuid4()),
            "ts": _now(),
            "type": (edit_type or "edit")[:40],
            "description": (description or "")[:300],
            "target": (target or "")[:120],
            "applied": bool(applied),
            "extra": dict(extra or {}),
        }
        card.edit_history.append(entry)
        card.edit_history = card.edit_history[-200:]
        # reflect UI element mutations into the ui_elements snapshot
        if edit_type in {"add_button", "remove_button", "add_command",
                         "remove_command", "add_keyboard", "remove_keyboard"}:
            bucket = "buttons" if "button" in edit_type else (
                "commands" if "command" in edit_type else "keyboards"
            )
            lst = list(card.ui_elements.get(bucket) or [])
            name = (target or description or "").strip()[:80]
            if edit_type.startswith("add"):
                if name and name not in lst:
                    lst.append(name)
            elif edit_type.startswith("remove"):
                if name:
                    lst = [x for x in lst if x != name]
            card.ui_elements[bucket] = lst
        return self.upsert_card(card)

    def update_structure(self, project_id: str, structure: dict[str, Any]) -> bool:
        card = self.get_card(project_id)
        if not card:
            return False
        card.structure = {**card.structure, **structure}
        self.upsert_card(card)
        return True

    def delete_card(self, project_id: str) -> bool:
        with self._lock:
            with self._conn() as conn:
                cur = conn.execute(
                    "DELETE FROM project_cards WHERE project_id=?",
                    (project_id,),
                )
                conn.commit()
                return cur.rowcount > 0

    
    def record_resolved_error(
        self,
        project_id: str,
        *,
        error: str,
        solution: str,
        tool: str = "",
        strategy: str = "",
        extra: dict[str, Any] | None = None,
    ) -> ProjectCard | None:
        """Store a resolved error + linked solution on the project card.

        Kept in meta['resolved_errors'] (newest first, capped) and mirrored into
        edit_history with edit_type='resolved_error' for ordered continuity.
        """
        card = self.get_card(project_id)
        if not card:
            return None
        entry = {
            "error": str(error or "")[:500],
            "solution": str(solution or "")[:500],
            "tool": str(tool or "")[:80],
            "strategy": str(strategy or "")[:80],
            "at": _now(),
        }
        if extra and isinstance(extra, dict):
            entry["extra"] = {str(k)[:40]: str(v)[:120] for k, v in list(extra.items())[:8]}
        resolved = list((card.meta or {}).get("resolved_errors") or [])
        # de-dupe by error head
        head = entry["error"][:120]
        resolved = [r for r in resolved if str((r or {}).get("error") or "")[:120] != head]
        resolved.insert(0, entry)
        card.meta = dict(card.meta or {})
        card.meta["resolved_errors"] = resolved[:40]
        self.upsert_card(card)
        self.record_edit(
            project_id,
            edit_type="resolved_error",
            description=f"{entry['error'][:160]} → {entry['solution'][:160]}",
            target=entry.get("tool") or "",
            applied=True,
            extra={"strategy": entry.get("strategy"), "error": entry["error"][:200]},
        )
        return self.get_card(project_id)

    def list_resolved_errors(self, project_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
        card = self.get_card(project_id)
        if not card:
            return []
        items = list((card.meta or {}).get("resolved_errors") or [])
        return items[: max(1, min(int(limit or 20), 40))]

    def get_active_card(
        self,
        user_id: int,
        *,
        path: str = "",
        project_id: str = "",
    ) -> ProjectCard | None:
        """Resolve the active project card for a user (by id, path, or most recent)."""
        if project_id:
            card = self.get_card(project_id)
            if card and int(card.user_id or 0) == int(user_id or 0):
                return card
        path_n = str(path or "").rstrip("/")
        cards = self.list_cards(int(user_id or 0))
        if path_n:
            for c in cards:
                cp = str(c.path or "").rstrip("/")
                if cp and (cp == path_n or path_n.startswith(cp + "/") or cp.startswith(path_n + "/")):
                    return c
        return cards[0] if cards else None

    def context_for_engine(self, project_id: str, *, max_history: int = 20) -> str:
        """Compact project card for the AI/engines to reason about edits."""
        card = self.get_card(project_id)
        if not card:
            return ""
        lines = [f"### ذاكرة المشروع: {card.label or card.project_id}"]
        lines.append(f"- النوع: {card.kind}")
        if card.source_request:
            lines.append(f"- الطلب الأصلي: {card.source_request[:200]}")
        ui = card.ui_elements
        if ui:
            if ui.get("buttons"):
                lines.append(f"- الأزرار الحالية: {', '.join(map(str, ui['buttons']))}")
            if ui.get("commands"):
                lines.append(f"- الأوامر الحالية: {', '.join(map(str, ui['commands']))}")
            if ui.get("keyboards"):
                lines.append(f"- لوحات المفاتيح: {', '.join(map(str, ui['keyboards']))}")
        hist = card.edit_history[-max_history:]
        if hist:
            lines.append("- سجل التعديلات:")
            for e in hist:
                mark = "✓" if e.get("applied") else "·"
                lines.append(f"  {mark} [{e.get('type')}] {e.get('description')}")
        
        resolved = list((card.meta or {}).get("resolved_errors") or [])
        if resolved:
            lines.append("- أخطاء محلولة سابقة:")
            for r in resolved[:6]:
                err = str((r or {}).get("error") or "")[:100]
                sol = str((r or {}).get("solution") or "")[:100]
                tool = str((r or {}).get("tool") or "")
                bit = f"  • [{tool}] {err}" if tool else f"  • {err}"
                if sol:
                    bit += f" → {sol}"
                lines.append(bit)

        return "\n".join(lines)[:3000]


_store: ProjectMemoryStore | None = None
_store_lock = threading.Lock()


def get_project_memory_store() -> ProjectMemoryStore:
    global _store
    with _store_lock:
        if _store is None:
            _store = ProjectMemoryStore()
        return _store


__all__ = [
    "ProjectCard",
    "ProjectMemoryStore",
    "get_project_memory_store",
]
