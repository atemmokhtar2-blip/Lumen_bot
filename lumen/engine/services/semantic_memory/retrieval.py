"""Memory retrieval — semantic recall for the AI layer.

Called BEFORE a model/chat request: fetches the most relevant durable memories
for the current user message (and active project), and packs them into a
compact, structured context block the model can reason over.

This is the "read" phase of the Mem0 pipeline:
  search(user_message) → relevant facts → compact context string for the prompt.
"""
from __future__ import annotations

import logging
from typing import Any

from .store import MemoryRecord, get_semantic_store

logger = logging.getLogger(__name__)


def recall(
    *,
    user_id: int,
    query: str,
    project_id: str = "",
    top_k: int = 8,
    min_score: float = 0.30,
) -> list[tuple[MemoryRecord, float]]:
    """Semantic recall scoped to a user (+ optional project)."""
    return get_semantic_store().semantic_search(
        user_id=user_id, query=query,
        project_id=project_id, top_k=top_k, min_score=min_score,
    )


def build_memory_context(
    *,
    user_id: int,
    user_message: str,
    project_id: str = "",
    top_k: int = 8,
) -> str:
    """Compact, structured context string of relevant memories for the model.

    Split into:
      - user_profile: profile/preference/decision facts (cross-project)
      - project_memory: project_note/instruction facts for the active project
    This lets the model act with continuity: "the user prefers X", "on this
    project we decided to remove button Y", etc.
    """
    uid = int(user_id or 0)
    msg = (user_message or "").strip()
    if not uid or not msg:
        return ""

    # Cross-project long-term facts about the user
    profile_hits = recall(
        user_id=uid, query=msg, project_id="", top_k=top_k, min_score=0.30,
    )
    profile_recs = [r for r, _ in profile_hits
                    if r.kind in {"preference", "decision", "profile", "fact"}]

    # Project-scoped memory (structure / buttons / instructions for edits)
    project_recs: list[MemoryRecord] = []
    if project_id:
        phits = recall(
            user_id=uid, query=msg, project_id=project_id,
            top_k=top_k, min_score=0.28,
        )
        project_recs = [r for r, _ in phits
                        if r.kind in {"project_note", "instruction", "decision"}]

    if not profile_recs and not project_recs:
        return ""

    lines: list[str] = []
    if profile_recs:
        lines.append("### ذاكرة المستخدم (حقائق دائمة عنه):")
        for r in profile_recs[:6]:
            kind_label = {
                "preference": "تفضيل", "decision": "قرار",
                "profile": "ملف", "fact": "حقيقة",
            }.get(r.kind, r.kind)
            lines.append(f"- [{kind_label}] {r.content}")
    if project_recs:
        lines.append(f"\n### ذاكرة المشروع الحالي ({project_id}):")
        for r in project_recs[:8]:
            kind_label = {
                "project_note": "ملاحظة", "instruction": "تعليمات",
                "decision": "قرار",
            }.get(r.kind, r.kind)
            lines.append(f"- [{kind_label}] {r.content}")
    return "\n".join(lines)[:3500]


def memory_context_for_llm(
    *,
    user_id: int,
    user_message: str,
    project_id: str = "",
    top_k: int = 8,
) -> dict[str, Any]:
    """Structured payload to merge into chat SERVER_CONTEXT."""
    ctx_str = build_memory_context(
        user_id=user_id, user_message=user_message,
        project_id=project_id, top_k=top_k,
    )
    hits = recall(user_id=user_id, query=user_message,
                  project_id=project_id, top_k=top_k)
    memories = [
        {"id": r.id, "kind": r.kind, "content": r.content,
         "project_id": r.project_id}
        for r, _ in hits
    ]
    return {
        "semantic_memory": ctx_str,
        "semantic_memory_hits": memories,
    }


__all__ = [
    "recall",
    "build_memory_context",
    "memory_context_for_llm",
]
