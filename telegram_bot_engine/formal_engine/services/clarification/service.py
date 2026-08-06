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

    if not bot_name and len(cmds) == 0:
        missing.append("bot_name")

    # purpose gap: short text with no commands
    if len(cmds) == 0 and len(text) < 40:
        missing.append("purpose")

    if len(cmds) < _MIN_MEANINGFUL_COMMANDS:
        missing.append("commands")

    # entities optional if user already said no data / or commands exist
    skip_data = any(
        k in text for k in ("مفيش بيانات", "بدون بيانات", "no data", "مفيش")
    )
    if not ents and not skip_data and len(cmds) == 0:
        missing.append("entities")

    skip_btn = any(k in text for k in ("بدون أزرار", "بدون ازرار", "بدون", "no buttons"))
    if not btns and not skip_btn and len(cmds) == 0:
        missing.append("buttons")

    # Ready rules — smarter thresholds
    ready = False
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


# Arabic -> Latin phonetic transliteration table (readable slugs, no meaning invention).
_AR_TRANS: dict[str, str] = {
    "ا": "a", "أ": "a", "إ": "i", "آ": "aa", "ى": "a", "ء": "",
    "ب": "b", "ت": "t", "ث": "th", "ج": "j", "ح": "h", "خ": "kh",
    "د": "d", "ذ": "dh", "ر": "r", "ز": "z", "س": "s", "ش": "sh",
    "ص": "s", "ض": "d", "ط": "t", "ظ": "z", "ع": "a", "غ": "gh",
    "ف": "f", "ق": "q", "ك": "k", "ل": "l", "م": "m", "ن": "n",
    "ه": "h", "ة": "h", "و": "w", "ي": "y", "ئ": "y", "ؤ": "w",
    "0": "0", "1": "1", "2": "2", "3": "3", "4": "4",
    "5": "5", "6": "6", "7": "7", "8": "8", "9": "9",
}

# Words that carry no command meaning -> dropped from transliterated slugs.
_AR_STOP = {
    "ال", "في", "من", "على", "علي", "الي", "و", "او", "أو", "ثم",
    "هذا", "هذه", "ذلك", "التي", "الذي", "ما", "لا", "نعم", "كل",
    "بعض", "غير", "مع", "عن", "ان", "أن", "إن",
}


def _transliterate_ar(label: str) -> str:
    """Convert Arabic text to a readable latin slug (phonetic, stable).

    Keeps digits, drops stop-words, collapses repeated separators.
    Never invents meaning -- only a pronounceable id, e.g.
    'إدارة الجلسات' -> 'idarat_aljlsat'.
    """
    out: list[str] = []
    for ch in (label or ""):
        out.append(_AR_TRANS.get(ch, ch))
    s = "".join(out)
    # remove leftover Arabic / non-ascii / punctuation -> separators
    s = re.sub(r"[^a-zA-Z0-9]+", "_", s)
    # drop stop-ish tiny fragments and collapse underscores
    parts = [p for p in s.split("_") if p and len(p) > 1]
    s = "_".join(parts)
    s = re.sub(r"_+", "_", s).strip("_").lower()
    if not s:
        s = "cmd"
    return s[:40]


def _slug_cmd(label: str) -> str:
    """Derive ascii command id from user label (structural, not domain pack).

    Priority:
      1) explicit known stems (Arabic + English synonyms) -> stable english id
      2) latin words present in label -> snake_case of them
      3) Arabic-only label -> phonetic transliteration (readable, stable)
      4) final fallback -> short hash (only when nothing else works)
    """
    raw = (label or "").strip().lower()
    raw = raw.lstrip("/")
    stems = [
        (r"تسجيل|register|signup|إنشاء\s*حساب", "register"),
        (r"تتبع|track|متابعة", "track"),
        (r"طلب\s*جديد|new\s*order|اورد\s*جديد|إنشاء\s*طلب", "order"),
        (r"طلباتي|my\s*orders|اوردرات|قائمة\s*طلبات", "my_orders"),
        (r"منيو|menu|قائمة\s*الطعام", "menu"),
        (r"حجز|book|reserve|reservation", "book"),
        (r"إحصائ|stats|statistics|إحصاءات", "stats"),
        (r"أدمن|admin|مشرف|المشرفين|المدراء", "admin"),
        (r"دفع|pay|payment|مدفوعات|فواتير|billing", "pay"),
        (r"بحث|search|lookup", "search"),
        (r"دعم|support|مساعدة|help\s*desk", "support"),
        (r"توصيل|delivery|شحن|تتبع\s*الشحنة", "delivery"),
        (r"تقسيم\s*ملف|split|split\s*pdf|قسم\s*ملف|تقسيم", "split_file"),
        (r"دمج\s*ملف|merge|merge\s*pdf|ضم\s*ملف", "merge_file"),
        (r"ضغط\s*ملف|compress|compress\s*pdf|compres", "compress_file"),
        (r"تحويل|convert|تحويل\s*صيغة|format\s*convert", "convert_file"),
        (r"profile|حسابي|الملف\s*الشخصي", "profile"),
        (r"إعدادات|settings|اعدادات|تفضيلات|preferences", "settings"),
        (r"إلغاء|cancel|الغاء", "cancel"),
        (r"تأكيد|confirm|تاكيد", "confirm"),
        (r"جلس|session|إدارة\s*الجلسات|الجلسات", "sessions"),
        (r"كلمة\s*المرور|password|استعادة\s*كلمة|نسيت\s*كلمة|reset\s*password", "password_reset"),
        (r"أجهزة|devices|الأجهزة\s*المتصلة|إدارة\s*الأجهزة", "devices"),
        (r"رسوم\s*بيان|charts|إحصائيات\s*مباشرة|grafana|dashboard\s*charts", "charts"),
        (r"المستخدمين|users|إدارة\s*المستخدمين|الأعضاء|members", "users"),
        (r"لوحة\s*تحكم|dashboard|panel|control\s*panel", "dashboard"),
        (r"اشتراك|subscription|اشتراكات|الباقات|plans", "subscription"),
        (r"محفظة|wallet|wallet|الرصيد|balance|credit", "wallet"),
        (r"تذاكر|tickets|ticket|الدعم\s*الفني|فتح\s*تذكرة", "tickets"),
        (r"إشعار|notifications|notifications|تنبيهات|alerts", "notifications"),
        (r"سجل\s*التدقيق|audit|audit\s*log|تدقيق", "audit_log"),
        (r"سجل\s*الأخطاء|error\s*log|logs|سجلات", "error_logs"),
        (r"مراقبة\s*السيرفر|server\s*monitor|monitor|الحالة\s*السيرفر", "server_monitor"),
        (r"صلاحيات|permissions|roles|الأدوار|roles", "permissions"),
        (r"تصدير|export|تصدير\s*بيانات", "export"),
        (r"استيراد|import|استيراد\s*بيانات", "import_data"),
        (r"تقارير|reports|report|تقرير", "reports"),
        (r"نسخة\s*احتياطية|backup|backup|النسخ\s*الاحتياطي", "backup"),
        (r"تسجيل\s*خروج|logout|signout|خروج", "logout"),
        (r"تسجيل\s*دخول|login|signin|دخول", "login"),
        (r"توثيق|2fa|auth|المصادقة\s*الثنائية|twofa", "two_fa"),
        (r"حظر|ban|block|blocklist|القائمة\s*السوداء", "ban"),
        (r"مراجعة|review|التقييمات|ratings|تقييم", "reviews"),
    ]
    for pat, cmd in stems:
        if re.search(pat, label, re.I):
            return cmd
    # latin words -> snake_case
    latin = re.findall(r"[a-zA-Z][a-zA-Z0-9]{1,20}", label)
    if latin:
        return "_".join(w.lower() for w in latin)[:32]
    # arabic-only -> readable transliteration (stable, pronounceable)
    tr = _transliterate_ar(label)
    if tr and tr != "cmd":
        return tr
    # final fallback -> short hash (rarely reached now)
    import hashlib
    h = hashlib.sha1((label or "x").encode("utf-8")).hexdigest()[:6]
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
