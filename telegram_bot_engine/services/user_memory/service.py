"""UserMemory — persistent per-user context for smart developer collaboration.

Stores:
  - recent conversation turns (user / assistant / system-note)
  - last intent / last project path
  - light facts the user stated (free-form, not a fixed schema)

Does NOT store canned bot templates or default command packs.
Everything is derived from real interaction with this user.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..user_sandbox.service import get_user_sandbox


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@dataclass
class UserMemory:
    user_id: int
    path: Path
    max_turns: int = 40

    def ensure(self) -> "UserMemory":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write({
                "user_id": self.user_id,
                "turns": [],
                "last_intent": "",
                "last_project_path": "",
                "last_capability": "",
                "facts": [],
                "updated_at": _now(),
            })
        return self

    def _read(self) -> dict[str, Any]:
        try:
            if self.path.exists():
                return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {
            "user_id": self.user_id,
            "turns": [],
            "last_intent": "",
            "last_project_path": "",
            "last_capability": "",
            "facts": [],
            "updated_at": "",
        }

    def _write(self, data: dict[str, Any]) -> None:
        data = dict(data)
        data["user_id"] = self.user_id
        data["updated_at"] = _now()
        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def add_turn(self, role: str, text: str, *, meta: dict[str, Any] | None = None) -> None:
        """Append a conversation turn. role: user | assistant | note."""
        self.ensure()
        data = self._read()
        turn: dict[str, Any] = {
            "role": (role or "user")[:20],
            "text": (text or "")[:2000],
            "ts": _now(),
        }
        if meta:
            turn["meta"] = {k: v for k, v in meta.items() if v is not None}
        turns = list(data.get("turns") or [])
        turns.append(turn)
        data["turns"] = turns[-self.max_turns :]
        self._write(data)

    def set_last(
        self,
        *,
        intent: str = "",
        project_path: str = "",
        capability: str = "",
    ) -> None:
        self.ensure()
        data = self._read()
        if intent:
            data["last_intent"] = intent[:200]
        if project_path:
            data["last_project_path"] = project_path[:500]
        if capability:
            data["last_capability"] = capability[:80]
        self._write(data)

    def add_fact(self, fact: str) -> None:
        """Free-form fact stated by / about the user (no fixed schema)."""
        fact = (fact or "").strip()
        if not fact:
            return
        self.ensure()
        data = self._read()
        facts = [f for f in (data.get("facts") or []) if f != fact]
        facts.insert(0, fact[:300])
        data["facts"] = facts[:30]
        self._write(data)

    def snapshot(self) -> dict[str, Any]:
        self.ensure()
        return self._read()

    def context_for_ai(self, *, max_turns: int = 12) -> str:
        """
        Build a compact dynamic context string for the AI layer.
        Not a user-facing reply — only background for understanding.
        Includes recent turns + last project + sandbox project list.
        """
        data = self._read()
        parts: list[str] = []

        last_proj = (data.get("last_project_path") or "").strip()
        last_cap = (data.get("last_capability") or "").strip()
        last_intent = (data.get("last_intent") or "").strip()
        if last_proj or last_cap or last_intent:
            bits = []
            if last_intent:
                bits.append(f"intent={last_intent}")
            if last_cap:
                bits.append(f"capability={last_cap}")
            if last_proj:
                bits.append(f"last_project={last_proj}")
            parts.append("state: " + "; ".join(bits))

        facts = list(data.get("facts") or [])[:8]
        if facts:
            parts.append("facts: " + " | ".join(facts))

        # Projects from sandbox index (what this user actually built)
        try:
            sb = get_user_sandbox(self.user_id)
            projs = sb.list_projects()[:8]
            if projs:
                lines = []
                for p in projs:
                    label = p.get("label") or p.get("id") or ""
                    prev = (p.get("source_request_preview") or "")[:80]
                    lines.append(f"- {label}: {prev}".strip(": "))
                parts.append("user_projects:\n" + "\n".join(lines))
            clones = sb.list_clones()[:5]
            if clones:
                parts.append(
                    "user_clones: "
                    + ", ".join(
                        (c.get("label") or c.get("url") or c.get("id") or "")[:60]
                        for c in clones
                    )
                )
        except Exception:
            pass

        turns = list(data.get("turns") or [])[-max_turns:]
        if turns:
            chat_lines = []
            for t in turns:
                role = t.get("role") or "?"
                txt = (t.get("text") or "").replace("\n", " ")[:180]
                chat_lines.append(f"{role}: {txt}")
            parts.append("recent_chat:\n" + "\n".join(chat_lines))

        return "\n\n".join(parts)[:3500]


def get_user_memory(user_id: int, base_dir: str | Path | None = None) -> UserMemory:
    """Memory file lives inside the user's sandbox root."""
    sb = get_user_sandbox(int(user_id or 0), base_dir)
    path = sb.root / "memory.json"
    return UserMemory(user_id=int(user_id or 0), path=path).ensure()


__all__ = ["UserMemory", "get_user_memory"]
