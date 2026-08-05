"""
ClarificationService — pure rule-based sufficiency check.

Zero LLM. Zero domain templates.
When the extracted DSL is too thin, return targeted questions
built from gaps in the user text — never invent features.
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "score": self.score,
            "missing": list(self.missing),
            "questions": list(self.questions),
            "summary": dict(self.summary),
            "bot_name": self.bot_name,
        }


_MIN_MEANINGFUL_COMMANDS = 1  # beyond start/help
_MIN_SCORE = 0.40


def _extract_bot_name(text: str) -> str:
    m = re.search(
        r"(?:باسم|اسمه|اسمها|اسم البوت|bot\s*name|named|name[:\s]+)\s*"
        r"[«\"']?([A-Za-z0-9\u0600-\u06FF][A-Za-z0-9\u0600-\u06FF \-_]{1,40})[»\"']?",
        text or "",
        re.I,
    )
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip()[:48]
    return ""


def assess_spec(user_text: str) -> ClarificationResult:
    """
    Run formal DSL extraction and decide if generation can proceed.

    ready=True  → enough surface to build a real bot
    ready=False → return questions the user must answer
    """
    text = (user_text or "").strip()
    if len(text) < 3:
        return ClarificationResult(
            ready=False,
            score=0.0,
            missing=["description"],
            questions=[
                "وصف البوت قصير جدًا.\n"
                "اكتب لي:\n"
                "1) اسم البوت\n"
                "2) الأوامر اللي عايزها (مثال: /register /track /menu)\n"
                "3) الكيانات أو البيانات (عميل، طلب، حجز…)\n"
                "4) أي أزرار أو خطوات مهمة"
            ],
            bot_name="",
        )

    try:
        from ...dsl.extractor import extract_dsl
        program = extract_dsl(text)
    except Exception as exc:
        return ClarificationResult(
            ready=False,
            score=0.0,
            missing=["parse_error"],
            questions=[
                f"ما قدرتش أفهم الوصف ({type(exc).__name__}).\n"
                "جرّب تكتب الأوامر صراحة مثل:\n"
                "/start /help /register /track\n"
                "ومع كل أمر جملة قصيرة عن وظيفته."
            ],
        )

    cmds = [c.name for c in program.commands if c.name not in ("start", "help")]
    ents = [e.name for e in program.entities]
    btns = [b.label for b in program.buttons]
    rules = list(getattr(program, "rules", None) or [])
    ops = list(getattr(program, "operations", None) or [])
    bot_name = _extract_bot_name(text)

    score = 0.0
    # Explicit /commands weigh heavily
    score += min(0.45, 0.15 * len(cmds))
    # Entities
    score += min(0.25, 0.10 * len(ents))
    # Buttons
    score += min(0.15, 0.05 * len(btns))
    # Rules / operations (behavior)
    score += min(0.15, 0.05 * (len(rules) + len(ops)))
    # Named bot slightly helps
    if bot_name:
        score += 0.05
    # Long structured text
    if len(text) >= 120:
        score += 0.05
    if len(text) >= 300:
        score += 0.05
    score = min(1.0, score)

    missing: list[str] = []
    questions: list[str] = []

    if len(cmds) < _MIN_MEANINGFUL_COMMANDS:
        missing.append("commands")
        questions.append(
            "ما الأوامر اللي عايزها في البوت؟\n"
            "اكتبها بصيغة /اسم_الأمر مع وصف قصير لكل أمر.\n"
            "مثال:\n"
            "/register — تسجيل مستخدم\n"
            "/track — تتبع طلب\n"
            "/menu — عرض القائمة"
        )

    if not ents and not any(
        k in text for k in ("يحفظ", "قاعدة بيانات", "database", "تخزين", "سجل")
    ):
        # Only ask about entities if nothing data-like was mentioned
        if "commands" in missing or len(cmds) == 0:
            missing.append("entities")
            questions.append(
                "هل في بيانات عايز البوت يحفظها؟\n"
                "مثال: عميل (اسم، هاتف) — طلب (عنوان، حالة) — حجز (موعد، عدد).\n"
                "لو مفيش بيانات، اكتب «مفيش بيانات»."
            )

    # Buttons are optional when we already have meaningful commands
    if not btns and len(cmds) == 0:
        missing.append("buttons_or_flows")
        questions.append(
            "هل عايز أزرار في القائمة الرئيسية؟\n"
            "اكتب أسماء الأزرار سطر بسطر أو مفصولة بفاصلة.\n"
            "مثال: تسجيل، تتبع، طلباتي\n"
            "لو مش محتاج أزرار، اكتب «بدون أزرار»."
        )

    if not bot_name and len(cmds) == 0:
        missing.append("bot_name")
        questions.insert(
            0,
            "إيه اسم البوت؟\nاكتب مثلًا: باسم عبود  أو  اسمه ShopBot",
        )

    # Ready when we have at least one real command beyond start/help
    ready = (
        len(cmds) >= _MIN_MEANINGFUL_COMMANDS
        and "commands" not in missing
    )

    # Two or more commands → always ready (user was explicit enough)
    if len(cmds) >= 2:
        ready = True
        questions = [q for q in questions if "الأوامر" not in q]
        missing = [m for m in missing if m != "commands"]

    # One command + entities or decent score → ready
    if len(cmds) >= 1 and (ents or score >= _MIN_SCORE):
        ready = True
        questions = [q for q in questions if "الأوامر" not in q]
        missing = [m for m in missing if m != "commands"]

    return ClarificationResult(
        ready=ready,
        score=round(score, 3),
        missing=missing,
        questions=questions,
        summary={
            "commands": cmds,
            "entities": ents,
            "buttons": btns,
            "rules": len(rules),
            "operations": len(ops),
            "text_len": len(text),
        },
        bot_name=bot_name,
    )


def build_clarification_message(result: ClarificationResult) -> str:
    """Human-readable Arabic message with the questions to ask."""
    lines = [
        "📌 عشان أعمل بوت *مكتمل* محتاج منك تفاصيل واضحة (مش /start و /help بس).",
    ]
    if result.bot_name:
        lines.append(f"• الاسم: {result.bot_name}")
    if result.summary.get("commands"):
        lines.append(
            "• أوامر فهمتها: "
            + ", ".join(f"/{c}" for c in result.summary["commands"])
        )
    else:
        lines.append("• لسه مفيش أوامر واضحة غير /start و /help")

    lines.append("")
    lines.append("ابعت رد واحد فيه:")
    lines.append("")
    lines.append("الأوامر:")
    lines.append("/register — تسجيل")
    lines.append("/order — طلب جديد")
    lines.append("/track — تتبع")
    lines.append("/my_orders — طلباتي")
    lines.append("")
    lines.append("الكيانات:")
    lines.append("Customer (name, phone)")
    lines.append("Order (address, phone, status)")
    lines.append("")
    lines.append("الأزرار:")
    lines.append("تسجيل، طلب جديد، تتبع، طلباتي")
    lines.append("")
    if result.questions:
        lines.append("أو جاوب على:")
        for i, q in enumerate(result.questions, 1):
            lines.append(f"{i}) {q}")
        lines.append("")
    lines.append("✅ هبني البوت من كلامك فقط — بدون قوالب جاهزة وبدون ذكاء اصطناعي.")
    return "\n".join(lines)


def merge_answers(original: str, answers: str, prior_extra: str = "") -> str:
    """
    Merge original request + clarification answers into one grounded spec text.
    No invention — only concatenate user words into sections the extractor knows.
    """
    parts: list[str] = []
    base = (original or "").strip()
    extra = (answers or "").strip()
    prior = (prior_extra or "").strip()

    if base:
        parts.append(base)
    if prior:
        parts.append(prior)
    if extra:
        # If answers look like bare /commands list, label them
        if re.search(r"/[a-zA-Z]", extra) and "الأوامر" not in extra:
            parts.append("الأوامر:\n" + extra)
        else:
            parts.append(extra)

    return "\n\n".join(parts)
