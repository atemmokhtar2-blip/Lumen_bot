"""Authoritative multi-domain detector (zero-AI, deterministic).

Phase A foundation
------------------
This module is the *root signal* for what vertical a user request belongs to.
Downstream preset stacking and capability suites MUST respect:

* ``decide(text).primary`` — winning domain (or None)
* ``decide(text).blocked_presets`` — presets that must not enter the stack
* ``decide(text).allowed_domains`` — domains extractors may expand

Design rules
------------
1. Ambiguous Arabic/English tokens (موعد، تذكير، reminder…) never open a
   vertical by themselves — they need domain anchors.
2. A first-class ``tasks`` domain captures todo/reminder bots.
3. When ``tasks`` wins with strong evidence, clinic/booking/shop are blocked
   at the domain layer (not left for later stages to "maybe" clean up).
4. Matching is longest-phrase-first to prefer «موعد المهمة» over «موعد».
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class DomainHit:
    domain: str
    score: float
    matched: tuple[str, ...]
    hard_count: float = 0.0
    ambig_count: float = 0.0


@dataclass(frozen=True)
class DomainDecision:
    """Authoritative output consumed by composer / extractors / presets."""

    primary: str | None
    hits: tuple[DomainHit, ...]
    allowed_domains: tuple[str, ...]
    blocked_presets: frozenset[str] = field(default_factory=frozenset)
    blocked_domains: frozenset[str] = field(default_factory=frozenset)
    confidence: float = 0.0  # 0..1
    reason: str = ""

    @property
    def domains(self) -> list[str]:
        return list(self.allowed_domains)


# Shared tokens that must never open a vertical alone.
_AMBIGUOUS: frozenset[str] = frozenset(
    {
        "موعد",
        "مواعيد",
        "تذكير",
        "تذكيرات",
        "ذكرني",
        "reminder",
        "remind",
        "deadline",
        "notification",
        "إشعار",
        "اشعار",
        "طلب",  # order vs request
    }
)

# Presets that collide with a pure tasks intent.
_TASKS_BLOCKS_PRESETS: frozenset[str] = frozenset(
    {
        "clinic",
        "booking",
        "shop",
        "commerce_pro",
        "marketplace",
        "restaurant",
        "hr",
        "fitness",
    }
)

_TASKS_BLOCKS_DOMAINS: frozenset[str] = frozenset(
    {
        "healthcare",
        "ecommerce",
        "marketplace",
        "hr",
        "fitness",
    }
)


DOMAINS: dict[str, dict[str, Any]] = {
    "group_moderation": {
        "keywords": (
            "إدارة جروبات", "ادارة جروبات", "إدارة مجموعات", "ادارة مجموعات",
            "إدارة جروب", "ادارة جروب", "مشرفين", "مشرف المجموعة",
            "group admin", "group management", "moderation bot",
            "حظر أعضاء", "طرد أعضاء", "كتم أعضاء", "نظام تحذيرات",
            "حماية الجروب", "حماية المجموعة", "anti spam", "مضاد سبام",
            "حذف الروابط", "منع الروابط", "ترحيب تلقائي",
            "سجل إداري", "صلاحيات الأدمن", "pubg", "ببجي",
        ),
        "ambiguous": ("جروب", "مجموعة", "أدمن", "ادمن", "مشرف", "حظر", "كتم", "طرد"),
        "anchors": (
            "إدارة جروب", "ادارة جروب", "إدارة مجموعات", "group admin",
            "حظر", "كتم", "طرد", "تحذير", "ترحيب", "سبام", "روابط",
            "مشرفين", "moderation", "pubg", "ببجي",
        ),
        "weight": 2.8,
        "min_score": 1.5,
        "preset": "group_management",
    },
    "tasks": {
        "keywords": (
            "قائمة المهام",
            "قائمة مهام",
            "اضافة مهمة",
            "إضافة مهمة",
            "اضف مهمة",
            "أضف مهمة",
            "حذف مهمة",
            "امسح مهمة",
            "إنهاء مهمة",
            "انهاء مهمة",
            "تمت المهمة",
            "موعد المهمة",
            "موعد مهمه",
            "تذكير بالمهمة",
            "تذكير بالمهام",
            "ذكرني بالمهمة",
            "add task",
            "delete task",
            "remove task",
            "complete task",
            "task list",
            "task reminder",
            "to-do",
            "to do",
            "todo list",
            "مهام",
            "مهمة",
            "مهمه",
            "todo",
            "task",
            "tasks",
        ),
        "ambiguous": (
            "موعد",
            "مواعيد",
            "تذكير",
            "تذكيرات",
            "ذكرني",
            "reminder",
            "remind",
            "deadline",
        ),
        "anchors": (
            "مهام",
            "مهمة",
            "مهمه",
            "todo",
            "task",
            "tasks",
            "قائمة مهام",
            "قائمة المهام",
            "to-do",
        ),
        "weight": 3.5,
        "min_score": 1,
        "preset": "tasks",
    },
    "cybersecurity": {
        "keywords": (
            "security", "cyber", "cybersecurity", "cyberguard", "أمن", "امن", "سيبراني",
            "فحص أمني", "ثغرة", "phishing", "تصيد", "تصيّد", "dns", "tls", "ssl",
            "spf", "dmarc", "mx records", "security headers", "domain scan",
            "website scan", "soc", "incident", "vulnerability", "pentest",
            "certificate", "شهادة ssl", "نصائح أمان", "توعية أمنية",
        ),
        "weight": 3.0,
        "min_score": 1,
        "preset": "security_ops",
    },
    "iot": {
        "keywords": (
            "iot", "إنترنت الأشياء", "انترنت الاشياء", "أجهزة ذكية", "اجهزة ذكية",
            "smart devices", "smart home", "sensors", "حساسات", "مستشعرات",
            "mqtt", "home automation", "أتمتة منزلية", "arduino", "esp32",
            "raspberry", "telemetry", "تلمتري",
        ),
        "weight": 2.6,
        "min_score": 1,
        "preset": "iot",
    },
    "blockchain": {
        "keywords": (
            "blockchain", "بلوك تشين", "بلوكتشين", "crypto", "عملة رقمية",
            "bitcoin", "بيتكوين", "ethereum", "إيثريوم", "smart contract",
            "عقد ذكي", "nft", "defi", "web3",
        ),
        "weight": 2.5,
        "min_score": 1,
        "preset": "blockchain",
    },
    "ai_ml": {
        "keywords": (
            "ذكاء اصطناعي", "الذكاء الاصطناعي", "machine learning", "تعلم آلي",
            "chatgpt", "gpt", "openai", "nlp", "deep learning", "llm",
        ),
        # bare "ai" is too noisy — kept out on purpose
        "weight": 2.4,
        "min_score": 1,
        "preset": "ai_assistant",
    },
    "devops": {
        "keywords": (
            "devops", "ci/cd", "cicd", "pipeline", "docker", "kubernetes", "k8s",
            "deploy", "نشر", "terraform", "monitoring", "مراقبة",
        ),
        "weight": 2.4,
        "min_score": 1,
        "preset": "devops",
    },
    "healthcare": {
        "keywords": (
            "موعد طبي",
            "حجز موعد طبي",
            "مواعيد العيادة",
            "medical records",
            "سجلات طبية",
            "healthcare",
            "hospital",
            "مستشفى",
            "عيادة",
            "clinic",
            "doctor",
            "دكتور",
            "طبيب",
            "patient",
            "مريض",
            "prescription",
            "وصفة",
            "pharmacy",
            "صيدلية",
            "مختبر",
            "طبي",
            "صحي",
            "medical",
        ),
        "ambiguous": ("موعد", "مواعيد", "تذكير", "reminder", "حجز موعد", "حجز"),
        "anchors": (
            "طبي", "صحي", "medical", "healthcare", "hospital", "مستشفى",
            "عيادة", "clinic", "doctor", "دكتور", "طبيب", "patient", "مريض",
            "وصفة", "pharmacy", "صيدلية", "موعد طبي", "حجز موعد طبي",
        ),
        "weight": 2.5,
        "min_score": 1,
        "preset": "clinic",
    },
    "education": {
        "keywords": (
            "تعليم", "education", "course", "دورة", "كورس", "quiz", "اختبار",
            "امتحان", "student", "طالب", "teacher", "معلم", "lesson", "درس",
            "homework", "واجب",
        ),
        "weight": 2.0,
        "min_score": 1,
        "preset": "education",
    },
    "ecommerce": {
        "keywords": (
            "ecommerce", "shop", "store", "متجر", "بيع", "products", "منتجات",
            "سلة", "cart", "كتالوج", "catalog", "checkout",
        ),
        "ambiguous": ("طلب",),
        "anchors": (
            "shop", "store", "متجر", "بيع", "products", "منتجات", "ecommerce",
            "سلة", "cart", "كتالوج", "catalog", "checkout",
        ),
        "weight": 1.8,
        "min_score": 2,
        "preset": "shop",
    },
    "marketplace": {
        "keywords": (
            "marketplace", "سوق متعدد", "multi-vendor", "بائعين", "vendor",
            "escrow", "affiliate", "عمولة", "dropshipping", "مزاد", "auction",
        ),
        "weight": 2.3,
        "min_score": 1,
        "preset": "marketplace",
    },
    "finance": {
        "keywords": (
            "مالية", "finance", "محاسبة", "accounting", "bank", "بنك",
            "invoice", "فاتورة", "budget", "ميزانية", "tax", "ضريبة",
        ),
        "weight": 2.2,
        "min_score": 1,
        "preset": "finance",
    },
    "logistics": {
        "keywords": (
            "لوجستيات", "logistics", "شحن", "shipping", "delivery", "توصيل",
            "warehouse", "مستودع", "inventory", "مخزون", "tracking", "تتبع",
        ),
        "weight": 2.1,
        "min_score": 1,
        "preset": "logistics",
    },
    "gaming": {
        "keywords": (
            "game", "لعبة", "ألعاب", "العاب", "multiplayer", "leaderboard",
            "achievement", "tournament", "بطولة",
        ),
        "weight": 2.0,
        "min_score": 1,
        "preset": "gaming",
    },
    "social": {
        "keywords": (
            "social media", "وسائل التواصل", "community", "مجتمع", "forum",
            "منتدى", "منشور", "timeline", "news feed",
        ),
        "weight": 1.7,
        "min_score": 2,
        "preset": "community",
    },
    "projects": {
        "keywords": (
            "project management", "إدارة مشاريع", "ادارة مشاريع",
            "projects", "project", "مشاريع", "مشروع",
        ),
        "weight": 1.6,
        "min_score": 1,
        "preset": "tasks",
    },
    "saas": {
        "keywords": (
            "saas", "multi-tenant", "workspace", "tenant", "rbac", "quota",
            "منصة برمجية", "feature flag",
        ),
        "weight": 2.2,
        "min_score": 1,
        "preset": "saas",
    },
    "hr": {
        "keywords": (
            "موارد بشرية", "hr", "إجازة", "اجازة", "payroll", "رواتب",
            "employee", "موظف",
        ),
        "weight": 1.8,
        "min_score": 1,
        "preset": "hr",
    },
    "fitness": {
        "keywords": (
            "fitness", "gym", "جيم", "workout", "تمارين", "عضوية نادي",
        ),
        "weight": 1.9,
        "min_score": 1,
        "preset": "fitness",
    },
}


def _norm(text: str) -> str:
    t = (text or "").lower()
    # collapse whitespace for phrase matching stability
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _match_phrases(text: str, phrases: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    """Longest-first; each phrase counted at most once."""
    ordered = sorted({(p or "").strip() for p in phrases if p}, key=len, reverse=True)
    found: list[str] = []
    # Work on a mutable mask so shorter tokens inside longer hits are de-prioritized
    mask = text
    for phrase in ordered:
        pl = phrase.lower()
        if len(pl) <= 2 and pl.isascii():
            # short ASCII tokens need crude word-boundary
            if not re.search(rf"(?<![a-z0-9]){re.escape(pl)}(?![a-z0-9])", mask):
                continue
        if pl in mask or phrase in mask:
            found.append(phrase)
            # neutralize matched span to reduce double-count of nested phrases
            mask = mask.replace(pl, " " * len(pl), 1)
            if phrase != pl:
                mask = mask.replace(phrase, " " * len(phrase), 1)
    return tuple(found)


def _score_domain(text: str, domain: str, cfg: dict[str, Any]) -> DomainHit | None:
    hard = set(_match_phrases(text, tuple(cfg.get("keywords") or ())))
    anchors = set(_match_phrases(text, tuple(cfg.get("anchors") or ())))
    ambig_cfg = tuple(cfg.get("ambiguous") or ())
    ambig = set(_match_phrases(text, ambig_cfg)) if ambig_cfg else set()

    # Ambiguous evidence requires anchors or hard keywords on this domain
    if ambig and not (anchors or hard):
        ambig = set()
    if cfg.get("anchors") and ambig and not anchors:
        ambig = set()

    # Strip pure global-ambiguous from hard if they snuck into keywords list
    hard = {h for h in hard if h not in _AMBIGUOUS or h in anchors or len(h) > 6}

    hard_count = float(len(hard | anchors))
    ambig_count = float(len(ambig)) if (hard or anchors) else 0.0
    raw = hard_count + 0.35 * ambig_count
    if raw < float(cfg.get("min_score", 1)):
        return None

    score = raw * float(cfg.get("weight", 1.0))
    # Bonus for multi-phrase hard evidence (explicit user intent)
    if hard_count >= 2:
        score *= 1.15
    if hard_count >= 3:
        score *= 1.1
    if hard_count <= 0 and ambig_count > 0:
        score *= 0.2

    matched = tuple(dict.fromkeys(list(hard) + list(anchors) + list(ambig)))
    return DomainHit(
        domain=domain,
        score=score,
        matched=matched,
        hard_count=hard_count,
        ambig_count=ambig_count,
    )


def detect_detailed(text: str, *, limit: int = 8) -> list[DomainHit]:
    t = _norm(text)
    hits = [h for h in (_score_domain(t, d, cfg) for d, cfg in DOMAINS.items()) if h]
    hits.sort(key=lambda h: (-h.score, h.domain))
    return hits[:limit]


def decide(text: str, *, limit: int = 8) -> DomainDecision:
    """Authoritative domain decision for the whole generation pipeline."""
    hits = detect_detailed(text, limit=limit)
    if not hits:
        return DomainDecision(
            primary=None,
            hits=tuple(),
            allowed_domains=tuple(),
            confidence=0.0,
            reason="no_domain_hit",
        )

    primary = hits[0]
    conf = min(1.0, primary.score / 12.0)

    blocked_presets: set[str] = set()
    blocked_domains: set[str] = set()
    allowed = [h.domain for h in hits]
    reason = f"primary={primary.domain}"

    # Strong tasks intent: lock verticals that historically swallowed todo bots
    if primary.domain in {"tasks", "projects"} and primary.hard_count >= 1:
        # Require tasks-like hard evidence, not only ambiguous
        tasks_strong = primary.domain == "tasks" or primary.hard_count >= 2
        if primary.domain == "tasks" or tasks_strong:
            blocked_presets |= set(_TASKS_BLOCKS_PRESETS)
            blocked_domains |= set(_TASKS_BLOCKS_DOMAINS)
            allowed = [d for d in allowed if d not in blocked_domains]
            if "tasks" not in allowed and primary.domain == "tasks":
                allowed.insert(0, "tasks")
            elif primary.domain == "projects" and "projects" not in allowed:
                allowed.insert(0, "projects")
            # Re-filter hits
            hits = [h for h in hits if h.domain not in blocked_domains]
            conf = max(conf, min(1.0, 0.55 + 0.1 * primary.hard_count))
            reason = f"tasks_lock:{primary.domain}:blocked={sorted(blocked_presets)}"

    # Strong healthcare: block pure shop noise only
    if primary.domain == "healthcare" and primary.hard_count >= 1:
        blocked_presets |= {"commerce_pro", "shop", "marketplace"}
        reason = f"healthcare_lock:block_shop"

    # Strong ecommerce: block clinic
    if primary.domain == "ecommerce" and primary.hard_count >= 2:
        blocked_presets |= {"clinic", "booking"}
        blocked_domains |= {"healthcare"}
        allowed = [d for d in allowed if d not in blocked_domains]
        hits = [h for h in hits if h.domain not in blocked_domains]
        reason = f"ecommerce_lock"

    # Strong group moderation: never drag commerce / complex platform packs
    if primary.domain == "group_moderation" and primary.hard_count >= 1:
        blocked_presets |= {
            "shop", "commerce_pro", "marketplace", "saas", "iot", "blockchain",
            "clinic", "booking", "restaurant", "fitness", "hr", "auction",
            "delivery", "education", "gaming",
        }
        blocked_domains |= {
            "ecommerce", "marketplace", "healthcare", "iot", "blockchain",
            "devops", "gaming", "fitness", "hr",
        }
        allowed = ["group_moderation"] + [d for d in allowed if d not in blocked_domains and d != "group_moderation"]
        hits = [h for h in hits if h.domain not in blocked_domains]
        conf = max(conf, min(1.0, 0.6 + 0.08 * primary.hard_count))
        reason = f"group_moderation_lock:blocked={sorted(blocked_presets)[:8]}"


    return DomainDecision(
        primary=primary.domain if primary else None,
        hits=tuple(hits),
        allowed_domains=tuple(dict.fromkeys(allowed)),
        blocked_presets=frozenset(blocked_presets),
        blocked_domains=frozenset(blocked_domains),
        confidence=conf,
        reason=reason,
    )


def detect(text: str, *, limit: int = 8) -> list[str]:
    """Backward-compatible list of allowed domain ids (post-decision)."""
    return list(decide(text, limit=limit).allowed_domains)


def domains_to_presets(domains: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for d in domains:
        preset = (DOMAINS.get(d) or {}).get("preset")
        if preset and preset not in seen:
            seen.add(preset)
            out.append(str(preset))
    return out


def decision_to_presets(decision: DomainDecision) -> list[str]:
    """Presets derived from allowed domains only (never blocked)."""
    presets = domains_to_presets(list(decision.allowed_domains))
    return [p for p in presets if p not in decision.blocked_presets]


__all__ = [
    "DomainHit",
    "DomainDecision",
    "DOMAINS",
    "detect",
    "detect_detailed",
    "decide",
    "domains_to_presets",
    "decision_to_presets",
]
