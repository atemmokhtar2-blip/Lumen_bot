"""Phase 5 — Web Research Engine (hardened).

Produces ResearchSpec only — NEVER executable code.
Backends (in order):
  1) Local knowledge base for common Telegram-bot gaps
  2) DuckDuckGo Instant Answer API
  3) DuckDuckGo HTML lite (parse result links)
  4) Wikipedia summary API (optional context)

Registration still requires approve_and_register + emit contract.
"""
from __future__ import annotations

import html as html_lib
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

_USER_AGENT = (
    "Mozilla/5.0 (compatible; ai_Agent_7h_bot-research/1.1; +ResearchSpec-only)"
)

_PREFERRED_HOSTS = (
    "docs.python.org",
    "pypi.org",
    "github.com",
    "readthedocs.io",
    "python-telegram-bot.org",
    "docs.python-telegram-bot.org",
    "core.telegram.org",
    "stackoverflow.com",
    "developer.mozilla.org",
    "wikipedia.org",
)

# ---------------------------------------------------------------------------
# Local knowledge — high-signal seeds for frequent gaps (not code emission)
# ---------------------------------------------------------------------------
_LOCAL_KB: list[dict[str, Any]] = [
    {
        "id": "auto_translate",
        "phrases": (
            "ترجم", "ترجمة", "translate", "translation", "auto translate",
            "ترجمة تلقائية", "يترجم الرسائل",
        ),
        "title": "Auto message translation",
        "summary": (
            "Translate incoming chat messages via a translation API or library. "
            "Common stack: deep-translator / googletrans / LibreTranslate HTTP API; "
            "hook on message handler, detect language, reply or edit with translation."
        ),
        "libraries": ["deep-translator", "googletrans", "httpx", "python-telegram-bot"],
        "apis": [
            "https://pypi.org/project/deep-translator/",
            "https://github.com/LibreTranslate/LibreTranslate",
            "https://docs.python-telegram-bot.org/",
        ],
        "patterns": [
            "MessageHandler filter TEXT → detect lang → translate → reply",
            "Optional per-chat toggle stored in DB",
            "Rate-limit external API calls",
        ],
        "keywords": ["ترجمة", "translate", "auto_translate"],
        "suggested_service": "translate",
        "suggested_method": "translate",
        "risks": ["third_party_api_quota", "privacy_of_message_content"],
    },
    {
        "id": "ocr_images",
        "phrases": (
            "ocr", "قراءة صور", "استخراج نص", "image text", "تتعرف على الصورة",
            "تحليل صور", "اقرأ الصورة",
        ),
        "title": "Image OCR for Telegram photos",
        "summary": (
            "Extract text from user-sent photos. Common stack: pytesseract + Pillow, "
            "or cloud Vision APIs. Download photo via Bot API getFile, run OCR, reply text."
        ),
        "libraries": ["pytesseract", "Pillow", "python-telegram-bot"],
        "apis": [
            "https://pypi.org/project/pytesseract/",
            "https://core.telegram.org/bots/api#getfile",
        ],
        "patterns": [
            "MessageHandler PHOTO → download file → OCR → reply",
            "Require tesseract system binary if using pytesseract",
        ],
        "keywords": ["ocr", "صورة", "pytesseract"],
        "suggested_service": "ocr",
        "suggested_method": "ocr_hint",
        "risks": ["system_dependency_tesseract", "large_image_memory"],
    },
    {
        "id": "ai_chat",
        "phrases": (
            "ذكاء اصطناعي", "chatgpt", "openai", "llm", "gpt", "يتعلم",
            "محادثة ذكية", "ai chat",
        ),
        "title": "LLM-backed chat replies",
        "summary": (
            "Forward user text to an LLM HTTP API and return the completion. "
            "Out of zero-AI generator scope for training; integration is API-only."
        ),
        "libraries": ["httpx", "openai", "python-telegram-bot"],
        "apis": [
            "https://platform.openai.com/docs/",
            "https://docs.python-telegram-bot.org/",
        ],
        "patterns": [
            "Store API key in env",
            "MessageHandler → HTTP chat completion → reply",
            "Token budget + moderation filter",
        ],
        "keywords": ["ai", "llm", "openai"],
        "suggested_service": "generic",
        "suggested_method": "echo",
        "risks": ["api_cost", "prompt_injection", "out_of_zero_ai_scope"],
    },
    {
        "id": "payments_stripe",
        "phrases": (
            "stripe", "دفع اونلاين", "بطاقة", "payment gateway", "checkout session",
        ),
        "title": "Card payments via Stripe",
        "summary": (
            "Telegram bots can use Provider tokens or external checkout links. "
            "Stripe Checkout Session + success webhook is a common pattern."
        ),
        "libraries": ["stripe", "python-telegram-bot"],
        "apis": [
            "https://stripe.com/docs/payments/checkout",
            "https://core.telegram.org/bots/payments",
        ],
        "patterns": [
            "Create checkout session → send URL",
            "Webhook confirms payment → unlock feature",
        ],
        "keywords": ["stripe", "payment", "checkout"],
        "suggested_service": "shop",
        "suggested_method": "checkout",
        "risks": ["pci_compliance", "webhook_security"],
    },
    {
        "id": "scheduler_jobs",
        "phrases": (
            "جدولة", "cron", "كل يوم", "تذكير تلقائي", "schedule job", "APScheduler",
        ),
        "title": "Scheduled jobs inside bot process",
        "summary": (
            "Run periodic tasks (reminders, digests). APScheduler or PTB JobQueue."
        ),
        "libraries": ["APScheduler", "python-telegram-bot"],
        "apis": [
            "https://docs.python-telegram-bot.org/en/stable/telegram.ext.jobqueue.html",
            "https://apscheduler.readthedocs.io/",
        ],
        "patterns": [
            "JobQueue.run_repeating / run_daily",
            "Persist job metadata in SQLite",
        ],
        "keywords": ["schedule", "jobqueue", "تذكير"],
        "suggested_service": "scheduler",
        "suggested_method": "schedule_note",
        "risks": ["process_restart_drops_in_memory_jobs"],
    },
]


@dataclass
class ResearchHit:
    title: str
    url: str
    snippet: str = ""
    host: str = ""
    backend: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "host": self.host,
            "backend": self.backend,
        }


@dataclass
class ResearchResult:
    ok: bool
    query: str
    hits: list[ResearchHit] = field(default_factory=list)
    spec: ResearchSpec | None = None
    errors: list[str] = field(default_factory=list)
    source: str = "web"
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "query": self.query,
            "hits": [h.to_dict() for h in self.hits],
            "spec": self.spec.to_dict() if self.spec else None,
            "errors": list(self.errors),
            "source": self.source,
            "confidence": round(self.confidence, 3),
        }


def _slug(text: str, max_len: int = 48) -> str:
    s = re.sub(r"[^a-z0-9_]+", "_", (text or "").lower())
    s = re.sub(r"_+", "_", s).strip("_")
    return (s or "feature")[:max_len]


def _http_get(url: str, *, timeout: float = 10.0) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _score_host(host: str) -> int:
    h = (host or "").lower()
    for i, pref in enumerate(_PREFERRED_HOSTS):
        if pref in h:
            return 100 - i
    return 0


def _rank_hits(hits: list[ResearchHit]) -> list[ResearchHit]:
    return sorted(hits, key=lambda h: (-_score_host(h.host), -len(h.snippet or "")))


def _normalize_query_text(phrase: str) -> str:
    t = (phrase or "").strip()
    # light Arabic → English tech expansion for search backends
    mapping = (
        ("ترجمة", "translate translation"),
        ("ترجم", "translate"),
        ("ذكاء اصطناعي", "AI LLM chatbot"),
        ("قراءة صور", "OCR image text"),
        ("تحليل صور", "image analysis OCR"),
        ("جدولة", "schedule cron jobqueue"),
        ("دفع", "payment checkout"),
        ("تذكير", "reminder schedule"),
    )
    extra: list[str] = []
    low = t.lower()
    for ar, en in mapping:
        if ar in t or ar in low:
            extra.append(en)
    if extra:
        t = f"{t} {' '.join(extra)}"
    return t


# ---- backends --------------------------------------------------------------

def _local_kb_hits(phrase: str) -> tuple[list[ResearchHit], dict[str, Any] | None]:
    text = (phrase or "").lower()
    best: dict[str, Any] | None = None
    best_score = 0
    for row in _LOCAL_KB:
        score = 0
        for p in row["phrases"]:
            if p.lower() in text:
                score += 2 if len(p) > 3 else 1
        if score > best_score:
            best_score = score
            best = row
    if not best or best_score <= 0:
        return [], None
    hits = [
        ResearchHit(
            title=best["title"],
            url=(best.get("apis") or ["local://kb"])[0],
            snippet=best["summary"][:500],
            host="local.kb",
            backend="local_kb",
        )
    ]
    for api in (best.get("apis") or [])[:4]:
        host = urllib.parse.urlparse(api).netloc or "local.kb"
        hits.append(
            ResearchHit(
                title=best["title"],
                url=api,
                snippet=best["summary"][:240],
                host=host,
                backend="local_kb",
            )
        )
    return hits, best


def _duckduckgo_instant(query: str, *, timeout: float = 8.0) -> list[ResearchHit]:
    q = (query or "").strip()
    if not q:
        return []
    url = "https://api.duckduckgo.com/?" + urllib.parse.urlencode(
        {"q": q, "format": "json", "no_html": 1, "skip_disambig": 1}
    )
    try:
        raw = _http_get(url, timeout=timeout)
        data = json.loads(raw)
    except Exception:
        return []
    hits: list[ResearchHit] = []
    abstract = (data.get("AbstractText") or "").strip()
    abs_url = (data.get("AbstractURL") or "").strip()
    abs_src = (data.get("AbstractSource") or "").strip()
    if abstract and abs_url:
        host = urllib.parse.urlparse(abs_url).netloc
        hits.append(
            ResearchHit(
                title=abs_src or "Abstract",
                url=abs_url,
                snippet=abstract[:500],
                host=host,
                backend="ddg_instant",
            )
        )
    for topic in (data.get("RelatedTopics") or [])[:10]:
        if not isinstance(topic, dict) or "Topics" in topic:
            continue
        text = (topic.get("Text") or "").strip()
        furl = (topic.get("FirstURL") or "").strip()
        if not text or not furl:
            continue
        host = urllib.parse.urlparse(furl).netloc
        hits.append(
            ResearchHit(
                title=text[:80],
                url=furl,
                snippet=text[:400],
                host=host,
                backend="ddg_instant",
            )
        )
    return hits


def _duckduckgo_html(query: str, *, timeout: float = 10.0) -> list[ResearchHit]:
    """Parse DuckDuckGo HTML results page for links (best-effort)."""
    q = (query or "").strip()
    if not q:
        return []
    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": q})
    try:
        raw = _http_get(url, timeout=timeout)
    except Exception:
        return []
    hits: list[ResearchHit] = []
    # result links: <a rel="nofollow" class="result__a" href="...">title</a>
    for m in re.finditer(
        r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        raw,
        flags=re.I | re.S,
    ):
        href = html_lib.unescape(m.group(1))
        title = re.sub(r"<[^>]+>", "", html_lib.unescape(m.group(2))).strip()
        # DDG sometimes wraps redirects
        if "uddg=" in href:
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
            href = (qs.get("uddg") or [href])[0]
        if not href.startswith("http"):
            continue
        host = urllib.parse.urlparse(href).netloc
        hits.append(
            ResearchHit(
                title=title[:120] or host,
                url=href,
                snippet=title[:400],
                host=host,
                backend="ddg_html",
            )
        )
        if len(hits) >= 10:
            break
    # snippets
    snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</(?:a|td|div)', raw, flags=re.I | re.S)
    for i, sn in enumerate(snippets[: len(hits)]):
        text = re.sub(r"<[^>]+>", "", html_lib.unescape(sn)).strip()
        if text and i < len(hits):
            hits[i].snippet = text[:400]
    return hits


def _wikipedia_summary(query: str, *, timeout: float = 8.0) -> list[ResearchHit]:
    # Use English Wikipedia REST summary for first token-ish query
    title = (query or "").strip().split()
    if not title:
        return []
    # Prefer a short english topic
    topic = " ".join(title[:6])
    api = "https://en.wikipedia.org/api/rest_v1/page/summary/" + urllib.parse.quote(
        topic.replace(" ", "_")
    )
    try:
        raw = _http_get(api, timeout=timeout)
        data = json.loads(raw)
    except Exception:
        return []
    extract = (data.get("extract") or "").strip()
    page_url = ((data.get("content_urls") or {}).get("desktop") or {}).get("page") or ""
    if not extract:
        return []
    return [
        ResearchHit(
            title=data.get("title") or topic,
            url=page_url or api,
            snippet=extract[:500],
            host="en.wikipedia.org",
            backend="wikipedia",
        )
    ]


def _extract_libraries(text: str) -> list[str]:
    libs: list[str] = []
    stop = {
        "the", "a", "an", "import", "from", "pip", "install", "library", "package",
        "user", "sent", "photos", "via", "bot", "api", "http", "common", "stack",
    }
    for m in re.finditer(
        r"(?:pip install)\s+([a-zA-Z0-9_][a-zA-Z0-9_\-]*)",
        text,
        flags=re.I,
    ):
        name = m.group(1)
        if name.lower() in stop:
            continue
        if name not in libs:
            libs.append(name)
    for known in (
        "deep-translator", "googletrans", "pytesseract", "Pillow", "httpx",
        "openai", "stripe", "APScheduler", "python-telegram-bot", "aiohttp",
        "LibreTranslate", "tesseract",
    ):
        if known.lower() in text.lower() and known not in libs:
            libs.append(known)
    return libs[:14]


def build_research_spec_from_hits(
    *,
    feature_phrase: str,
    reason: str,
    hits: list[ResearchHit],
    query: str,
    kb_row: dict[str, Any] | None = None,
) -> ResearchSpec:
    ranked = _rank_hits(hits)
    snippets = " ".join(h.snippet for h in ranked[:6])
    libs = list(kb_row.get("libraries") or []) if kb_row else []
    for lib in _extract_libraries(snippets):
        if lib not in libs:
            libs.append(lib)
    apis = list(kb_row.get("apis") or []) if kb_row else []
    for h in ranked[:6]:
        if h.url and h.url not in apis:
            apis.append(h.url)
    patterns = list(kb_row.get("patterns") or []) if kb_row else []
    for h in ranked[:5]:
        if h.title and h.title not in patterns:
            patterns.append(h.title[:120])
    risks = list(kb_row.get("risks") or []) if kb_row else []
    risks.extend(
        [
            "requires_human_or_emit_contract_review",
            "no_codegen_from_raw_research",
        ]
    )
    if not any(_score_host(h.host) > 0 or h.backend == "local_kb" for h in ranked):
        risks.append("no_preferred_host_hit")
    risks = list(dict.fromkeys(risks))

    summary_parts = []
    if reason:
        summary_parts.append(reason)
    if kb_row and kb_row.get("summary"):
        summary_parts.append(str(kb_row["summary"]))
    elif ranked:
        summary_parts.append(ranked[0].snippet)
    summary = " | ".join(summary_parts)[:800]

    conf = 0.2
    if kb_row:
        conf += 0.45
    if any(h.backend == "ddg_html" for h in ranked):
        conf += 0.15
    if any(h.backend == "ddg_instant" for h in ranked):
        conf += 0.1
    if any(_score_host(h.host) > 0 for h in ranked):
        conf += 0.15
    conf = min(conf, 0.95)

    return ResearchSpec(
        feature_id=_slug((kb_row or {}).get("id") or feature_phrase),
        title=(kb_row or {}).get("title") or feature_phrase or query,
        summary=summary,
        libraries=libs[:14],
        apis=apis[:10],
        patterns=patterns[:10],
        risks=risks,
        keywords=list(
            dict.fromkeys(
                list((kb_row or {}).get("keywords") or [])
                + [w for w in re.split(r"\s+", feature_phrase or query) if len(w) > 2]
            )
        )[:16],
        status="draft",
        source="web" if not kb_row else "local_kb+web",
        created_at=time.time(),
        meta={
            "query": query,
            "hit_count": len(ranked),
            "hosts": list(dict.fromkeys(h.host for h in ranked if h.host))[:12],
            "backends": list(dict.fromkeys(h.backend for h in ranked if h.backend)),
            "confidence": conf,
            "suggested_service": (kb_row or {}).get("suggested_service"),
            "suggested_method": (kb_row or {}).get("suggested_method"),
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
    if allow_network is None:
        allow_network = os.getenv("CAPABILITY_RESEARCH_OFFLINE", "").strip() not in {
            "1", "true", "yes",
        }

    expanded = _normalize_query_text(phrase)
    query = " ".join(
        x for x in [expanded, "python telegram bot", extra_query] if x
    ).strip()

    hits: list[ResearchHit] = []
    errors: list[str] = []
    kb_row: dict[str, Any] | None = None

    # 1) Local KB always (works offline)
    local_hits, kb_row = _local_kb_hits(phrase + " " + reason)
    hits.extend(local_hits)

    if allow_network:
        for backend_fn, label in (
            (_duckduckgo_instant, "ddg_instant"),
            (lambda q: _duckduckgo_html(q + " python telegram"), "ddg_html"),
            (_wikipedia_summary, "wikipedia"),
        ):
            try:
                more = backend_fn(query if label != "wikipedia" else expanded)
                hits.extend(more)
            except Exception as exc:
                errors.append(f"{label}:{type(exc).__name__}")
    else:
        errors.append("offline_mode")

    # de-dupe by URL
    seen_url: set[str] = set()
    uniq: list[ResearchHit] = []
    for h in hits:
        key = (h.url or h.title).strip()
        if not key or key in seen_url:
            continue
        seen_url.add(key)
        uniq.append(h)
    hits = _rank_hits(uniq)

    if not hits and not kb_row:
        spec = ResearchSpec(
            feature_id=_slug(phrase),
            title=phrase or "unknown",
            summary=reason or "no research hits",
            status="draft",
            source="web_empty",
            created_at=time.time(),
            keywords=[w for w in (phrase or "").split() if len(w) > 2][:12],
            risks=["no_web_hits", "no_codegen_from_raw_research"],
            meta={"query": query},
        )
        if persist:
            save_research_spec(spec)
        return ResearchResult(
            ok=False, query=query, hits=[], spec=spec, errors=errors or ["no_hits"],
            source=spec.source, confidence=0.1,
        )

    spec = build_research_spec_from_hits(
        feature_phrase=phrase,
        reason=reason,
        hits=hits,
        query=query,
        kb_row=kb_row,
    )
    if persist:
        save_research_spec(spec)
    conf = float((spec.meta or {}).get("confidence") or 0.5)
    return ResearchResult(
        ok=True,
        query=query,
        hits=hits[:12],
        spec=spec,
        errors=errors,
        source=spec.source,
        confidence=conf,
    )


def research_open_gaps(*, limit: int = 5, persist: bool = True) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for gap in list_open_gaps(limit=limit):
        result = research_feature(gap.phrase, reason=gap.reason, persist=persist)
        draft = None
        if result.spec:
            meta = result.spec.meta or {}
            draft = draft_pack_from_research(
                result.spec,
                service=str(meta.get("suggested_service") or "generic"),
                method=str(meta.get("suggested_method") or "echo"),
            )
        out.append({
            "gap": gap.to_dict() if isinstance(gap, GapRecord) else gap,
            "research": result.to_dict(),
            "draft_pack": draft.to_dict() if draft else None,
        })
    return out


def research_for_detection_gaps(
    gaps: list[Any],
    *,
    request: str = "",
    limit: int = 3,
    persist: bool = True,
) -> list[dict[str, Any]]:
    """Helper for preflight/integration: research top gap phrases."""
    out: list[dict[str, Any]] = []
    for g in (gaps or [])[:limit]:
        phrase = str(getattr(g, "phrase", None) or (g.get("phrase") if isinstance(g, dict) else "") or "")
        reason = str(getattr(g, "reason", None) or (g.get("reason") if isinstance(g, dict) else "") or "")
        if not phrase and not reason:
            continue
        result = research_feature(phrase or request, reason=reason, persist=persist)
        out.append(result.to_dict())
    return out


__all__ = [
    "ResearchHit",
    "ResearchResult",
    "research_feature",
    "research_open_gaps",
    "research_for_detection_gaps",
    "build_research_spec_from_hits",
]
