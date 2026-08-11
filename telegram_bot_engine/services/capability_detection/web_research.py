"""Phase 5 — Web Research Engine (ResearchSpec only).

Hard rules:
- Output is ResearchSpec / structured notes — NEVER executable code.
- Prefer trusted sources patterns; no arbitrary code execution.
- Results stay draft until approve_and_register (emit contract).
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from .gap_journal import GapRecord, list_open_gaps
from .packs.pipeline import draft_pack_from_research
from .research_spec import ResearchSpec, save_research_spec

# Allowlist-ish host fragments (best-effort; not a security boundary alone)
_PREFERRED_HOSTS = (
    "docs.python.org",
    "pypi.org",
    "github.com",
    "readthedocs.io",
    "python-telegram-bot.org",
    "core.telegram.org",
    "stackoverflow.com",
    "developer.mozilla.org",
)

_USER_AGENT = "ai_Agent_7h_bot-research/1.0 (+local; ResearchSpec only)"


@dataclass
class ResearchHit:
    title: str
    url: str
    snippet: str = ""
    host: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"title": self.title, "url": self.url, "snippet": self.snippet, "host": self.host}


@dataclass
class ResearchResult:
    ok: bool
    query: str
    hits: list[ResearchHit] = field(default_factory=list)
    spec: ResearchSpec | None = None
    errors: list[str] = field(default_factory=list)
    source: str = "web"

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "query": self.query,
            "hits": [h.to_dict() for h in self.hits],
            "spec": self.spec.to_dict() if self.spec else None,
            "errors": list(self.errors),
            "source": self.source,
        }


def _slug(text: str, max_len: int = 48) -> str:
    s = re.sub(r"[^a-z0-9_]+", "_", (text or "").lower())
    s = re.sub(r"_+", "_", s).strip("_")
    return (s or "feature")[:max_len]


def _duckduckgo_instant(query: str, *, timeout: float = 8.0) -> list[ResearchHit]:
    """Use DuckDuckGo Instant Answer API (no key). Best-effort."""
    q = (query or "").strip()
    if not q:
        return []
    url = "https://api.duckduckgo.com/?" + urllib.parse.urlencode(
        {"q": q, "format": "json", "no_html": 1, "skip_disambig": 1}
    )
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        data = json.loads(raw)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
        return []

    hits: list[ResearchHit] = []
    abstract = (data.get("AbstractText") or "").strip()
    abs_url = (data.get("AbstractURL") or "").strip()
    abs_src = (data.get("AbstractSource") or "").strip()
    if abstract and abs_url:
        host = urllib.parse.urlparse(abs_url).netloc
        hits.append(ResearchHit(title=abs_src or "Abstract", url=abs_url, snippet=abstract[:500], host=host))

    for topic in (data.get("RelatedTopics") or [])[:8]:
        if not isinstance(topic, dict):
            continue
        if "Topics" in topic:  # nested group
            continue
        text = (topic.get("Text") or "").strip()
        furl = (topic.get("FirstURL") or "").strip()
        if not text or not furl:
            continue
        host = urllib.parse.urlparse(furl).netloc
        hits.append(ResearchHit(title=text[:80], url=furl, snippet=text[:400], host=host))
    return hits


def _score_host(host: str) -> int:
    h = (host or "").lower()
    for i, pref in enumerate(_PREFERRED_HOSTS):
        if pref in h:
            return 100 - i
    return 0


def _rank_hits(hits: list[ResearchHit]) -> list[ResearchHit]:
    return sorted(hits, key=lambda h: (-_score_host(h.host), -len(h.snippet)))


def _extract_libraries(text: str) -> list[str]:
    libs: list[str] = []
    # simple patterns: pip install X, import X
    for m in re.finditer(r"(?:pip install|import|from)\s+([a-zA-Z0-9_\-]+)", text):
        name = m.group(1).lower()
        if name in {"the", "a", "an", "import", "from", "pip", "install"}:
            continue
        if name not in libs:
            libs.append(name)
    return libs[:12]


def build_research_spec_from_hits(
    *,
    feature_phrase: str,
    reason: str,
    hits: list[ResearchHit],
    query: str,
) -> ResearchSpec:
    ranked = _rank_hits(hits)
    snippets = " ".join(h.snippet for h in ranked[:5])
    libs = _extract_libraries(snippets)
    patterns = [h.title for h in ranked[:6] if h.title]
    risks = [
        "requires_human_or_emit_contract_review",
        "no_codegen_from_raw_research",
        "sources_may_be_incomplete",
    ]
    if not any(_score_host(h.host) > 0 for h in ranked):
        risks.append("no_preferred_host_hit")

    return ResearchSpec(
        feature_id=_slug(feature_phrase),
        title=feature_phrase or query,
        summary=(reason + " | " + (ranked[0].snippet if ranked else ""))[:600],
        libraries=libs,
        apis=[h.url for h in ranked[:5]],
        patterns=patterns,
        risks=risks,
        keywords=[w for w in re.split(r"\s+", feature_phrase or query) if len(w) > 2][:12],
        status="draft",
        source="web",
        created_at=time.time(),
        meta={
            "query": query,
            "hit_count": len(ranked),
            "hosts": list(dict.fromkeys(h.host for h in ranked if h.host))[:10],
        },
    )


def research_feature(
    phrase: str,
    *,
    reason: str = "",
    extra_query: str = "",
    persist: bool = True,
    allow_network: bool | None = None,
) -> ResearchResult:
    """Research a capability gap. Network can be disabled via CAPABILITY_RESEARCH_OFFLINE=1."""
    if allow_network is None:
        allow_network = os.getenv("CAPABILITY_RESEARCH_OFFLINE", "").strip() not in {"1", "true", "yes"}

    query = " ".join(
        x for x in [
            phrase,
            "python telegram bot",
            extra_query,
            reason[:80] if reason else "",
        ] if x
    ).strip()

    hits: list[ResearchHit] = []
    errors: list[str] = []
    if allow_network:
        try:
            hits = _duckduckgo_instant(query)
        except Exception as exc:
            errors.append(f"network:{type(exc).__name__}")
    else:
        errors.append("offline_mode")

    # Offline / empty fallback: still produce a draft spec from the gap text
    if not hits:
        spec = ResearchSpec(
            feature_id=_slug(phrase),
            title=phrase or "unknown",
            summary=reason or "no web hits",
            status="draft",
            source="web_offline" if not allow_network else "web_empty",
            created_at=time.time(),
            keywords=[w for w in (phrase or "").split() if len(w) > 2][:12],
            risks=["no_web_hits", "no_codegen_from_raw_research"],
            meta={"query": query},
        )
        if persist:
            save_research_spec(spec)
        return ResearchResult(ok=False, query=query, hits=[], spec=spec, errors=errors or ["no_hits"], source=spec.source)

    spec = build_research_spec_from_hits(
        feature_phrase=phrase, reason=reason, hits=hits, query=query
    )
    if persist:
        save_research_spec(spec)
    return ResearchResult(ok=True, query=query, hits=_rank_hits(hits)[:10], spec=spec, errors=errors, source="web")


def research_open_gaps(*, limit: int = 5, persist: bool = True) -> list[dict[str, Any]]:
    """Research top open gaps → ResearchSpec + optional draft pack (not registered)."""
    out: list[dict[str, Any]] = []
    for gap in list_open_gaps(limit=limit):
        result = research_feature(gap.phrase, reason=gap.reason, persist=persist)
        draft = None
        if result.spec:
            # Default draft uses safe echo — human must upgrade service/method
            draft = draft_pack_from_research(result.spec, service="generic", method="echo")
        out.append({
            "gap": gap.to_dict() if isinstance(gap, GapRecord) else gap,
            "research": result.to_dict(),
            "draft_pack": draft.to_dict() if draft else None,
        })
    return out


__all__ = [
    "ResearchHit",
    "ResearchResult",
    "research_feature",
    "research_open_gaps",
    "build_research_spec_from_hits",
]
