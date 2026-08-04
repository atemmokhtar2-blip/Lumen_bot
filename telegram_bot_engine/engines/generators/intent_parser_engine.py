"""
Intent parser engine — converts the user request into a structured intent.

Simulates understanding by:
1. Scoring domain signals (not first-keyword-wins)
2. Extracting explicit /commands from the text
3. Extracting capability phrases (موظفين، مهام، حضور…)
4. Building a command list the composer can use without hard profiles

Downstream engines rely on the ``intent`` artefact shape only.
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

from ...core.context import GenerationContext
from ...core.result import StageResult
from ..base.base_engine import BaseEngine


# Domain scores: each tuple is (bot_type, positive keywords, negative keywords)
_DOMAIN_SIGNALS: List[Tuple[str, List[str], List[str]]] = [
    (
        "company_ops",
        [
            "شركة", "مؤسسة", "موظفين", "موظفين", "موظف", "employees", "company",
            "حضور", "انصراف", "attendance", "check-in", "checkout",
            "رواتب", "payroll", "hr", "موارد بشرية",
            "تقارير يومية", "تقرير يومي", "daily report",
        ],
        ["جروب", "مجموعة", "group", "ban", "mute"],
    ),
    (
        "group_admin",
        [
            "جروب", "جروبات", "مجموعة", "مجموعات", "group", "groups",
            "مشرف", "moderat", "حظر", "كتم", "تحذير", "ban", "mute", "warn",
            "إدارة مجموعات", "ادارة مجموعات", "group admin",
        ],
        ["شركة", "موظفين", "حضور", "انصراف", "رواتب"],
    ),
    (
        "store",
        ["متجر", "متجري", "store", "shop", "ecommerce", "منتجات", "سلة", "طلب"],
        [],
    ),
    (
        "downloader",
        ["تحميل", "يوتيوب", "youtube", "download", "downloader", "فيديو من رابط"],
        [],
    ),
    (
        "ai_assistant",
        ["ذكاء اصطناعي", "chatgpt", "gpt", "openai", "ai assistant"],
        [],
    ),
    (
        "task_manager",
        ["مهام", "مهمة", "todo", "task", "تذكير", "reminder"],
        ["شركة", "موظفين"],  # company_ops wins if both
    ),
]

# Capability → suggested command names (understanding → structure)
_CAPABILITY_COMMANDS: List[Tuple[List[str], str, str, bool]] = [
    # keywords, command_name, description, admin_only
    (["موظفين", "موظف", "employees", "staff"], "employees", "إدارة الموظفين / Employees", True),
    (["مهام", "مهمة", "tasks", "task"], "tasks", "إدارة المهام / Tasks", False),
    (["حضور", "انصراف", "attendance", "check-in"], "attendance", "تسجيل حضور وانصراف", False),
    (["تقرير", "تقارير", "report", "reports"], "report", "التقارير", True),
    (["رواتب", "payroll"], "payroll", "الرواتب", True),
    (["حظر", "ban"], "ban", "حظر عضو", True),
    (["كتم", "mute"], "mute", "كتم عضو", True),
    (["تحذير", "warn"], "warn", "تحذير عضو", True),
    (["إحصائ", "احصائ", "stats"], "stats", "إحصائيات", False),
    (["ترحيب", "welcome"], "welcome_settings", "إعدادات الترحيب", True),
    (["منتجات", "products"], "products", "المنتجات", False),
    (["سلة", "cart"], "cart", "السلة", False),
    (["طلب", "order"], "order", "الطلبات", False),
    (["تحميل", "download"], "download", "تحميل", False),
    (["اسأل", "ask", "سؤال"], "ask", "اسأل البوت", False),
]


class IntentParserEngine(BaseEngine):
    """Parses a natural-language request into a structured intent."""

    def __init__(self) -> None:
        super().__init__(
            name="intent_parser",
            version="2.0.0",
            description=(
                "Understands the user request: domain, features, explicit "
                "commands, and capability phrases — without fixed wrong profiles."
            ),
            tags=["understanding", "intent", "nlp-heuristic"],
            metadata={"phase": "understanding"},
        )

    def execute(self, context: GenerationContext) -> StageResult:
        request = context.request.strip()
        if not request:
            return self.failed(["Empty request — nothing to parse."])

        self._log.info("Parsing intent", {"request_len": len(request)})

        bot_type, scores = self._classify(request)
        features = self._extract_features(request, bot_type)
        explicit_commands = self._extract_explicit_commands(request)
        capability_commands = self._extract_capability_commands(request)
        language = self._detect_language(request)
        framework = self._detect_framework(request)

        # Merge commands: explicit first, then capabilities, unique by name
        commands: List[Dict] = []
        seen = set()
        for c in explicit_commands + capability_commands:
            n = c["name"]
            if n in seen:
                continue
            seen.add(n)
            commands.append(c)

        # Always have start/help as baseline understanding of a bot UX
        for base in (
            {"name": "start", "description": "بدء التشغيل", "admin_only": False},
            {"name": "help", "description": "قائمة الأوامر", "admin_only": False},
        ):
            if base["name"] not in seen:
                commands.insert(0 if base["name"] == "start" else len(commands), base)
                seen.add(base["name"])

        intent: Dict = {
            "raw": request,
            "bot_type": bot_type,
            "features": features,
            "commands": commands,
            "domain_scores": scores,
            "language": language,
            "language_version": "3.11",
            "framework": framework,
            "summary": self._summary(request, bot_type, commands),
        }

        context.set("intent", intent)
        self._log.info(
            "Intent parsed",
            {
                "bot_type": bot_type,
                "features": features,
                "command_count": len(commands),
            },
        )
        return self.ok(outputs={"intent": intent})

    # ------------------------------------------------------------------
    # Classification — score domains, don't first-match blindly
    # ------------------------------------------------------------------

    @staticmethod
    def _classify(request: str) -> Tuple[str, Dict[str, int]]:
        text = request.lower()
        scores: Dict[str, int] = {}
        for bot_type, positive, negative in _DOMAIN_SIGNALS:
            score = 0
            for kw in positive:
                if kw.lower() in text or kw in request:
                    score += 2 if len(kw) > 3 else 1
            for kw in negative:
                if kw.lower() in text or kw in request:
                    score -= 3
            scores[bot_type] = score

        # Special rule: "إدارة" alone is weak; with company words → company_ops
        if any(w in request for w in ("شركة", "موظفين", "موظف", "حضور", "انصراف")):
            scores["company_ops"] = scores.get("company_ops", 0) + 5
            scores["group_admin"] = scores.get("group_admin", 0) - 4

        # Explicit group words boost group_admin
        if any(w in request for w in ("جروب", "مجموعة", "مجموعات", "group")):
            scores["group_admin"] = scores.get("group_admin", 0) + 4

        best = "general"
        best_score = 0
        for k, v in scores.items():
            if v > best_score:
                best_score = v
                best = k
        if best_score <= 0:
            return "general", scores
        return best, scores

    @staticmethod
    def _extract_features(request: str, bot_type: str) -> List[str]:
        lowered = request.lower()
        feature_map: Dict[str, List[str]] = {
            "database": ["database", "db", "store data", "قاعدة", "بيانات", "موظفين", "مهام"],
            "admin_panel": ["admin", "panel", "لوحة", "تحكم", "مشرف"],
            "payments": ["payment", "pay", "checkout", "دفع", "مدفوعات", "stripe"],
            "ai": ["ai", "gpt", "ذكاء", "اصطناعي"],
            "media_download": ["download", "youtube", "تحميل", "فيديو"],
            "scheduling": ["schedule", "cron", "جدولة", "مجدول", "تذكير"],
            "employees": ["موظفين", "موظف", "employees", "staff", "hr"],
            "tasks": ["مهام", "مهمة", "tasks", "todo"],
            "attendance": ["حضور", "انصراف", "attendance"],
            "reports": ["تقرير", "تقارير", "report"],
            "moderation": ["حظر", "كتم", "تحذير", "ban", "mute", "warn"],
            "welcome": ["ترحيب", "welcome", "أعضاء جدد", "اعضاء جدد"],
        }
        detected: List[str] = []
        for feature, keywords in feature_map.items():
            if any(kw in lowered or kw in request for kw in keywords):
                detected.append(feature)

        # Tag domain feature
        if bot_type and bot_type not in detected:
            detected.append(bot_type)
        return detected

    @staticmethod
    def _extract_explicit_commands(request: str) -> List[Dict]:
        """Find /command mentions in the user text."""
        found: List[Dict] = []
        seen = set()
        for m in re.finditer(r"/([a-zA-Z_][a-zA-Z0-9_]{0,31})", request):
            name = m.group(1).lower()
            if name in seen:
                continue
            seen.add(name)
            # Try to grab a short Arabic/English description after the command
            tail = request[m.end(): m.end() + 60]
            desc_m = re.match(r"\s*[—\-:]?\s*([^\n/]{3,50})", tail)
            desc = desc_m.group(1).strip() if desc_m else f"Command /{name}"
            found.append({
                "name": name,
                "description": desc,
                "admin_only": name in {"ban", "mute", "warn", "settings", "payroll"},
            })
        return found

    @staticmethod
    def _extract_capability_commands(request: str) -> List[Dict]:
        out: List[Dict] = []
        seen = set()
        for keywords, name, desc, admin in _CAPABILITY_COMMANDS:
            if any(k in request or k.lower() in request.lower() for k in keywords):
                if name in seen:
                    continue
                seen.add(name)
                out.append({
                    "name": name,
                    "description": desc,
                    "admin_only": admin,
                })
        return out

    @staticmethod
    def _detect_language(request: str) -> str:
        if re.search(r"[\u0600-\u06FF]", request):
            return "ar"
        return "en"

    @staticmethod
    def _detect_framework(request: str) -> str:
        low = request.lower()
        if "aiogram" in low:
            return "aiogram"
        if "pyrogram" in low:
            return "pyrogram"
        if "telethon" in low:
            return "telethon"
        return "python-telegram-bot"

    @staticmethod
    def _summary(request: str, bot_type: str, commands: List[Dict]) -> str:
        names = ", ".join(c["name"] for c in commands[:12])
        return f"type={bot_type}; commands=[{names}]; request_len={len(request)}"


__all__ = ["IntentParserEngine"]
