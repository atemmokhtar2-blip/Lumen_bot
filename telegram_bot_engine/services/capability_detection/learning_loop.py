"""Phase 6 — Learning Loop (hardened).

Promotes frequent capability gaps into:
  1) Dynamic local-KB entries (persisted + runtime)
  2) Draft ResearchSpecs
  3) Draft CapabilityPacks (never auto-registered)

Triggers:
  - Explicit: run_learning_cycle / promote_gap_to_kb
  - Automatic: maybe_auto_learn() after gap journal writes (threshold)

Deterministic. No LLM. No codegen from research.
"""
from __future__ import annotations

import hashlib
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
_AUTO_LAST_RUN = 0.0
_AUTO_COOLDOWN_SEC = 30.0


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
    updated_at: float = 0.0
    status: str = "active"  # active | retired

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
            updated_at=float(data.get("updated_at") or 0),
            status=str(data.get("status") or "active"),
        )


def _data_dir() -> Path:
    base = os.getenv("OUTPUT_DIR") or "/tmp/generated"
    p = Path(base) / "platform" / "learning"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _kb_path() -> Path:
    return _data_dir() / "learned_kb.json"


def _stats_path() -> Path:
    return _data_dir() / "learning_stats.json"


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


def learning_stats() -> dict[str, Any]:
    entries = load_learned_kb()
    drafts = list(_data_dir().glob("draft_*.json"))
    open_gaps = list_open_gaps(limit=200)
    return {
        "learned_entries": len(entries),
        "active_entries": sum(1 for e in entries if e.status == "active"),
        "draft_packs": len(drafts),
        "open_gaps": len(open_gaps),
        "top_gaps": [
            {"phrase": g.phrase, "count": g.count, "status": g.status}
            for g in open_gaps[:10]
        ],
        "kb_path": str(_kb_path()),
        "data_dir": str(_data_dir()),
    }


def _entry_id_for_phrase(phrase: str) -> str:
    """Stable id that works for Arabic (hash + short slug)."""
    raw = (phrase or "").strip().lower()
    # keep arabic letters in a readable suffix when possible
    readable = re.sub(r"[^\w\u0600-\u06FF]+", "_", raw, flags=re.UNICODE)
    readable = re.sub(r"_+", "_", readable).strip("_")[:24]
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]
    if readable and not readable.isdigit():
        return f"learned_{digest}_{readable}"
    return f"learned_{digest}"


def _normalize_phrase(phrase: str) -> str:
    t = (phrase or "").strip().lower()
    t = re.sub(r"\s+", " ", t)
    # light stem-ish collapse for Arabic common prefixes
    for pref in ("ال",):
        if t.startswith(pref) and len(t) > len(pref) + 2:
            t = t[len(pref) :]
    return t


def _phrase_tokens(phrase: str) -> list[str]:
    parts = re.split(r"[\s_]+", _normalize_phrase(phrase))
    return [p for p in parts if len(p) >= 2]


def _related_gap_cluster(seed: GapRecord, pool: list[GapRecord]) -> list[GapRecord]:
    """Merge gaps that share tokens or substring relation."""
    seed_n = _normalize_phrase(seed.phrase)
    seed_toks = set(_phrase_tokens(seed.phrase))
    cluster = [seed]
    for g in pool:
        if g is seed:
            continue
        gn = _normalize_phrase(g.phrase)
        if not gn:
            continue
        if seed_n and (seed_n in gn or gn in seed_n):
            cluster.append(g)
            continue
        gt = set(_phrase_tokens(g.phrase))
        if seed_toks and gt and len(seed_toks & gt) >= 1:
            cluster.append(g)
    return cluster


def _phrases_from_gap(gap: GapRecord) -> list[str]:
    out: list[str] = []
    if gap.phrase:
        out.append(gap.phrase.strip())
    # pull useful tokens from request preview
    prev = gap.request_preview or ""
    for tok in re.split(r"\s+", prev):
        tok = tok.strip()
        if len(tok) >= 3 and tok not in out:
            # skip pure fillers
            if tok in {"بوت", "bot", "فقط", "عايز", "أريد", "مع", "من"}:
                continue
            out.append(tok)
        if len(out) >= 12:
            break
    # tokenized phrase parts
    for t in _phrase_tokens(gap.phrase):
        if t not in out:
            out.append(t)
    return list(dict.fromkeys(out))


def promote_gap_to_kb(
    gap: GapRecord,
    *,
    research: bool = True,
    min_count: int = 1,
    cluster: bool = True,
) -> dict[str, Any]:
    """Research a frequent gap (optionally clustered) and upsert learned KB + draft pack."""
    if gap.count < min_count and not cluster:
        return {"ok": False, "reason": "below_min_count", "count": gap.count}

    with _LOCK:
        entries = load_learned_kb()
        pool = list_open_gaps(limit=100)
        related = _related_gap_cluster(gap, pool) if cluster else [gap]
        total_count = sum(g.count for g in related)
        if total_count < min_count:
            return {
                "ok": False,
                "reason": "below_min_count",
                "count": total_count,
                "cluster_size": len(related),
            }

        # pick richest phrase for research
        primary = max(related, key=lambda g: (g.count, len(g.phrase or "")))
        entry_id = _entry_id_for_phrase(primary.phrase or primary.reason)

        result = None
        if research:
            result = research_feature(
                primary.phrase or primary.request_preview,
                reason=primary.reason,
                persist=True,
            )

        spec: ResearchSpec | None = result.spec if result else None
        if not spec:
            spec = ResearchSpec(
                feature_id=entry_id,
                title=primary.phrase or "gap",
                summary=primary.reason,
                status="draft",
                source="learning_loop",
                created_at=time.time(),
                keywords=_phrase_tokens(primary.phrase)[:12],
                risks=["no_codegen_from_raw_research", "learned_from_gap_journal"],
            )
            save_research_spec(spec)

        meta = spec.meta or {}
        phrases: list[str] = []
        for g in related:
            phrases.extend(_phrases_from_gap(g))
        phrases = list(dict.fromkeys(phrases))

        now = time.time()
        entry = LearnedKBEntry(
            id=entry_id,
            phrases=phrases,
            title=spec.title,
            summary=spec.summary,
            libraries=list(spec.libraries or []),
            apis=list(spec.apis or []),
            patterns=list(spec.patterns or []),
            keywords=list(dict.fromkeys(list(spec.keywords or []) + phrases))[:20],
            risks=list(dict.fromkeys(list(spec.risks or []) + ["learned_from_gap_journal"])),
            suggested_service=str(meta.get("suggested_service") or "generic"),
            suggested_method=str(meta.get("suggested_method") or "echo"),
            hit_count=total_count,
            source="learning_loop",
            created_at=now,
            updated_at=now,
            status="active",
        )

        by_id = {e.id: e for e in entries}
        # also merge if same normalized phrase already learned under other id
        for existing in entries:
            if existing.id == entry_id:
                continue
            if set(_phrase_tokens(existing.title)) & set(_phrase_tokens(entry.title)):
                entry.phrases = list(dict.fromkeys(existing.phrases + entry.phrases))
                entry.libraries = list(dict.fromkeys(existing.libraries + entry.libraries))
                entry.hit_count = max(existing.hit_count, entry.hit_count)
                entry.created_at = existing.created_at or now
                by_id.pop(existing.id, None)

        if entry_id in by_id:
            prev = by_id[entry_id]
            entry.created_at = prev.created_at or now
            entry.hit_count = max(prev.hit_count, total_count)
            entry.phrases = list(dict.fromkeys(prev.phrases + entry.phrases))
            entry.libraries = list(dict.fromkeys(prev.libraries + entry.libraries))
            entry.apis = list(dict.fromkeys(prev.apis + entry.apis))
        by_id[entry_id] = entry
        save_learned_kb(list(by_id.values()))

        _inject_entry_into_runtime(entry)

        draft = draft_pack_from_research(
            spec,
            service=entry.suggested_service if entry.suggested_service in {
                "generic", "content", "utils", "shop", "reminders", "core"
            } else "generic",
            method=entry.suggested_method if entry.suggested_method in {
                "echo", "announce", "start", "help"
            } else "echo",
        )
        draft_path = _data_dir() / f"draft_{entry.id}.json"
        draft_path.write_text(
            json.dumps(draft.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        for g in related:
            mark_gap_status(g.phrase, g.reason, "researching")

        _write_stats_event("promote", entry.id, total_count)

        return {
            "ok": True,
            "entry": entry.to_dict(),
            "research_spec": spec.to_dict(),
            "draft_pack": draft.to_dict(),
            "draft_path": str(draft_path),
            "kb_path": str(_kb_path()),
            "cluster_size": len(related),
            "cluster_phrases": [g.phrase for g in related],
        }


def _inject_entry_into_runtime(entry: LearnedKBEntry) -> None:
    try:
        from . import web_research as wr
    except Exception:
        return
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
    for i, existing in enumerate(wr._LOCAL_KB):
        if existing.get("id") == entry.id:
            wr._LOCAL_KB[i] = row
            return
    wr._LOCAL_KB.append(row)


def _write_stats_event(kind: str, entry_id: str, count: int) -> None:
    try:
        path = _stats_path()
        events = []
        if path.is_file():
            events = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(events, list):
                events = []
        events.append({
            "ts": time.time(),
            "kind": kind,
            "entry_id": entry_id,
            "count": count,
        })
        path.write_text(json.dumps(events[-200:], ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def run_learning_cycle(
    *,
    min_count: int = 2,
    limit: int = 10,
    research: bool = True,
) -> dict[str, Any]:
    """Promote open gaps with cluster count >= min_count."""
    promoted: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    seen_phrases: set[str] = set()
    for gap in list_open_gaps(limit=limit * 5):
        norm = _normalize_phrase(gap.phrase)
        if norm in seen_phrases:
            continue
        res = promote_gap_to_kb(
            gap, research=research, min_count=min_count, cluster=True
        )
        if res.get("ok"):
            for p in res.get("cluster_phrases") or [gap.phrase]:
                seen_phrases.add(_normalize_phrase(p))
            promoted.append(res)
        else:
            skipped.append({"phrase": gap.phrase, "result": res})
        if len(promoted) >= limit:
            break
    _write_stats_event("cycle", f"n={len(promoted)}", len(promoted))
    return {
        "ok": True,
        "promoted": len(promoted),
        "skipped": len(skipped),
        "items": promoted,
        "skipped_items": skipped[:20],
        "learned_kb_size": len(load_learned_kb()),
        "stats": learning_stats(),
    }


def maybe_auto_learn(*, force: bool = False) -> dict[str, Any] | None:
    """Auto-run learning cycle if enabled and cooldown elapsed.

    Env:
      CAPABILITY_LEARNING_AUTO=1 (default on)
      CAPABILITY_LEARNING_MIN_COUNT=2
      CAPABILITY_LEARNING_COOLDOWN=30
    """
    global _AUTO_LAST_RUN
    enabled = os.getenv("CAPABILITY_LEARNING_AUTO", "1").strip().lower() in {
        "1", "true", "yes",
    }
    if not enabled and not force:
        return None
    try:
        cooldown = float(os.getenv("CAPABILITY_LEARNING_COOLDOWN") or _AUTO_COOLDOWN_SEC)
    except ValueError:
        cooldown = _AUTO_COOLDOWN_SEC
    now = time.time()
    if not force and (now - _AUTO_LAST_RUN) < cooldown:
        return {"ok": True, "skipped": True, "reason": "cooldown"}
    try:
        min_count = int(os.getenv("CAPABILITY_LEARNING_MIN_COUNT") or "2")
    except ValueError:
        min_count = 2
    _AUTO_LAST_RUN = now
    return run_learning_cycle(min_count=min_count, limit=5, research=True)


def bootstrap_learned_kb_into_runtime() -> int:
    entries = [e for e in load_learned_kb() if e.status == "active"]
    if not entries:
        return 0
    for entry in entries:
        _inject_entry_into_runtime(entry)
    return len(entries)


def list_draft_packs() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for path in sorted(_data_dir().glob("draft_*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            out.append({"path": str(path), "pack": data})
        except Exception:
            continue
    return out


__all__ = [
    "LearnedKBEntry",
    "load_learned_kb",
    "save_learned_kb",
    "learning_stats",
    "promote_gap_to_kb",
    "run_learning_cycle",
    "maybe_auto_learn",
    "bootstrap_learned_kb_into_runtime",
    "list_draft_packs",
]
