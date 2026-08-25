"""
ChatRouter — the chat layer understands the whole bot surface.

Rules (strict):
  - Routes ONLY: maps user text → capability id + params
  - Does NOT generate code, edit files, or invent success
  - New features register here so chat "knows" them
  - Matching is soft (phrases, stems, word overlap) for natural Arabic/English
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class Capability:
    """One thing the system can do — chat must know it."""
    id: str
    title_ar: str
    description_ar: str
    # phrases that strongly signal this capability
    phrases: tuple[str, ...] = ()
    # optional regex patterns (case-insensitive)
    patterns: tuple[str, ...] = ()
    # words that boost score when co-occurring
    boost_words: tuple[str, ...] = ()
    # words that reduce score (disambiguation)
    block_words: tuple[str, ...] = ()
    priority: int = 50  # higher wins ties
    # if True, needs active repo / project in user context
    needs_active_repo: bool = False
    needs_project: bool = False


@dataclass
class ChatRoute:
    capability_id: str
    confidence: float
    title_ar: str
    params: dict[str, Any] = field(default_factory=dict)
    # human hint when low confidence
    alternatives: list[str] = field(default_factory=list)
    raw_text: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.capability_id) and self.confidence >= 0.35


# ---------------------------------------------------------------------------
# Built-in capability registry — extend when adding system features
# ---------------------------------------------------------------------------

_BUILTIN: list[Capability] = [
    Capability(
        id="host_start",
        title_ar="بدء الاستضافة",
        description_ar="تشغيل البوت كخدمة استضافة طويلة الأمد",
        phrases=(
            "استضافة", "استضف", "افتح الاستضافة", "شغل الاستضافة", "شغّل الاستضافة",
            "تفعيل الاستضافة", "ابدأ الاستضافة", "start hosting", "host this",
            "ارفع البوت", "شغل البوت للاستضافة", "خلي البوت شغال",
            "ازاي افتح الاستضافة", "كيف أفتح الاستضافة", "افتح لي الاستضافة",
            "عايز استضافة", "عايز الاستضافة", "ممكن استضافة", "شغل الاستضافه",
            "فعل الاستضافة", "بدء الاستضافة", "deploy bot", "host bot",
        ),
        patterns=(
            r"استضاف",
            r"\bhost(ing)?\b",
            r"افتح.*(بوت|استضاف)",
            r"شغ[ّ]?ل.*(استضاف|host)",
        ),
        boost_words=("افتح", "شغل", "شغّل", "ابدأ", "فعّل", "start", "open"),
        block_words=("أوقف", "اوقف", "وقف", "stop", "حالة", "status", "تشخيص"),
        priority=80,
        needs_project=True,
    ),
    Capability(
        id="host_stop",
        title_ar="إيقاف الاستضافة",
        description_ar="إيقاف مثيل الاستضافة",
        phrases=(
            "أوقف الاستضافة", "اوقف الاستضافة", "وقف الاستضافة", "stop hosting",
            "أوقف البوت المستضاف", "اقفل الاستضافة",
        ),
        patterns=(r"أ?وقف.*استضاف", r"stop\s*host"),
        boost_words=("أوقف", "اوقف", "stop", "اقفل"),
        priority=85,
    ),
    Capability(
        id="host_status",
        title_ar="حالة الاستضافة",
        description_ar="عرض مثيلات الاستضافة",
        phrases=(
            "حالة الاستضافة", "المثيلات", "status host", "hosting status",
            "الاستضافة شغالة", "في استضافة",
        ),
        patterns=(r"حالة.*استضاف", r"host.*status", r"status.*host"),
        boost_words=("حالة", "status", "مثيل"),
        priority=75,
    ),
    Capability(
        id="host_diagnose",
        title_ar="تشخيص الاستضافة",
        description_ar="تشخيص أخطاء الاستضافة",
        phrases=(
            "تشخيص الاستضافة", "أخطاء الاستضافة", "اخطاء الاستضافة", "diagnose host",
        ),
        patterns=(r"تشخيص.*استضاف", r"diagnose.*host"),
        priority=75,
    ),
    Capability(
        id="create_repo",
        title_ar="إنشاء مستودع",
        description_ar="إنشاء مستودع GitHub جديد بالتوكن",
        phrases=(
            "أنشئ مستودع", "انشئ مستودع", "إنشاء مستودع", "اعمل مستودع",
            "مستودع جديد", "ريبو جديد", "create repo", "new repo",
            "أنشئ ريبو", "انشئ ريبو",
        ),
        patterns=(
            r"(?:أن?شئ|اعمل|إنشاء).*مستودع",
            r"(?:أن?شئ|اعمل).*ريبو",
            r"create\s+repo", r"new\s+repo",
            r"مستودع\s*جديد",
        ),
        boost_words=("توكن", "token", "ghp_", "github", "خاص", "private"),
        priority=92,
    ),
    Capability(
        id="git_push",
        title_ar="دفع للمستودع",
        description_ar="git push للتغييرات على المستودع النشط",
        phrases=(
            "اعمل بوش", "بوش", "ادفع", "ادفع للمستودع", "git push", "push",
            "ارفع التعديلات", "ادفع التغييرات",
        ),
        patterns=(r"\bpush\b", r"بوش", r"ادفع", r"git\s+push"),
        boost_words=("توكن", "token", "ghp_", "origin"),
        priority=88,
    ),
    Capability(
        id="git_pull",
        title_ar="تحديث المستودع",
        description_ar="سحب آخر نسخة git pull",
        phrases=(
            "هات آخر نسخة", "هات اخر نسخه", "اسحب آخر نسخة", "حدّث المستودع",
            "حدث المستودع", "git pull", "pull", "آخر النسخة من المستودع",
        ),
        patterns=(r"git\s+pull", r"\bpull\b", r"آخر\s*نسخ", r"اخر\s*نسخ", r"حد[ّ]?ث\s*المستودع"),
        boost_words=("توكن", "token", "مستودع", "repo"),
        priority=87,
    ),
    Capability(
        id="repo_understand",
        title_ar="فهم المستودع",
        description_ar="المحرك يجمع المواد وجوراك يشرح ويجاوب عن المستودع",
        phrases=(
            "افهم المستودع", "فهم المستودع", "حلل المستودع", "اشرح المستودع",
            "فهم الريبو", "افهم الريبو", "understand repo", "analyze repo",
            "وش فيه المستودع", "ايه اللي في المستودع", "وصف المستودع",
            "كم عدد الاسطر", "كم عدد الأسطر", "عدد الاسطر", "عدد الأسطر",
            "كم ملف", "عدد الملفات", "ايه التقنيات", "ما هو المستودع",
            "اشرح المشروع", "وصف المشروع", "how many lines",
        ),
        patterns=(
            r"افهم\s*المستودع",
            r"فهم\s*المستودع",
            r"اشرح\s*المستودع",
            r"حلل\s*المستودع",
            r"understand\s*repo",
            r"analyze\s*repo",
            r"عدد\s*الأسطر",
            r"عدد\s*الاسطر",
            r"كم\s*سطر",
            r"عدد\s*الملفات",
            r"كم\s*ملف",
            r"اشرح\s*المشروع",
            r"وصف\s*المشروع",
            r"how\s*many\s*lines",
        ),
        boost_words=("مستودع", "ريبو", "repo", "github", "أسطر", "اسطر", "ملفات"),
        priority=88,
        needs_active_repo=False,
    ),
    Capability(
        id="clone_repo",
        title_ar="سحب مستودع",
        description_ar="سحب مستودع Git وفهمه",
        phrases=(
            "اسحب المستودع", "سحب المستودع", "clone", "git clone",
            "نزّل المستودع", "نزل المستودع", "جيب المستودع",
            "اسحب الريبو", "سحب ريبو",
        ),
        patterns=(
            r"اسحب|سحب",
            r"clone",
            r"github\.com|gitlab\.com",
            r"مستودع|ريبو|repo",
        ),
        boost_words=("توكن", "token", "ghp_", "github", "مستودع", "repo"),
        priority=90,
    ),
    Capability(
        id="generate_bot",
        title_ar="توليد بوت",
        description_ar="فهم مواصفة وتوليد مشروع بوت",
        phrases=(
            "اعمل بوت", "أنشئ بوت", "انشئ بوت", "ولّد بوت", "ولد بوت",
            "عايز بوت", "أريد بوت", "اريد بوت", "create bot", "generate bot",
            "بوت حجز", "بوت متجر", "بوت دعم",
        ),
        patterns=(
            r"اعمل\s*بوت", r"أن?شئ\s*بوت", r"عايز\s*بوت",
            r"generate\s*bot", r"create\s*bot",
            r"/[a-zA-Z][a-zA-Z0-9_]{1,32}\s*[-–—:]",
        ),
        boost_words=("أوامر", "اوامر", "كيان", "كيانات", "أزرار", "/start", "/help", "/book"),
        priority=95,
    ),
    Capability(
        id="static_analysis",
        title_ar="تحليل استاتيكي",
        description_ar="تشغيل StaticDevGate على المشروع النشط",
        phrases=(
            "تحليل استاتيكي", "تحقق استاتيكي", "افحص الكود", "تحقق من الكود",
            "static analysis", "static gate", "بوابة التحقق",
        ),
        patterns=(r"استاتيك", r"static", r"افحص.*كود", r"تحقق.*كود"),
        priority=70,
        needs_active_repo=True,
    ),
    Capability(
        id="package_health",
        title_ar="صحة الحزم",
        description_ar="فحص إصدارات PyPI للحزم",
        phrases=(
            "صحة الحزم", "حالة الحزم", "package health", "إصدارات", "outdated",
        ),
        patterns=(r"صحة\s*الحزم", r"package\s*health", r"outdated"),
        priority=70,
        needs_active_repo=True,
    ),
    Capability(
        id="upgrade_apply",
        title_ar="تطبيق ترقيات آمنة",
        description_ar="تطبيق ترقيات minor/yanked فقط",
        phrases=(
            "طبّق الترقيات", "طبق الترقيات", "طبّق الترقيات الآمنة",
            "apply upgrades", "apply safe upgrade",
        ),
        patterns=(r"طب[ّ]?ق\s*الترق", r"apply\s*safe\s*upgrade"),
        priority=72,
        needs_active_repo=True,
    ),
    Capability(
        id="upgrade_recommend",
        title_ar="توصيات الترقية",
        description_ar="عرض ترقيات مقترحة",
        phrases=(
            "توصيات الترقية", "ترقية آمنة", "recommend upgrade",
        ),
        patterns=(r"توصيات\s*الترق", r"ترقية\s*آمنة"),
        priority=68,
        needs_active_repo=True,
    ),
    Capability(
        id="repo_develop",
        title_ar="تطوير المستودع",
        description_ar="تطوير على المستودع النشط بعد الفهم",
        phrases=(
            "طوّر", "طور المستودع", "أضف أمر", "اضف امر", "عدّل البوت",
            "خطة تطوير", "develop",
        ),
        patterns=(r"طو[ّ]?ر", r"أ?ضف\s*أمر", r"develop"),
        priority=65,
        needs_active_repo=True,
    ),
    Capability(
        id="live_run",
        title_ar="تشغيل حي",
        description_ar="تشغيل تجريبي قصير ب توكن",
        phrases=(
            "تشغيل حي", "شغّل البوت", "جرب البوت", "live run", "run bot",
        ),
        patterns=(r"تشغيل\s*حي", r"live\s*run", r"جر[ّ]?ب\s*البوت"),
        priority=70,
        needs_project=True,
    ),
    Capability(
        id="help",
        title_ar="مساعدة",
        description_ar="شرح قدرات البوت",
        # ONLY pure help asks — never match "/help - مساعدة" inside a bot spec
        phrases=(
            "ماذا تستطيع", "ايه اللي تقدر", "ايه قدراتك", "ما هي قدراتك",
            "explain capabilities", "what can you do",
        ),
        patterns=(
            r"^help$",
            r"^مساعدة$",
            r"^المساعدة$",
            r"^القدرات$",
            r"^\s*help\s*$",
            r"^\s*مساعدة\s*$",
        ),
        priority=30,
        block_words=("اعمل بوت", "أنشئ بوت", "انشئ بوت", "عايز بوت", "/start", "/book", "كيان", "أوامر"),
    ),
]


def _looks_like_bot_spec(text: str) -> bool:
    """True when the user is describing a bot to generate — not asking for system help."""
    t = text or ""
    if re.search(
        r"اعمل\s*بوت|أن?شئ\s*بوت|ول[ّ]?د\s*بوت|عايز\s*بوت|أريد\s*بوت|اريد\s*بوت|"
        r"generate\s*bot|create\s*bot|bot\s*spec",
        t,
        re.I,
    ):
        return True
    # Spec starts with بوت + purpose description (common Arabic style)
    if re.match(r"^\s*بوت\b", t) and len(t.strip()) >= 18:
        if not re.search(
            r"(كم\s*سطر|عدد\s*الملفات|هات\s*الملف|اعرض\s*الملف|شوف\s*المستودع)",
            t,
            re.I,
        ):
            return True
    # Two or more explicit slash-commands → generation payload
    if len(re.findall(r"/[a-zA-Z][a-zA-Z0-9_]{1,32}", t)) >= 2:
        return True
    if re.search(r"(?m)^\s*[A-Za-z][A-Za-z0-9_]+\s*\([^\)]+\)\s*$", t):
        return True
    return False



def _normalize(text: str) -> str:
    t = (text or "").strip().lower()
    t = t.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    t = t.replace("ة", "ه")
    t = re.sub(r"\s+", " ", t)
    return t


def _score(cap: Capability, text: str, norm: str) -> float:
    score = 0.0
    # phrase hits
    for ph in cap.phrases:
        pn = _normalize(ph)
        if pn and pn in norm:
            score += 1.2 + min(len(pn), 20) * 0.02
    # regex
    for pat in cap.patterns:
        try:
            if re.search(pat, text, re.I) or re.search(pat, norm, re.I):
                score += 0.9
        except re.error:
            continue
    # boost / block
    for w in cap.boost_words:
        if _normalize(w) in norm:
            score += 0.35
    for w in cap.block_words:
        if _normalize(w) in norm:
            score -= 1.1
    if score <= 0:
        return 0.0
    # priority tie-break as slight bump
    score += cap.priority * 0.001
    return score


def _extract_clone_params(text: str) -> dict[str, Any]:
    params: dict[str, Any] = {}
    url_m = re.search(
        r"https?://[^\s]+|git@[^\s]+",
        text,
    )
    if url_m:
        params["url"] = url_m.group(0).rstrip(").,،")
    tok_m = re.search(r"\b(ghp_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b", text)
    if tok_m:
        params["token"] = tok_m.group(1)
    # «باستخدام التوكن» without token present → expect follow-up
    if re.search(r"توكن|token", text, re.I) and "token" not in params:
        params["await_token"] = True
    return params


class ChatRouter:
    def __init__(self, extra: list[Capability] | None = None) -> None:
        self._caps: list[Capability] = list(_BUILTIN)
        if extra:
            self._caps.extend(extra)

    def register(self, cap: Capability) -> None:
        """Call when a new system feature is added — chat will know it."""
        self._caps = [c for c in self._caps if c.id != cap.id]
        self._caps.append(cap)

    def list_capabilities(self) -> list[Capability]:
        return list(self._caps)

    def route(self, text: str) -> ChatRoute:
        raw = text or ""
        norm = _normalize(raw)
        if len(norm) < 2:
            return ChatRoute("", 0.0, "", raw_text=raw)

        scored: list[tuple[float, Capability]] = []
        for cap in self._caps:
            s = _score(cap, raw, norm)
            if s > 0:
                scored.append((s, cap))
        if not scored:
            return ChatRoute("", 0.0, "", raw_text=raw)

        scored.sort(key=lambda x: x[0], reverse=True)
        best_s, best = scored[0]
        # normalize confidence roughly
        conf = min(1.0, best_s / 2.5)
        alts = [c.title_ar for _, c in scored[1:4]]

        # Never hijack a bot-spec message into "help" because it contains /help - مساعدة
        if best.id == "help" and _looks_like_bot_spec(raw):
            for s, c in scored:
                if c.id == "generate_bot":
                    best_s, best = s, c
                    conf = min(1.0, max(best_s / 2.5, 0.9))
                    break
            else:
                return ChatRoute("", 0.0, "", raw_text=raw)

        params: dict[str, Any] = {}
        if best.id == "clone_repo":
            params = _extract_clone_params(raw)

        return ChatRoute(
            capability_id=best.id,
            confidence=conf,
            title_ar=best.title_ar,
            params=params,
            alternatives=alts,
            raw_text=raw,
        )

    def help_text(self) -> str:
        lines = ["🤖 *قدرات النظام (الشات يوجّه فقط — لا يكتب كود)*", ""]
        for c in sorted(self._caps, key=lambda x: -x.priority):
            lines.append(f"• *{c.title_ar}* — {c.description_ar}")
        lines.append("")
        lines.append("_مثال: «افتح الاستضافة» / «اسحب المستودع بالتوكن» / «افحص الكود»_")
        return "\n".join(lines)


_ROUTER: ChatRouter | None = None


def get_router() -> ChatRouter:
    global _ROUTER
    if _ROUTER is None:
        _ROUTER = ChatRouter()
    return _ROUTER


def route_message(text: str) -> ChatRoute:
    return get_router().route(text)
