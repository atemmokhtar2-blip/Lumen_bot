"""
ContextEngine — Phase 3

Resolves whether the user's current message refers to prior projects/clones
or continues an ongoing thread. Purely dynamic from:
  - UserMemory (last project, turns, facts)
  - UserSandbox index (projects/clones the user actually produced)

No canned bot templates. No fixed reply texts for the end user.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..user_memory.service import get_user_memory
from ..user_sandbox.service import get_user_sandbox


@dataclass
class ContextResolution:
    """Machine-readable resolution only — not a user-facing message."""

    refers_to_prior: bool = False
    target_path: str = ""
    target_kind: str = ""  # generated | clone | ""
    target_label: str = ""
    confidence: float = 0.0
    signals: list[str] = field(default_factory=list)
    projects_known: int = 0
    clones_known: int = 0
    memory_context: str = ""
    source_request_preview: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "refers_to_prior": self.refers_to_prior,
            "target_path": self.target_path,
            "target_kind": self.target_kind,
            "target_label": self.target_label,
            "confidence": self.confidence,
            "signals": list(self.signals)[:12],
            "projects_known": self.projects_known,
            "clones_known": self.clones_known,
            "source_request_preview": self.source_request_preview[:200],
        }


# Linguistic cues that the user is pointing at prior work (not templates —
# matching only; replies still come from AI/engines).
_PRIOR_CUES = (
    r"السابق", r"اللي\s*فات", r"اللي\s*قبل", r"امبارح", r"أمس", r"قبل\s*كده",
    r"آخر\s*مشروع", r"اخر\s*مشروع", r"آخر\s*بوت", r"اخر\s*بوت",
    r"نفس\s*المشروع", r"نفس\s*البوت", r"المشروع\s*ده", r"البوت\s*ده",
    r"عد[لّ](?:ه|ها|ـ)?", r"كم[لّ]", r"كمّل", r"كمّلي", r"طور", r"عدّل",
    r"رج[عّ]", r"كمّل\s*على", r"كمّل\s*علي",
    r"\bprevious\b", r"\blast\s+project\b", r"\blast\s+bot\b",
    r"\bsame\s+project\b", r"\bcontinue\b", r"\bmodify\b", r"\bupdate\s+the\s+bot\b",
)

_PRIOR_RE = re.compile("|".join(f"(?:{_})" for _ in _PRIOR_CUES), re.I)


def _score_entry(text: str, entry: dict[str, Any]) -> tuple[float, list[str]]:
    """Score how well an index entry matches the user text."""
    t = (text or "").lower()
    signals: list[str] = []
    score = 0.0

    label = (entry.get("label") or entry.get("id") or "").lower()
    preview = (entry.get("source_request_preview") or "").lower()
    path = (entry.get("path") or "").lower()

    if label and label in t:
        score += 0.45
        signals.append("label_in_text")
    if preview:
        # overlap of significant tokens from original generation request
        tokens = [w for w in re.split(r"\s+", preview) if len(w) > 2][:12]
        hits = sum(1 for w in tokens if w in t)
        if hits:
            score += min(0.4, 0.08 * hits)
            signals.append(f"preview_overlap:{hits}")

    # path id fragment
    pid = Path(path).name.lower() if path else ""
    if pid and len(pid) > 6 and pid[:10] in t.replace(" ", "_"):
        score += 0.2
        signals.append("path_id")

    return score, signals


# Edit-intent cues: the user wants to modify a prior project (buttons, commands,
# keyboards, files). These pair with semantic matching against project memory so
# the engine binds to the right project even without an explicit "السابق" cue.
_EDIT_CUES = re.compile(
    r"(?:شيل|احذف|امسح|ضيف|ضيف\s*زر|زر\s*جديد|اعمل\s*زر|امر|امر\s*جديد|"
    r"كيبورد|ازرار|عدل|عدل\s*على|تعديل|ضيف\s*زرار|شيل\s*الزر|"
    r"remove|add|button|command|keyboard|edit|modify|delete\s+the)",
    re.I,
)


def _semantic_project_match(
    user_id: int, text: str, candidate_paths: list[str],
) -> tuple[str, float, list[str]]:
    """Use the semantic memory store to match the user's edit message to a project.

    Returns (best_project_path, score, signals). Uses project_note/decision
    memories scoped per-project: the project whose stored memories best match
    the user's message semantically wins. This is the real continuity engine —
    "remove the help button" matches the project that has a project_note about
    "help button" even with no lexical overlap.
    """
    uid = int(user_id or 0)
    if not uid or not text or not candidate_paths:
        return "", 0.0, []
    try:
        from ..semantic_memory.store import get_semantic_store
        store = get_semantic_store()
    except Exception:
        return "", 0.0, []
    best_path = ""
    best_score = 0.0
    signals: list[str] = []
    for pid in candidate_paths:
        try:
            hits = store.semantic_search(
                user_id=uid, query=text, project_id=pid,
                kind="", top_k=3, min_score=0.30,
            )
        except Exception:
            hits = []
        if not hits:
            continue
        # use the top hit score for this project
        top_rec, top_score = hits[0]
        if top_score > best_score:
            best_score = top_score
            best_path = pid
            signals.append(f"semantic_match:{top_rec.kind}:{top_score:.2f}")
    return best_path, best_score, signals


def resolve_context(
    user_id: int,
    text: str,
    *,
    base_dir: str | Path | None = None,
    active_path: str = "",
) -> ContextResolution:
    """
    Resolve current message against this user's memory + sandbox index.
    """
    uid = int(user_id or 0)
    text = (text or "").strip()
    res = ContextResolution()

    mem = get_user_memory(uid, base_dir)
    sb = get_user_sandbox(uid, base_dir)
    res.memory_context = mem.context_for_ai()
    projects = sb.list_projects()
    clones = sb.list_clones()
    res.projects_known = len(projects)
    res.clones_known = len(clones)

    snap = mem.snapshot()
    last_path = (snap.get("last_project_path") or "").strip()
    if active_path and Path(active_path).exists():
        # session-active repo wins as soft default target
        res.target_path = str(Path(active_path).resolve())
        res.target_kind = "clone" if "clones" in res.target_path else "generated"
        res.confidence = 0.35
        res.signals.append("session_active")

    if not text:
        return res

    prior_cue = bool(_PRIOR_RE.search(text))
    if prior_cue:
        res.signals.append("prior_cue")

    best_path = ""
    best_kind = ""
    best_label = ""
    best_preview = ""
    best_score = 0.0
    best_signals: list[str] = []

    for kind, entries in (("generated", projects), ("clone", clones)):
        for e in entries:
            sc, sigs = _score_entry(text, e)
            # recency boost: first items in index are newest
            if entries and e is entries[0]:
                sc += 0.12
                sigs = sigs + ["newest"]
            if sc > best_score:
                best_score = sc
                best_path = e.get("path") or ""
                best_kind = kind
                best_label = e.get("label") or e.get("id") or ""
                best_preview = e.get("source_request_preview") or ""
                best_signals = sigs

    # Semantic matching (Mem0-inspired): for edit-intent messages ("remove the
    # help button", "add a settings command") match the user's text against the
    # per-project semantic memory store. This binds the engine to the correct
    # project even when there is zero lexical overlap with the project label.
    edit_cue = bool(_EDIT_CUES.search(text))
    if edit_cue:
        res.signals.append("edit_cue")
        _candidate_paths = [
            e.get("path") or "" for e in (projects + clones)
            if e.get("path")
        ]
        if not _candidate_paths and last_path:
            _candidate_paths = [last_path]
        _sem_path, _sem_score, _sem_signals = _semantic_project_match(
            uid, text, _candidate_paths,
        )
        if _sem_path and _sem_score >= 0.30:
            # semantic match boosts confidence — it can override a weak lexical
            # result because it reflects genuine memory continuity.
            _sem_boost = _sem_score * 0.6
            if _sem_boost > best_score:
                best_path = _sem_path
                best_kind = "clone" if "clones" in _sem_path else "generated"
                best_label = Path(_sem_path).name
                best_score = _sem_boost
                best_signals = _sem_signals
            else:
                # augment existing best match with semantic signal
                best_score = min(0.95, best_score + _sem_boost * 0.4)
                best_signals.extend(_sem_signals)

    # If user signals prior work but no lexical match, use last_project from memory
    if prior_cue and best_score < 0.25 and last_path and Path(last_path).exists():
        best_path = last_path
        best_kind = "generated" if "projects" in last_path else "clone"
        best_score = 0.55
        best_signals = ["memory_last_project"]
        best_label = Path(last_path).name
        res.signals.append("fallback_last_project")

    if prior_cue and best_path:
        res.refers_to_prior = True
        res.target_path = best_path
        res.target_kind = best_kind
        res.target_label = best_label
        res.source_request_preview = best_preview
        res.confidence = min(0.95, 0.4 + best_score + (0.15 if prior_cue else 0))
        res.signals.extend(best_signals)
    elif best_score >= 0.35 and best_path:
        # strong match without explicit "السابق" still counts as reference
        res.refers_to_prior = True
        res.target_path = best_path
        res.target_kind = best_kind
        res.target_label = best_label
        res.source_request_preview = best_preview
        res.confidence = min(0.9, best_score + 0.2)
        res.signals.extend(best_signals)
    elif last_path and not res.target_path:
        res.target_path = last_path
        res.confidence = max(res.confidence, 0.25)
        res.signals.append("memory_last_soft")

    return res


class _ContextEngine:
    def resolve(
        self,
        user_id: int,
        text: str,
        *,
        base_dir: str | Path | None = None,
        active_path: str = "",
    ) -> ContextResolution:
        return resolve_context(
            user_id, text, base_dir=base_dir, active_path=active_path
        )


def get_context_engine() -> _ContextEngine:
    return _ContextEngine()


__all__ = [
    "ContextResolution",
    "resolve_context",
    "get_context_engine",
]
