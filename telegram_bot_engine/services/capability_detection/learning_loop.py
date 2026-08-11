"""Phase 6 — Learning Loop.

Promotes frequent capability gaps into:
  1) Dynamic local-KB entries (runtime, persisted)
  2) Draft ResearchSpecs
  3) Draft CapabilityPacks (never auto-registered without emit-safe approve)

Deterministic. No LLM. No codegen from research.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .gap_journal import GapRecord, list_open_gaps, mark_gap_status
from .packs.pipeline import draft_pack_from_research
from .research_spec import ResearchSpec, save_research_spec
from .web_research import research_feature

_LOCK = threading.Lock()


@dataclass
class LearnedKBEntry:
    id: str
    phrases: list[str] = field(default_factory=list)
    title: str = ""
    summary: str = ""
    libraries: list[str] = field(default_factory=list)
    apis: list[str] = field(default_factory=list)
    patterns: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    suggested_service: str = "generic"
    suggested_method: str = "echo"
    hit_count: int = 0
    source: str = "learning_loop"
    created_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LearnedKBEntry":
        return cls(
            id=str(data.get("id") or ""),
            phrases=[str(x) for x in (data.get("phrases") or [])],
            title=str(data.get("title") or ""),
            summary=str(data.get("summary") or ""),
            libraries=[str(x) for x in (data.get("libraries") or [])],
            apis=[str(x) for x in (data.get("apis") or [])],
            patterns=[str(x) for x in (data.get("patterns") or [])],
            keywords=[str(x) for x in (data.get("keywords") or [])],
            risks=[str(x) for x in (data.get("risks") or [])],
            suggested_service=str(data.get("suggested_service") or "generic"),
            suggested_method=str(data.get("suggested_method") or "echo"),
            hit_count=int(data.get("hit_count") or 0),
            source=str(data.get("source") or "learning_loop"),
            created_at=float(data.get("created_at") or 0),
        )


def _data_dir() -> Path:
    base = os.getenv("OUTPUT_DIR") or "/tmp/generated"
    p = Path(base) / "platform" / "learning"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _kb_path() -> Path:
    return _data_dir() / "learned_kb.json"


def load_learned_kb() -> list[LearnedKBEntry]:
    path = _kb_path()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [LearnedKBEntry.from_dict(x) for x in (data if isinstance(data, list) else [])]
    except Exception:
        return []


def save_learned_kb(entries: list[LearnedKBEntry]) -> Path:
    path = _kb_path()
    path.write_text(
        json.dumps([e.to_dict() for e in entries], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def _slug(text: str, max_len: int = 40) -> str:
    s = re.sub(r"[^a-z0-9_]+", "_", (text or "").lower())
    s = re.sub(r"_+", "_", s).strip("_")
    return (s or "learned")[:max_len]


def promote_gap_to_kb(
    gap: GapRecord,
    *,
    research: bool = True,
    min_count: int = 1,
) -> dict[str, Any]:
    """Research a frequent gap and upsert into learned KB + draft pack."""
    if gap.count < min_count:
        return {"ok": False, "reason": "below_min_count", "count": gap.count}

    with _LOCK:
        entries = load_learned_kb()
        entry_id = "learned_" + _slug(gap.phrase or gap.reason)

        result = None
        if research:
            result = research_feature(
                gap.phrase or gap.request_preview,
                reason=gap.reason,
                persist=True,
            )

        spec: ResearchSpec | None = result.spec if result else None
        if not spec:
            spec = ResearchSpec(
                feature_id=entry_id,
                title=gap.phrase or "gap",
                summary=gap.reason,
                status="draft",
                source="learning_loop",
                created_at=time.time(),
                keywords=[w for w in (gap.phrase or "").split() if len(w) > 2][:12],
                risks=["no_codegen_from_raw_research", "learned_from_gap_journal"],
            )
            save_research_spec(spec)

        meta = spec.meta or {}
        phrases = list(dict.fromkeys(
            [gap.phrase] + [w for w in (gap.phrase or "").split() if len(w) > 2]
        ))
        entry = LearnedKBEntry(
            id=entry_id,
            phrases=phrases,
            title=spec.title,
            summary=spec.summary,
            libraries=list(spec.libraries or []),
            apis=list(spec.apis or []),
            patterns=list(spec.patterns or []),
            keywords=list(spec.keywords or []),
            risks=list(spec.risks or []) + ["learned_from_gap_journal"],
            suggested_service=str(meta.get("suggested_service") or "generic"),
            suggested_method=str(meta.get("suggested_method") or "echo"),
            hit_count=gap.count,
            source="learning_loop",
            created_at=time.time(),
        )

        # upsert
        by_id = {e.id: e for e in entries}
        if entry_id in by_id:
            prev = by_id[entry_id]
            entry.hit_count = max(prev.hit_count, gap.count) + 1
            entry.phrases = list(dict.fromkeys(prev.phrases + entry.phrases))
            entry.libraries = list(dict.fromkeys(prev.libraries + entry.libraries))
        by_id[entry_id] = entry
        save_learned_kb(list(by_id.values()))

        # inject into web_research local KB at runtime
        try:
            from . import web_research as wr
            row = {
                "id": entry.id,
                "phrases": tuple(entry.phrases),
                "title": entry.title,
                "summary": entry.summary,
                "libraries": entry.libraries,
                "apis": entry.apis,
                "patterns": entry.patterns,
                "keywords": entry.keywords,
                "suggested_service": entry.suggested_service,
                "suggested_method": entry.suggested_method,
                "risks": entry.risks,
            }
            # replace or append
            found = False
            for i, existing in enumerate(wr._LOCAL_KB):
                if existing.get("id") == entry.id:
                    wr._LOCAL_KB[i] = row
                    found = True
                    break
            if not found:
                wr._LOCAL_KB.append(row)
        except Exception:
            pass

        draft = draft_pack_from_research(
            spec,
            service=entry.suggested_service,
            method=entry.suggested_method,
        )
        # save draft pack json under learning/
        draft_path = _data_dir() / f"draft_{entry.id}.json"
        draft_path.write_text(
            json.dumps(draft.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        mark_gap_status(gap.phrase, gap.reason, "researching")

        return {
            "ok": True,
            "entry": entry.to_dict(),
            "research_spec": spec.to_dict(),
            "draft_pack": draft.to_dict(),
            "draft_path": str(draft_path),
            "kb_path": str(_kb_path()),
        }


def run_learning_cycle(
    *,
    min_count: int = 2,
    limit: int = 10,
    research: bool = True,
) -> dict[str, Any]:
    """Promote open gaps with count >= min_count."""
    promoted: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for gap in list_open_gaps(limit=limit * 3):
        if gap.count < min_count:
            skipped.append({"phrase": gap.phrase, "count": gap.count, "reason": "below_min_count"})
            continue
        if len(promoted) >= limit:
            break
        res = promote_gap_to_kb(gap, research=research, min_count=min_count)
        if res.get("ok"):
            promoted.append(res)
        else:
            skipped.append({"phrase": gap.phrase, "result": res})
    return {
        "ok": True,
        "promoted": len(promoted),
        "skipped": len(skipped),
        "items": promoted,
        "skipped_items": skipped[:20],
        "learned_kb_size": len(load_learned_kb()),
    }


def bootstrap_learned_kb_into_runtime() -> int:
    """Load persisted learned KB into web_research._LOCAL_KB (call on startup)."""
    entries = load_learned_kb()
    if not entries:
        return 0
    try:
        from . import web_research as wr
    except Exception:
        return 0
    n = 0
    for entry in entries:
        row = {
            "id": entry.id,
            "phrases": tuple(entry.phrases),
            "title": entry.title,
            "summary": entry.summary,
            "libraries": entry.libraries,
            "apis": entry.apis,
            "patterns": entry.patterns,
            "keywords": entry.keywords,
            "suggested_service": entry.suggested_service,
            "suggested_method": entry.suggested_method,
            "risks": entry.risks,
        }
        found = False
        for i, existing in enumerate(wr._LOCAL_KB):
            if existing.get("id") == entry.id:
                wr._LOCAL_KB[i] = row
                found = True
                break
        if not found:
            wr._LOCAL_KB.append(row)
        n += 1
    return n


__all__ = [
    "LearnedKBEntry",
    "load_learned_kb",
    "save_learned_kb",
    "promote_gap_to_kb",
    "run_learning_cycle",
    "bootstrap_learned_kb_into_runtime",
]
