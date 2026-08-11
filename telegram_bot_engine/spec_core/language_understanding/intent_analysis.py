"""Layer 2 — Intent Analysis Engine (zero-AI, rule-based, max quality).

Consumes Layer-1 LanguageUnderstandingResult and produces a multi-dimensional
intent decision: primary + secondary intents with weight/confidence/source,
complexity, skill, language, feature plan, and ask-vs-guess gate.

Does NOT invent domains from thin air: every signal is grounded in LU evidence
or explicit entity/pattern hits.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from .engine import DOMAIN_TO_PRESET, LanguageUnderstandingResult, understand
from .entities import ExtractedEntities

_DATA = Path(__file__).resolve().parent / "data"

# Confidence below this → ask, don't hard-commit fragile features
ASK_THRESHOLD = 0.60
# Secondary intents must clear this relative weight
SECONDARY_MIN_WEIGHT = 0.28


@dataclass
class IntentSignal:
    intent: str
    weight: float  # 0..1 relative importance
    confidence: float  # 0..1 reliability
    source: str  # keyword|synonym|context|pattern|entity|lu|rule
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent,
            "weight": round(self.weight, 3),
            "confidence": round(self.confidence, 3),
            "source": self.source,
            "evidence": list(self.evidence)[:8],
        }


@dataclass
class IntentAnalysis:
    primary: IntentSignal | None
    secondary: list[IntentSignal]
    complexity: str  # simple|medium|complex
    skill_level: str  # beginner|intermediate|expert
    language: str  # ar_eg|ar|en|mixed
    domain_family: str
    expected_feature_count: tuple[int, int]
    should_ask: bool
    ask_reason: str
    questions: list[str]
    feature_plan: list[str]
    preset: str | None
    secondary_presets: list[str]
    decision_trace: list[str] = field(default_factory=list)
    lu_snapshot: dict[str, Any] = field(default_factory=dict)
    filled_slots: dict[str, bool] = field(default_factory=dict)
    missing_slots: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary": self.primary.to_dict() if self.primary else None,
            "secondary": [s.to_dict() for s in self.secondary],
            "complexity": self.complexity,
            "skill_level": self.skill_level,
            "language": self.language,
            "domain_family": self.domain_family,
            "expected_feature_count": list(self.expected_feature_count),
            "should_ask": self.should_ask,
            "ask_reason": self.ask_reason,
            "questions": self.questions,
            "feature_plan": self.feature_plan,
            "preset": self.preset,
            "secondary_presets": self.secondary_presets,
            "filled_slots": self.filled_slots,
            "missing_slots": self.missing_slots,
            "decision_trace": self.decision_trace,
        }


@lru_cache(maxsize=1)
def _checklists() -> dict:
    path = _DATA / "intent_checklists.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _rules() -> dict:
    path = _DATA / "intent_rules.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def detect_language(text: str) -> str:
    t = text or ""
    ar = len(re.findall(r"[\u0600-\u06FF]", t))
    en = len(re.findall(r"[A-Za-z]", t))
    if ar and en and min(ar, en) / max(ar, en) > 0.25:
        return "mixed"
    if ar >= en:
        # Egyptian markers
        if re.search(r"(عايز|عاوز|كده|كدا|اوي|اوى|محتاج|جروب|دلوقتي|ازاي)", t):
            return "ar_eg"
        return "ar"
    return "en"


def _slot_status(intent: str, ent: ExtractedEntities, lu: LanguageUnderstandingResult) -> tuple[dict[str, bool], list[str]]:
    cl = _checklists().get(intent) or _checklists().get("default") or {}
    required = list(cl.get("required") or [])
    optional = list(cl.get("optional") or [])
    filled: dict[str, bool] = {}

    def mark(slot: str, ok: bool) -> None:
        filled[slot] = bool(ok)

    # Generic evaluators
    mark("product_or_category", bool(ent.product or ent.category))
    mark("payment", bool(ent.payment_methods))
    mark("delivery", bool(ent.wants_delivery))
    mark("discounts", bool(ent.wants_discounts))
    mark("reviews", bool(ent.wants_reviews))
    mark("inventory", bool(ent.wants_inventory))
    mark("wallet", bool(ent.wants_wallet or "wallet" in (ent.payment_methods or [])))
    mark("security_scope", bool(ent.security_checks or "security" == intent))
    mark("target_host", bool(ent.target_domain or ent.target_url or ent.target_ip))
    mark("report_audience", False)  # only via questions
    mark("awareness", "phishing" in (ent.security_checks or []))
    mark("audience", intent == "tickets")  # weak default
    mark("priority_sla", False)
    mark("kb", False)
    mark("course_scope", bool(ent.course_topic or ent.category == "دورات" or intent == "education"))
    mark("quiz", "quiz" in (lu.normalized or "") or "كويز" in (lu.original or "") or "اختبار" in (lu.original or ""))
    mark("certificate", "شهادة" in (lu.original or "") or "certificate" in (lu.normalized or ""))
    mark("progress", "تقدم" in (lu.original or "") or "progress" in (lu.normalized or ""))
    mark("booking_type", intent in {"booking", "clinic"})
    mark("duration", False)
    mark("reminders", "تذكير" in (lu.original or "") or "remind" in (lu.normalized or ""))
    mark("menu_or_orders", intent == "restaurant" or "menu" in (lu.normalized or "") or "منيو" in (lu.original or ""))
    mark("table_booking", "طاولة" in (lu.original or "") or "table" in (lu.normalized or ""))
    mark("connectivity", bool(ent.tech_stack) or intent == "iot")
    mark("alerts", "تنبيه" in (lu.original or "") or "alert" in (lu.normalized or ""))
    mark("device_inventory", False)
    mark("ops_scope", intent == "devops" or bool(ent.tech_stack))
    mark("webhooks", "webhook" in (lu.normalized or ""))
    mark("status", "status" in (lu.normalized or "") or "حالة" in (lu.original or ""))
    mark("pipeline", intent == "crm" or "pipeline" in (lu.normalized or "") or "صفقات" in (lu.original or ""))
    mark("followups", "متابعة" in (lu.original or "") or "follow" in (lu.normalized or ""))
    mark("broadcast", "إذاعة" in (lu.original or "") or "broadcast" in (lu.normalized or ""))
    mark("plans", intent in {"saas", "subscriptions"} or "خطة" in (lu.original or "") or "plan" in (lu.normalized or ""))
    mark("admin", "ادمن" in (lu.original or "") or "admin" in (lu.normalized or ""))
    mark("analytics", "تحليلات" in (lu.original or "") or "analytics" in (lu.normalized or ""))
    mark("api", "api" in (lu.normalized or ""))
    mark("game_loop", intent == "gaming")
    mark("leaderboard", "متصدر" in (lu.original or "") or "leaderboard" in (lu.normalized or ""))
    mark("tournaments", "بطولة" in (lu.original or "") or "tournament" in (lu.normalized or ""))
    mark("economy", "نقاط" in (lu.original or "") or "xp" in (lu.normalized or ""))
    mark("mod_actions", intent == "moderation")
    mark("filters", "فلتر" in (lu.original or "") or "filter" in (lu.normalized or "") or "spam" in (lu.normalized or ""))
    mark("rules", "قواعد" in (lu.original or "") or "rules" in (lu.normalized or ""))
    mark("chain_scope", intent == "blockchain")
    mark("wallet_track", "محفظة" in (lu.original or "") or "wallet" in (lu.normalized or ""))
    mark("nft", "nft" in (lu.normalized or ""))
    mark("finance_scope", intent == "finance")
    mark("invoices", "فاتورة" in (lu.original or "") or "invoice" in (lu.normalized or ""))
    mark("logistics_scope", intent == "logistics")
    mark("tracking", "تتبع" in (lu.original or "") or "track" in (lu.normalized or ""))
    mark("fleet", "أسطول" in (lu.original or "") or "fleet" in (lu.normalized or ""))
    mark("jobs_scope", intent == "jobs")
    mark("apply", "تقديم" in (lu.original or "") or "apply" in (lu.normalized or ""))
    mark("fitness_scope", intent == "fitness")
    mark("streaks", "سلسلة" in (lu.original or "") or "streak" in (lu.normalized or ""))
    mark("subs", "اشتراك" in (lu.original or "") or "subscription" in (lu.normalized or ""))
    mark("contest_type", intent == "contests")
    mark("draw", "قرعة" in (lu.original or "") or "draw" in (lu.normalized or ""))
    mark("rewards", "هدية" in (lu.original or "") or "reward" in (lu.normalized or ""))
    mark("vendors", "بائع" in (lu.original or "") or "vendor" in (lu.normalized or ""))
    mark("commission", "عمولة" in (lu.original or "") or "commission" in (lu.normalized or ""))
    mark("bot_purpose", bool(lu.primary_domain))

    missing = [s for s in required if not filled.get(s)]
    # also track optional fill ratio in filled
    for s in optional:
        filled.setdefault(s, False)
    return filled, missing


def _apply_conflict_rules(
    ranked: list[tuple[str, float, float, list[str]]],
    text: str,
    trace: list[str],
) -> list[tuple[str, float, float, list[str]]]:
    """Reorder / demote competing intents using weighted rules."""
    if len(ranked) < 2:
        return ranked
    by = {r[0]: r for r in ranked}
    rules = _rules()
    low = (text or "").lower()

    def demote(name: str, factor: float, why: str) -> None:
        if name not in by:
            return
        intent, w, c, ev = by[name]
        by[name] = (intent, w * factor, c * factor, ev + [why])
        trace.append(f"rule demote {name} x{factor}: {why}")

    def boost(name: str, factor: float, why: str) -> None:
        if name not in by:
            return
        intent, w, c, ev = by[name]
        by[name] = (intent, min(1.0, w * factor), min(0.99, c * factor), ev + [why])
        trace.append(f"rule boost {name} x{factor}: {why}")

    # Built-in hard rules (also reflected in JSON)
    if "security" in by and "shop" in by:
        if by["security"][1] >= by["shop"][1] * 0.7:
            demote("shop", 0.4, "security_dominates_shop")
    if "shop" in by and "delivery" in by:
        demote("delivery", 0.65, "delivery_is_secondary_to_shop")
    if "shop" in by and "payments" in by:
        demote("payments", 0.7, "payments_is_secondary_to_shop")
    if "moderation" in by and "security" in by:
        mod_keys = ["حظر", "كتم", "تحذير", "ban", "mute", "warn", "جروب", "مجموعة", "group"]
        if any(k in text or k in low for k in mod_keys):
            demote("security", 0.35, "moderation_keywords")
            boost("moderation", 1.15, "moderation_keywords")
    if "clinic" in by and "booking" in by:
        boost("clinic", 1.1, "clinic_over_booking")
        demote("booking", 0.7, "clinic_primary")
    if "education" in by and "shop" in by:
        if by["education"][1] >= 0.45:
            demote("shop", 0.35, "education_not_shop")
    if "iot" in by and "shop" in by:
        demote("shop", 0.3, "iot_not_shop")
    if "devops" in by and "shop" in by:
        demote("shop", 0.3, "devops_not_shop")
    if "gaming" in by and "shop" in by:
        demote("shop", 0.35, "gaming_not_shop")
    if "crm" in by and "shop" in by:
        if by["crm"][1] >= 0.4:
            demote("shop", 0.4, "crm_not_shop")

    # JSON rules optional extras
    for _name, rule in rules.items():
        when = set(rule.get("when") or [])
        if not when.issubset(by.keys()):
            continue
        prefer = rule.get("prefer")
        if rule.get("always") and prefer in by:
            for other in when - {prefer}:
                demote(other, 0.5, f"json_rule:{_name}")

    out = sorted(by.values(), key=lambda x: (-x[1], -x[2], x[0]))
    return out


def _signals_from_lu(lu: LanguageUnderstandingResult) -> list[tuple[str, float, float, list[str], str]]:
    """Convert LU domain scores into normalized intent candidates."""
    if not lu.domains:
        return []
    top = max(d.score for d in lu.domains) or 1.0
    out = []
    for d in lu.domains[:10]:
        weight = max(0.0, min(1.0, d.score / (top + 0.01)))
        # blend LU confidence with relative weight
        conf = max(0.0, min(0.99, 0.55 * d.confidence + 0.45 * weight))
        src = d.sources[0] if d.sources else "lu"
        out.append((d.domain, weight, conf, list(d.matched[:6]), src))
    return out


def _entity_intent_boosts(ent: ExtractedEntities) -> list[tuple[str, float, float, list[str], str]]:
    boosts = []
    if ent.security_checks or ent.target_domain or ent.target_url or ent.target_ip:
        boosts.append(
            (
                "security",
                0.95,
                0.9,
                list(ent.security_checks[:5]) + ([ent.target_domain] if ent.target_domain else []),
                "entity",
            )
        )
    if ent.course_topic:
        boosts.append(("education", 0.85, 0.85, [ent.course_topic], "entity"))
    if ent.tech_stack:
        for tech in ent.tech_stack:
            if tech in {"mqtt", "arduino", "esp32"}:
                boosts.append(("iot", 0.9, 0.88, [tech], "entity"))
            if tech in {"docker", "kubernetes", "nginx"}:
                boosts.append(("devops", 0.88, 0.86, [tech], "entity"))
    if ent.payment_methods and (ent.product or ent.category or ent.wants_delivery):
        boosts.append(("shop", 0.7, 0.75, list(ent.payment_methods[:3]), "entity"))
        boosts.append(("payments", 0.55, 0.7, list(ent.payment_methods[:3]), "entity"))
    if ent.brand_analogy in {"amazon", "noon", "jumia"}:
        boosts.append(("marketplace", 0.9, 0.88, [ent.brand_analogy], "entity"))
    return boosts


def _merge_candidates(
    items: list[tuple[str, float, float, list[str], str]],
) -> list[tuple[str, float, float, list[str]]]:
    bag: dict[str, tuple[float, float, list[str], set[str]]] = {}
    for intent, w, c, ev, src in items:
        if intent not in bag:
            bag[intent] = (w, c, list(ev), {src})
        else:
            ow, oc, oev, osrc = bag[intent]
            bag[intent] = (
                max(ow, w) + 0.15 * min(ow, w),  # soft combine
                max(oc, c),
                list(dict.fromkeys(oev + list(ev)))[:10],
                osrc | {src},
            )
    ranked = []
    for intent, (w, c, ev, srcs) in bag.items():
        ranked.append((intent, min(1.0, w), min(0.99, c), ev))
    ranked.sort(key=lambda x: (-x[1], -x[2], x[0]))
    return ranked


def _feature_plan(
    primary: str | None,
    secondary: list[str],
    lu: LanguageUnderstandingResult,
    ent: ExtractedEntities,
) -> list[str]:
    """Union of LU hints filtered by accepted intents only."""
    allowed = set()
    if primary:
        allowed.add(primary)
    allowed.update(secondary)
    # always allow payments/delivery as secondary modifiers for commerce
    if primary in {"shop", "marketplace", "restaurant"}:
        allowed.update({"payments", "delivery", "wallet"})
    if primary == "security":
        allowed.add("security")

    hints = list(lu.feature_hints or [])
    # Re-derive minimal safety set if LU hints empty
    if not hints and primary == "security":
        hints = ["sec_domain_overview", "sec_dns_check", "sec_tls_check", "sec_tips"]
    if not hints and primary == "shop":
        hints = ["shop_catalog", "cart_view", "cart_checkout", "shop_add_item"]

    # Filter shop hints if primary is non-commerce
    non_commerce = {
        "security", "education", "iot", "blockchain", "devops", "ai_ml",
        "gaming", "tickets", "crm", "saas", "moderation", "clinic",
        "healthcare", "finance", "jobs", "fitness", "tasks", "notes", "contests",
    }
    out: list[str] = []
    for h in hints:
        if primary in non_commerce and h.startswith(("shop_", "cart_", "coupon", "wishlist")):
            continue
        if h not in out:
            out.append(h)

    # Entity-driven precision adds
    if primary == "security":
        for chk, feat in (
            ("dns", "sec_dns_check"),
            ("mx", "sec_mx_check"),
            ("tls", "sec_tls_check"),
            ("headers", "sec_headers_check"),
        ):
            if chk in (ent.security_checks or []) and feat not in out:
                out.append(feat)
    if primary in {"shop", "marketplace"} and "vodafone_cash" in (ent.payment_methods or []):
        for f in ("vodafone_cash", "pay_methods", "wallet_topup"):
            if f not in out:
                out.append(f)
    return out


def analyze_intent(text: str, *, lu: LanguageUnderstandingResult | None = None) -> IntentAnalysis:
    """Full Layer-2 analysis for a user utterance."""
    trace: list[str] = []
    if lu is None:
        lu = understand(text or "")
        trace.append("lu=fresh")
    else:
        trace.append("lu=provided")

    lang = detect_language(text or "")
    skill = lu.skill_hint or "beginner"
    complexity = lu.complexity_hint or "simple"
    ent = lu.entities

    candidates = _signals_from_lu(lu)
    # rewrite to include source in merge
    flat = [(i, w, c, ev, src) for i, w, c, ev, src in candidates]
    flat.extend(_entity_intent_boosts(ent))
    ranked = _merge_candidates(flat)
    trace.append(f"candidates={[r[0] for r in ranked[:5]]}")

    ranked = _apply_conflict_rules(ranked, text or "", trace)

    primary_sig: IntentSignal | None = None
    secondary_sigs: list[IntentSignal] = []

    if ranked:
        intent, w, c, ev = ranked[0]
        # Cap confidence if LU said ambiguous or very short
        if lu.is_ambiguous:
            c = min(c, 0.55)
            trace.append("confidence_capped_ambiguous")
        if len((lu.tokens or [])) <= 1:
            c = min(c, 0.5)
            trace.append("confidence_capped_short")
        primary_sig = IntentSignal(
            intent=intent,
            weight=min(1.0, w),
            confidence=c,
            source="lu+rules",
            evidence=ev,
        )
        for intent2, w2, c2, ev2 in ranked[1:6]:
            if w2 < SECONDARY_MIN_WEIGHT:
                continue
            # secondary weight relative to primary
            secondary_sigs.append(
                IntentSignal(
                    intent=intent2,
                    weight=min(1.0, w2),
                    confidence=c2,
                    source="lu+rules",
                    evidence=ev2,
                )
            )

    primary_name = primary_sig.intent if primary_sig else None
    filled, missing = _slot_status(primary_name or "default", ent, lu)
    cl = _checklists().get(primary_name or "default") or _checklists().get("default") or {}
    family = cl.get("family") or "generic"
    budget = tuple(cl.get("feature_budget") or [4, 12])

    # Complexity refinement from secondary count + missing
    if len(secondary_sigs) >= 3 or (ent.payment_methods and ent.wants_delivery and ent.wants_discounts):
        complexity = "complex"
    elif len(secondary_sigs) >= 1 or missing:
        complexity = complexity if complexity != "simple" else "medium"

    should_ask = False
    ask_reason = ""
    if primary_sig is None:
        should_ask = True
        ask_reason = "no_primary_intent"
    elif primary_sig.confidence < ASK_THRESHOLD:
        should_ask = True
        ask_reason = f"low_confidence<{ASK_THRESHOLD}"
    elif missing:
        # critical slots missing → ask (generation can still use baseline plan)
        should_ask = True
        ask_reason = "missing_required_slots:" + ",".join(missing)
        trace.append(ask_reason)

    questions = list(lu.suggested_questions or [])
    # Slot-specific questions override/extend
    slot_q = {
        "product_or_category": "هتبيع / المجال إيه بالظبط؟",
        "payment": "طرق الدفع المطلوبة؟",
        "security_scope": "أي فحوصات أمنية؟ (DNS/TLS/Headers/Phishing)",
        "target_host": "الدومين أو الرابط المستهدف؟",
        "course_scope": "موضوع الكورسات؟",
        "connectivity": "بروتوكول الأجهزة؟ MQTT/HTTP؟",
        "pipeline": "مراحل الـ pipeline؟",
        "plans": "ما هي خطط الاشتراك؟",
        "game_loop": "شكل اللعب: نقاط / بطولات / مستويات؟",
        "mod_actions": "أوامر الإشراف المطلوبة؟",
        "bot_purpose": "عايز البوت يعمل إيه بالظبط؟",
        "booking_type": "نوع الحجز؟ موعد / طاولة / خدمة",
        "menu_or_orders": "منيو + طلبات فقط أم مع حجز طاولات؟",
        "ops_scope": "نطاق DevOps: deploy alerts / status / webhooks؟",
    }
    for slot in missing:
        q = slot_q.get(slot)
        if q and q not in questions:
            questions.insert(0, q)
    questions = questions[:5]

    secondary_names = [s.intent for s in secondary_sigs]
    features = _feature_plan(primary_name, secondary_names, lu, ent)

    # Feature budget trim for beginners with simple complexity
    low, high = budget
    if skill == "beginner" and complexity == "simple":
        features = features[: max(low, min(len(features), (low + high) // 2))]
    elif complexity == "complex" or skill == "expert":
        # keep full plan, budget is advisory
        pass

    preset = DOMAIN_TO_PRESET.get(primary_name) if primary_name else None
    sec_presets = []
    for n in secondary_names:
        ps = DOMAIN_TO_PRESET.get(n)
        if ps and ps not in sec_presets and ps != preset:
            sec_presets.append(ps)

    return IntentAnalysis(
        primary=primary_sig,
        secondary=secondary_sigs,
        complexity=complexity,
        skill_level=skill,
        language=lang,
        domain_family=family,
        expected_feature_count=(int(budget[0]), int(budget[1])),
        should_ask=should_ask,
        ask_reason=ask_reason,
        questions=questions,
        feature_plan=features,
        preset=preset,
        secondary_presets=sec_presets,
        decision_trace=trace,
        lu_snapshot={
            "primary_domain": lu.primary_domain,
            "ambiguous": lu.is_ambiguous,
            "tokens": len(lu.tokens or []),
        },
        filled_slots=filled,
        missing_slots=missing,
    )


def analyze(text: str) -> IntentAnalysis:
    """Public entry: LU + Intent Analysis pipeline."""
    return analyze_intent(text)


__all__ = [
    "IntentSignal",
    "IntentAnalysis",
    "analyze_intent",
    "analyze",
    "detect_language",
    "ASK_THRESHOLD",
]
