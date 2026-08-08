"""
ClarificationService — progressive, rule-based sufficiency check.

Zero LLM. Zero domain templates.
Asks ONE focused question at a time; merges user answers into grounded text
that extract_dsl already understands. Never invents features.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ClarificationResult:
    """Outcome of assessing whether a user text is ready for generation."""

    ready: bool
    score: float = 0.0
    missing: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    bot_name: str = ""
    # progressive: which single gap to ask next
    next_step: str = ""
    step_question: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "score": self.score,
            "missing": list(self.missing),
            "questions": list(self.questions),
            "summary": dict(self.summary),
            "bot_name": self.bot_name,
            "next_step": self.next_step,
            "step_question": self.step_question,
        }


_MIN_MEANINGFUL_COMMANDS = 1
_MIN_SCORE = 0.35

# Progressive order — ask the first gap only
_STEP_ORDER = ("bot_name", "purpose", "commands", "entities", "buttons")

_STEP_QUESTIONS: dict[str, str] = {
    "bot_name": (
        "إيه اسم البوت؟\n"
        "اكتب مثلًا: عبود   أو   باسم ShopBot"
    ),
    "purpose": (
        "البوت بيعمل إيه باختصار؟\n"
        "اكتب جملة عادية، مثال:\n"
        "تسجيل عملاء وطلبات وتتبع الأوردر"
    ),
    "commands": (
        "المستخدم هيقدر يعمل إيه؟\n"
        "اكتب أفعال أو أوامر بجمل قصيرة (سطر لكل حاجة)، مثال:\n"
        "تسجيل\n"
        "طلب جديد\n"
        "تتبع الطلب\n"
        "طلباتي\n\n"
        "أو بصيغة: /register /order /track"
    ),
    "entities": (
        "في بيانات تتسجل؟ لو أيوه اكتبها بجملة بسيطة:\n"
        "مثال: عميل اسم وهاتف — طلب عنوان وحالة\n"
        "لو مفيش: اكتب «مفيش»"
    ),
    "buttons": (
        "عايز أزرار في القائمة الرئيسية؟\n"
        "اكتب أسماءها مفصولة بفاصلة، مثال: تسجيل، طلب جديد، تتبع\n"
        "لو مش محتاج: اكتب «بدون»"
    ),
}


def _extract_bot_name(text: str) -> str:
    m = re.search(
        r"(?:باسم|اسمه|اسمها|اسم البوت|bot\s*name|named|name[:\s]+)\s*"
        r"[«\"']?([A-Za-z0-9\u0600-\u06FF][A-Za-z0-9\u0600-\u06FF \-_]{1,40})[»\"']?",
        text or "",
        re.I,
    )
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip()[:48]
    # bare short Latin/Arabic token as whole message (answer to "what's the name?")
    s = (text or "").strip()
    if 2 <= len(s) <= 40 and "\n" not in s and not s.startswith("/"):
        if re.match(
            r"^[A-Za-z0-9\u0600-\u06FF][A-Za-z0-9\u0600-\u06FF \-_]{1,38}$",
            s,
        ) and not any(
            k in s for k in ("اعمل", "بوت", "فيه", "عايز", "أوامر", "تسجيل", "بدون", "مفيش")
        ):
            return s[:48]
    return ""


def _looks_like_skip(text: str) -> bool:
    t = (text or "").strip().lower()
    return t in (
        "مفيش", "لا", "بدون", "no", "none", "skip", "بدون بيانات",
        "مفيش بيانات", "بدون أزرار", "بدون ازرار", "-",
    )


def assess_spec(user_text: str) -> ClarificationResult:
    """
    ready=True  → enough surface to build a real bot
    ready=False → next_step + step_question (ONE question)
    """
    text = (user_text or "").strip()
    if len(text) < 2:
        return ClarificationResult(
            ready=False,
            score=0.0,
            missing=["purpose"],
            next_step="purpose",
            step_question=_STEP_QUESTIONS["purpose"],
            questions=[_STEP_QUESTIONS["purpose"]],
        )

    try:
        from ...dsl.extractor import extract_dsl
        program = extract_dsl(text)
    except Exception as exc:
        return ClarificationResult(
            ready=False,
            score=0.0,
            missing=["parse_error"],
            next_step="commands",
            step_question=(
                f"ما قدرتش أفهم الوصف ({type(exc).__name__}).\n"
                "اكتب الأوامر سطر بسطر أو بصيغة /register /track"
            ),
            questions=["اكتب الأوامر سطر بسطر أو /register /track"],
        )

    cmds = [c.name for c in program.commands if c.name not in ("start", "help")]
    ents = [e.name for e in program.entities]
    btns = [b.label for b in program.buttons]
    rules = list(getattr(program, "rules", None) or [])
    ops = list(getattr(program, "operations", None) or [])
    bot_name = _extract_bot_name(text)
    # Natural Arabic requests often describe capabilities without slash commands
    # (e.g. "متجر فيه منتجات وسلة شراء"). Treat those capability signals as
    # sufficient intent; requiring a bot name or explicit /commands blocks the
    # primary one-message generation flow.
    feature_terms = (
        "متجر", "منتج", "منتجات", "سلة", "عربة", "طلب", "اوردر",
        "حجز", "موعد", "تسجيل", "عملاء", "عميل", "خدمة العملاء",
        "تذاكر", "دعم", "إدارة مجموعات", "ادارة مجموعات", "جروب", "مجموعة", "تحذير",
        "حظر", "طرد", "كتم", "تثبيت", "حذف رسالة", "توصيل", "دفع", "فاتورة", "بحث", "اشتراك",
        "مخزون", "مستخدمين", "موظفين", "تقارير", "إشعارات",
    )
    has_feature_signal = any(term in text for term in feature_terms)

    score = 0.0
    score += min(0.50, 0.18 * len(cmds))
    score += min(0.20, 0.08 * len(ents))
    score += min(0.15, 0.05 * len(btns))
    score += min(0.10, 0.04 * (len(rules) + len(ops)))
    if bot_name:
        score += 0.05
    if len(text) >= 80:
        score += 0.05
    if len(text) >= 200:
        score += 0.05
    score = min(1.0, score)

    missing: list[str] = []

    if not bot_name and len(cmds) == 0 and not has_feature_signal:
        missing.append("bot_name")

    # purpose gap: short text with no commands
    if len(cmds) == 0 and len(text) < 40 and not has_feature_signal:
        missing.append("purpose")

    if len(cmds) < _MIN_MEANINGFUL_COMMANDS:
        missing.append("commands")

    # entities optional if user already said no data / or commands exist
    skip_data = any(
        k in text for k in ("مفيش بيانات", "بدون بيانات", "no data", "مفيش")
    )
    if not ents and not skip_data and len(cmds) == 0 and not has_feature_signal:
        missing.append("entities")

    skip_btn = any(k in text for k in ("بدون أزرار", "بدون ازرار", "بدون", "no buttons"))
    if not btns and not skip_btn and len(cmds) == 0 and not has_feature_signal:
        missing.append("buttons")

    # Ready rules — smarter thresholds
    ready = False
    # Feature prose alone is NOT enough — need at least one actionable command
    # (slash or capability-evidenced). Otherwise we generate hollow start/help bots.
    if len(cmds) >= 2:
        ready = True
    elif len(cmds) >= 1 and (ents or btns or score >= _MIN_SCORE):
        ready = True
    elif len(cmds) >= 1 and len(text) >= 60:
        ready = True

    if ready:
        missing = []
        return ClarificationResult(
            ready=True,
            score=round(score, 3),
            missing=[],
            questions=[],
            summary={
                "commands": cmds,
                "entities": ents,
                "buttons": btns,
                "rules": len(rules),
                "operations": len(ops),
                "text_len": len(text),
            },
            bot_name=bot_name,
            next_step="",
            step_question="",
        )

    # Pick first gap in order for progressive ask
    next_step = ""
    step_question = ""
    for step in _STEP_ORDER:
        if step in missing:
            next_step = step
            step_question = _STEP_QUESTIONS.get(step, "")
            break
    if not next_step and not ready:
        next_step = "commands"
        step_question = _STEP_QUESTIONS["commands"]
        if "commands" not in missing:
            missing.append("commands")

    return ClarificationResult(
        ready=ready,
        score=round(score, 3),
        missing=missing,
        questions=[step_question] if step_question else [],
        summary={
            "commands": cmds,
            "entities": ents,
            "buttons": btns,
            "rules": len(rules),
            "operations": len(ops),
            "text_len": len(text),
        },
        bot_name=bot_name,
        next_step=next_step,
        step_question=step_question,
    )


def build_clarification_message(result: ClarificationResult) -> str:
    """ONE focused question + light context (easy UX)."""
    lines: list[str] = []

    if result.bot_name or result.summary.get("commands"):
        lines.append("✓ فهمت لحد دلوقتي:")
        if result.bot_name:
            lines.append(f"  • الاسم: {result.bot_name}")
        cmds = result.summary.get("commands") or []
        if cmds:
            lines.append("  • أوامر: " + ", ".join(f"/{c}" for c in cmds))
        ents = result.summary.get("entities") or []
        if ents:
            lines.append("  • بيانات: " + ", ".join(str(e) for e in ents))
        lines.append("")

    q = result.step_question or (result.questions[0] if result.questions else "")
    if not q:
        q = _STEP_QUESTIONS["commands"]

    lines.append(q)
    lines.append("")
    lines.append("💬 جاوب بجملة عادية — مش لازم صيغة تقنية.")
    return "\n".join(lines)


def _normalize_answer_to_sections(step: str, answer: str) -> str:
    """
    Turn a natural answer into labeled sections extract_dsl understands.
    Grounded only — uses the user's words, no invented features.
    """
    a = (answer or "").strip()
    if not a:
        return ""

    if step == "bot_name":
        name = _extract_bot_name(a) or a.split()[0][:40]
        return f"اعمل بوت تليجرام باسم {name}"

    if step == "purpose":
        return a

    if step == "commands":
        if _looks_like_skip(a):
            return ""
        # already has /commands
        if re.search(r"/[a-zA-Z]", a):
            return "الأوامر:\n" + a
        # lines or comma-separated feature words → command section
        parts = re.split(r"[\n,،]+", a)
        lines = []
        for part in parts:
            part = part.strip().lstrip("-•* ").strip()
            if not part or len(part) > 60:
                continue
            # keep as free text; extractor freeform + structural will pick verbs
            lines.append(part)
        if lines:
            return "فيه:\n" + "\n".join(lines) + "\nالأوامر:\n" + "\n".join(
                f"/{_slug_cmd(p)} — {p}" for p in lines
            )
        return a

    if step == "entities":
        if _looks_like_skip(a):
            return "مفيش بيانات"
        # "عميل اسم وهاتف" → structured hint
        return "الكيانات:\n" + a

    if step == "buttons":
        if _looks_like_skip(a):
            return "بدون أزرار"
        return "الأزرار:\n" + a

    return a


def _slug_cmd(label: str) -> str:
    """Derive ascii command id from user label (structural, not domain pack)."""
    raw = (label or "").strip().lower()
    # strip leading slash
    raw = raw.lstrip("/")
    # known grounded stems only when phrase appears in label itself
    stems = [
        (r"تسجيل|register|signup", "register"),
        (r"تتبع|track", "track"),
        (r"طلب\s*جديد|new\s*order|اوردر\s*جديد", "order"),
        (r"طلباتي|my\s*orders|اوردرات", "my_orders"),
        (r"منيو|menu|قائمة", "menu"),
        (r"حجز|book", "book"),
        (r"إحصائ|stats", "stats"),
        (r"أدمن|admin", "admin"),
        (r"دفع|pay", "pay"),
        (r"بحث|search", "search"),
        (r"دعم|support", "support"),
        (r"توصيل|delivery", "delivery"),
        (r"ملف|profile", "profile"),
        (r"إعداد|settings", "settings"),
        (r"إلغاء|cancel", "cancel"),
        (r"تأكيد|confirm", "confirm"),
    ]
    for pat, cmd in stems:
        if re.search(pat, label, re.I):
            return cmd
    # latin words → snake
    latin = re.findall(r"[a-zA-Z][a-zA-Z0-9]{1,20}", label)
    if latin:
        return "_".join(w.lower() for w in latin)[:32]
    # arabic → generic sequential-safe slug from transliteration-ish
    # use hash of label for stability without inventing meaning
    import hashlib
    h = hashlib.sha1(label.encode("utf-8")).hexdigest()[:6]
    return f"cmd_{h}"


def merge_answers(
    original: str,
    answers: str,
    prior_extra: str = "",
    step: str = "",
) -> str:
    """
    Merge original + progressive answers into one grounded spec text.
    """
    parts: list[str] = []
    base = (original or "").strip()
    prior = (prior_extra or "").strip()
    extra_raw = (answers or "").strip()

    if base:
        parts.append(base)
    if prior:
        parts.append(prior)

    if extra_raw:
        if step:
            parts.append(_normalize_answer_to_sections(step, extra_raw))
        elif re.search(r"/[a-zA-Z]", extra_raw) and "الأوامر" not in extra_raw:
            parts.append("الأوامر:\n" + extra_raw)
        else:
            parts.append(extra_raw)

    return "\n\n".join(p for p in parts if p and p.strip())
