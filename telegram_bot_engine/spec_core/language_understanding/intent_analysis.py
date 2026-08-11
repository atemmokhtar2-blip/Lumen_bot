"""Layer 2 — Intent Analysis Engine MAX (zero-AI).

Decision stack (highest trust first):
  1) High-precision signatures (anchors) — hard evidence
  2) Entity boosts (domain/IP/MQTT/payments…)
  3) Layer-1 LU domain scores — supporting only
  4) Conflict rules + negative evidence
  5) Confidence calibration → ask-vs-commit gate

Never invents a primary intent without evidence. Vague utterances force ask.
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
from .intent_signatures import match_signatures, vague_bot_request

_DATA = Path(__file__).resolve().parent / "data"

ASK_THRESHOLD = 0.62
SECONDARY_MIN_WEIGHT = 0.30
# Primary must beat runner-up by this margin unless signature-anchored
PRIMARY_MARGIN = 0.12


@dataclass
class IntentSignal:
    intent: str
    weight: float
    confidence: float
    source: str
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
    complexity: str
    skill_level: str
    language: str
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
    evidence_grade: str = "none"  # none|weak|solid|hard

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
            "evidence_grade": self.evidence_grade,
            "decision_trace": self.decision_trace,
        }


@lru_cache(maxsize=1)
def _checklists() -> dict:
    path = _DATA / "intent_checklists.json"
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
        if re.search(r"(عايز|عاوز|كده|كدا|اوي|محتاج|جروب|دلوقتي|ازاي)", t):
            return "ar_eg"
        return "ar"
    return "en"


def _slot_status(
    intent: str, ent: ExtractedEntities, lu: LanguageUnderstandingResult
) -> tuple[dict[str, bool], list[str]]:
    cl = _checklists().get(intent) or _checklists().get("default") or {}
    required = list(cl.get("required") or [])
    filled: dict[str, bool] = {}

    def mark(slot: str, ok: bool) -> None:
        filled[slot] = bool(ok)

    mark("product_or_category", bool(ent.product or ent.category))
    mark("payment", bool(ent.payment_methods))
    mark("delivery", bool(ent.wants_delivery))
    mark("discounts", bool(ent.wants_discounts))
    mark("reviews", bool(ent.wants_reviews))
    mark("inventory", bool(ent.wants_inventory))
    mark("wallet", bool(ent.wants_wallet or "wallet" in (ent.payment_methods or [])))
    mark("security_scope", bool(ent.security_checks) or intent == "security")
    mark("target_host", bool(ent.target_domain or ent.target_url or ent.target_ip))
    mark("course_scope", bool(ent.course_topic or ent.category == "دورات" or intent == "education"))
    mark("quiz", bool(re.search(r"quiz|كويز|اختبار", (lu.original or "") + (lu.normalized or ""), re.I)))
    mark("booking_type", intent in {"booking", "clinic"})
    mark("menu_or_orders", intent == "restaurant" or bool(re.search(r"menu|منيو|طلبات", lu.original or "", re.I)))
    mark("connectivity", bool(ent.tech_stack) or intent == "iot")
    mark("ops_scope", intent == "devops" or bool(ent.tech_stack))
    mark("pipeline", intent == "crm" or bool(re.search(r"pipeline|صفقات|ليد", lu.original or "", re.I)))
    mark("plans", intent in {"saas", "subscriptions"})
    mark("game_loop", intent == "gaming")
    mark("mod_actions", intent == "moderation")
    mark("chain_scope", intent == "blockchain")
    mark("finance_scope", intent == "finance")
    mark("logistics_scope", intent == "logistics")
    mark("jobs_scope", intent == "jobs")
    mark("fitness_scope", intent == "fitness")
    mark("contest_type", intent == "contests")
    mark("bot_purpose", bool(lu.primary_domain) or intent is not None)
    mark("audience", intent == "tickets")

    missing = [s for s in required if not filled.get(s)]
    return filled, missing


def _merge(
    bag: dict[str, dict[str, Any]], intent: str, weight: float, conf: float, source: str, evidence: list[str]
) -> None:
    if intent not in bag:
        bag[intent] = {
            "weight": weight,
            "conf": conf,
            "sources": {source},
            "evidence": list(evidence)[:8],
            "hard": source in {"signature", "entity_hard"},
        }
        return
    row = bag[intent]
    # evidence-additive: max + soft gain from second channel
    row["weight"] = min(1.0, max(row["weight"], weight) + 0.12 * min(row["weight"], weight))
    row["conf"] = min(0.99, max(row["conf"], conf) + (0.05 if source != list(row["sources"])[0] else 0))
    row["sources"].add(source)
    for e in evidence:
        if e not in row["evidence"]:
            row["evidence"].append(e)
    row["evidence"] = row["evidence"][:10]
    if source in {"signature", "entity_hard"}:
        row["hard"] = True


def _feature_plan(
    primary: str | None,
    secondary: list[str],
    lu: LanguageUnderstandingResult,
    ent: ExtractedEntities,
) -> list[str]:
    non_commerce = {
        "security", "education", "iot", "blockchain", "devops", "ai_ml",
        "gaming", "tickets", "crm", "saas", "moderation", "clinic",
        "healthcare", "finance", "jobs", "fitness", "tasks", "notes",
        "contests", "wallet", "points", "growth", "subscriptions",
    }
    hints = list(lu.feature_hints or [])
    if not hints and primary == "security":
        hints = ["sec_domain_overview", "sec_dns_check", "sec_tls_check", "sec_tips", "sec_list_reports"]
    if not hints and primary == "shop":
        hints = ["shop_catalog", "cart_view", "cart_checkout", "shop_add_item", "shop_orders"]
    if not hints and primary == "wallet":
        hints = ["wallet_balance", "wallet_topup", "pay_methods"]
    if not hints and primary == "moderation":
        hints = ["rules", "my_id"]
    if not hints and primary == "tickets":
        hints = ["ticket_open", "ticket_my", "ticket_list", "ticket_status"]

    out: list[str] = []
    for h in hints:
        if primary in non_commerce and h.startswith(("shop_", "cart_", "coupon", "wishlist")):
            continue
        if primary == "wallet" and h.startswith(("shop_", "cart_")):
            continue
        if h not in out:
            out.append(h)

    if primary == "security":
        for chk, feat in (
            ("dns", "sec_dns_check"),
            ("mx", "sec_mx_check"),
            ("tls", "sec_tls_check"),
            ("headers", "sec_headers_check"),
            ("spf", "sec_dns_check"),
            ("dmarc", "sec_dns_check"),
        ):
            if chk in (ent.security_checks or []) and feat not in out:
                out.append(feat)
        for base in ("sec_domain_overview", "sec_dns_check", "sec_tls_check", "sec_tips"):
            if base not in out:
                out.append(base)
    if primary in {"shop", "marketplace"}:
        pays = set(ent.payment_methods or [])
        if pays & {"vodafone_cash", "fawry", "instapay", "wallet"}:
            for f in ("wallet_balance", "wallet_topup", "vodafone_cash", "pay_methods"):
                if f not in out:
                    out.append(f)
        if pays & {"visa", "telegram_payments"}:
            for f in ("shop_buy", "pay_methods", "payment_history"):
                if f not in out:
                    out.append(f)
        if ent.wants_delivery:
            for f in ("shipping_set", "order_track"):
                if f not in out:
                    out.append(f)
        if ent.wants_discounts:
            for f in ("coupon_apply", "coupon_create"):
                if f not in out:
                    out.append(f)
    if primary == "clinic":
        for f in ("ticket_open", "ticket_my", "ticket_list"):
            if f not in out:
                out.append(f)
    if primary == "booking" and "clinic" in secondary:
        for f in ("ticket_open", "ticket_my"):
            if f not in out:
                out.append(f)
    return out


def _calibrate_confidence(
    *,
    weight: float,
    base_conf: float,
    hard: bool,
    n_sources: int,
    n_evidence: int,
    vague: bool,
    lu_ambiguous: bool,
    margin: float,
) -> float:
    c = base_conf
    if hard:
        c = max(c, 0.78)
        c = min(0.99, c + 0.08)
    if n_sources >= 2:
        c = min(0.99, c + 0.06)
    if n_evidence >= 3:
        c = min(0.99, c + 0.04)
    if margin >= 0.25:
        c = min(0.99, c + 0.05)
    elif margin < PRIMARY_MARGIN and not hard:
        c = min(c, 0.55)
    if vague:
        c = min(c, 0.35)
    if lu_ambiguous and not hard:
        c = min(c, 0.55)
    # weight floor
    c = min(c, 0.5 + 0.5 * weight)
    return max(0.0, min(0.99, c))


def analyze_intent(text: str, *, lu: LanguageUnderstandingResult | None = None) -> IntentAnalysis:
    trace: list[str] = []
    raw = text or ""

    if lu is None:
        lu = understand(raw)
        trace.append("lu=fresh")
    else:
        trace.append("lu=provided")

    vague = vague_bot_request(raw)
    if vague:
        trace.append("vague_utterance")

    lang = detect_language(raw)
    skill = lu.skill_hint or "beginner"
    complexity = lu.complexity_hint or "simple"
    ent = lu.entities

    bag: dict[str, dict[str, Any]] = {}

    # ── Channel A: high-precision signatures ─────────────────────
    sigs = match_signatures(raw)
    for h in sigs:
        _merge(bag, h.intent, min(1.0, 0.55 + h.score * 0.45), min(0.95, 0.7 + h.score * 0.25), "signature", list(h.anchors))
        trace.append(f"sig:{h.intent}={h.score:.2f}")

    # ── Channel B: hard entities ─────────────────────────────────
    if ent.security_checks or ent.target_domain or ent.target_url or ent.target_ip:
        ev = list(ent.security_checks[:5])
        if ent.target_domain:
            ev.append(ent.target_domain)
        _merge(bag, "security", 0.95, 0.92, "entity_hard", ev)
        trace.append("entity_hard:security")
    if ent.course_topic:
        _merge(bag, "education", 0.88, 0.88, "entity_hard", [ent.course_topic])
    if ent.tech_stack:
        for tech in ent.tech_stack:
            if tech in {"mqtt", "arduino", "esp32"}:
                _merge(bag, "iot", 0.92, 0.9, "entity_hard", [tech])
            if tech in {"docker", "kubernetes", "nginx"}:
                _merge(bag, "devops", 0.9, 0.88, "entity_hard", [tech])
    if ent.brand_analogy in {"amazon", "noon", "jumia"}:
        _merge(bag, "marketplace", 0.9, 0.88, "entity_hard", [ent.brand_analogy])
    if ent.payment_methods and (ent.product or ent.category or ent.wants_delivery or ent.wants_discounts):
        _merge(bag, "shop", 0.75, 0.8, "entity", list(ent.payment_methods[:3]))
        _merge(bag, "payments", 0.55, 0.72, "entity", list(ent.payment_methods[:3]))
    elif ent.payment_methods and not (ent.product or ent.category):
        # pure wallet/pay talk
        if set(ent.payment_methods) & {"wallet", "vodafone_cash", "fawry", "instapay"} or ent.wants_wallet:
            _merge(bag, "wallet", 0.8, 0.82, "entity", list(ent.payment_methods[:3]))
        else:
            _merge(bag, "payments", 0.7, 0.75, "entity", list(ent.payment_methods[:3]))

    # ── Channel C: LU supporting scores (never sole hard evidence) ─
    if lu.domains:
        top = max(d.score for d in lu.domains) or 1.0
        for d in lu.domains[:8]:
            w = max(0.0, min(1.0, d.score / (top + 0.01))) * 0.85  # LU discounted
            c = max(0.0, min(0.9, 0.4 * d.confidence + 0.4 * w))
            _merge(bag, d.domain, w, c, "lu", list(d.matched[:4]))

    # ── Vague: wipe soft-only intents ────────────────────────────
    if vague:
        bag = {k: v for k, v in bag.items() if v.get("hard")}
        trace.append("cleared_soft_due_to_vague")

    # ── Conflict / vertical locks ────────────────────────────────
    def demote(name: str, factor: float, why: str) -> None:
        if name in bag:
            bag[name]["weight"] *= factor
            bag[name]["conf"] *= factor
            bag[name]["evidence"].append(why)
            trace.append(f"demote:{name}x{factor}:{why}")

    if "security" in bag and "shop" in bag:
        if bag["security"]["weight"] >= bag["shop"]["weight"] * 0.65 or bag["security"].get("hard"):
            demote("shop", 0.35, "security_over_shop")
    if "moderation" in bag and "security" in bag:
        if bag["moderation"].get("hard") or bag["moderation"]["weight"] >= 0.5:
            demote("security", 0.3, "moderation_over_security")
    if "education" in bag and "shop" in bag and bag["education"]["weight"] >= 0.45:
        demote("shop", 0.3, "education_over_shop")
    for lock in ("iot", "devops", "gaming", "crm", "blockchain", "ai_ml"):
        if lock in bag and "shop" in bag and bag[lock]["weight"] >= 0.45:
            demote("shop", 0.3, f"{lock}_over_shop")
    if "shop" in bag and "delivery" in bag:
        demote("delivery", 0.6, "delivery_secondary")
    if "shop" in bag and "payments" in bag:
        demote("payments", 0.65, "payments_secondary")
    if "clinic" in bag and "booking" in bag:
        bag["clinic"]["weight"] = min(1.0, bag["clinic"]["weight"] * 1.12)
        demote("booking", 0.7, "clinic_primary")
    if "wallet" in bag and "shop" in bag and not bag["shop"].get("hard"):
        # pure money talk without sell verbs → prefer wallet
        if not re.search(r"يبيع|متجر|منتج|shop|store|cart", raw + (lu.normalized or ""), re.I):
            demote("shop", 0.25, "wallet_without_commerce")

    ranked = sorted(
        (
            (
                name,
                min(1.0, row["weight"]),
                min(0.99, row["conf"]),
                list(row["evidence"]),
                bool(row.get("hard")),
                len(row.get("sources") or []),
            )
            for name, row in bag.items()
        ),
        key=lambda x: (-x[1], -x[2], x[0]),
    )
    trace.append(f"ranked={[r[0] for r in ranked[:5]]}")

    primary_sig: IntentSignal | None = None
    secondary_sigs: list[IntentSignal] = []
    evidence_grade = "none"

    if ranked and not (vague and not any(r[4] for r in ranked)):
        name, w, c, ev, hard, nsrc = ranked[0]
        margin = w - (ranked[1][1] if len(ranked) > 1 else 0.0)
        # Reject soft primary with weak margin
        if not hard and margin < PRIMARY_MARGIN and len(ranked) > 1 and ranked[1][1] >= 0.35:
            # ambiguous competition → no primary commit
            trace.append(f"reject_weak_margin:{name}_vs_{ranked[1][0]}")
            primary_sig = None
            evidence_grade = "weak"
            # still keep both as secondary candidates for questions
            for r in ranked[:3]:
                secondary_sigs.append(
                    IntentSignal(intent=r[0], weight=r[1], confidence=r[2], source="contested", evidence=r[3])
                )
        else:
            conf = _calibrate_confidence(
                weight=w,
                base_conf=c,
                hard=hard,
                n_sources=nsrc,
                n_evidence=len(ev),
                vague=vague,
                lu_ambiguous=bool(lu.is_ambiguous),
                margin=margin,
            )
            primary_sig = IntentSignal(
                intent=name,
                weight=w,
                confidence=conf,
                source="signature" if hard else "ensemble",
                evidence=ev,
            )
            evidence_grade = "hard" if hard else ("solid" if conf >= ASK_THRESHOLD else "weak")
            for r in ranked[1:6]:
                if r[1] < SECONDARY_MIN_WEIGHT:
                    continue
                secondary_sigs.append(
                    IntentSignal(
                        intent=r[0],
                        weight=r[1],
                        confidence=r[2],
                        source="ensemble",
                        evidence=r[3],
                    )
                )
    else:
        trace.append("no_viable_primary")

    primary_name = primary_sig.intent if primary_sig else None
    filled, missing = _slot_status(primary_name or "default", ent, lu)
    cl = _checklists().get(primary_name or "default") or _checklists().get("default") or {}
    family = cl.get("family") or "generic"
    budget = tuple(cl.get("feature_budget") or [4, 12])

    if len(secondary_sigs) >= 3:
        complexity = "complex"
    elif secondary_sigs or missing:
        complexity = "medium" if complexity == "simple" else complexity

    should_ask = False
    ask_reason = ""
    if primary_sig is None:
        should_ask = True
        ask_reason = "no_primary_intent"
    elif vague:
        should_ask = True
        ask_reason = "vague_utterance"
    elif primary_sig.confidence < ASK_THRESHOLD:
        should_ask = True
        ask_reason = f"low_confidence<{ASK_THRESHOLD}"
    elif missing:
        should_ask = True
        ask_reason = "missing_required_slots:" + ",".join(missing)
    elif evidence_grade == "weak":
        should_ask = True
        ask_reason = "weak_evidence"

    questions = list(lu.suggested_questions or [])
    slot_q = {
        "product_or_category": "هتبيع / المجال إيه بالظبط؟",
        "payment": "طرق الدفع المطلوبة؟",
        "security_scope": "أي فحوصات؟ DNS / TLS / Headers / Phishing",
        "target_host": "الدومين أو الرابط المستهدف؟",
        "course_scope": "موضوع الكورسات؟",
        "connectivity": "بروتوكول الأجهزة؟ MQTT / HTTP؟",
        "pipeline": "مراحل الـ pipeline؟",
        "plans": "خطط الاشتراك؟",
        "game_loop": "نقاط / بطولات / مستويات؟",
        "mod_actions": "أوامر الإشراف: حظر / كتم / تحذير؟",
        "bot_purpose": "عايز البوت يعمل إيه بالظبط؟ (متجر / أمن / دعم / حجوزات / تعليم / IoT…)",
        "booking_type": "نوع الحجز: موعد / طاولة / خدمة؟",
        "menu_or_orders": "منيو + طلبات فقط أم مع حجز طاولات؟",
        "ops_scope": "DevOps: deploy alerts / status / webhooks؟",
        "audience": "التذاكر لعملاء خارجيين ولا فريق داخلي؟",
    }
    if primary_sig is None:
        questions = [slot_q["bot_purpose"]] + [
            f"هل تقصد: {s.intent}؟" for s in secondary_sigs[:3]
        ]
    for slot in missing:
        q = slot_q.get(slot)
        if q and q not in questions:
            questions.insert(0, q)
    questions = questions[:5]

    secondary_names = [s.intent for s in secondary_sigs]
    features = _feature_plan(primary_name, secondary_names, lu, ent) if primary_sig else []

    # Beginner simple → trim
    low, high = int(budget[0]), int(budget[1])
    if primary_sig and skill == "beginner" and complexity == "simple":
        features = features[: max(low, min(len(features), (low + high) // 2))]

    preset = DOMAIN_TO_PRESET.get(primary_name) if primary_name else None
    sec_presets: list[str] = []
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
        expected_feature_count=(low, high),
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
        evidence_grade=evidence_grade,
    )


def analyze(text: str) -> IntentAnalysis:
    return analyze_intent(text)


__all__ = [
    "IntentSignal",
    "IntentAnalysis",
    "analyze_intent",
    "analyze",
    "detect_language",
    "ASK_THRESHOLD",
]
