"""Lumen — single source of truth for platform identity.

Every surface (chat prompts, API, watermark, paths, telemetry, docs claims)
MUST read brand strings from this module. Do not hardcode product names elsewhere.
"""
from __future__ import annotations

# ── Canonical product identity (never fork these in feature code) ──────────
PRODUCT_NAME: str = "Lumen"
PRODUCT_NAME_AR: str = "Lumen"
PRODUCT_ID: str = "lumen"
REPO_NAME: str = "Lumen_bot"
REPO_URL: str = "https://github.com/atemmokhtar2-blip/Lumen_bot"

# ── Public service identifiers ─────────────────────────────────────────────
API_SERVICE_ID: str = "lumen-api"
TELEGRAM_SERVICE_ID: str = "lumen-telegram"
API_TITLE: str = "Lumen B2B API"
API_VERSION: str = "1.0.0"

# ── User-visible brand ─────────────────────────────────────────────────────
WATERMARK_TEXT: str = "⚡ Powered by Lumen"
SUPPORT_EMAIL: str = "support@lumen.bot"
WELCOME_EN: str = "Welcome to Lumen"
WELCOME_AR: str = "مرحباً بك في Lumen"

# ── Filesystem defaults ────────────────────────────────────────────────────
DOTDIR_NAME: str = ".lumen"
VAR_LIB_PATH: str = "/var/lib/lumen"
OUTPUT_DIR_DEFAULT: str = "/tmp/lumen_output"
CONTROL_PLANE_DEFAULT: str = "/tmp/lumen_control"
REDIS_KEY_PREFIX: str = "lumen:ma:"

# ── Chat / LLM — who the model is ──────────────────────────────────────────
SYSTEM_PROMPT_IDENTITY_AR: str = (
    "أنت Lumen: منصة توليد بوتات تيليجرام احترافية."
)
SYSTEM_PROMPT_IDENTITY_LONG_AR: str = (
    "أنت Lumen: منصة توليد بوتات تيليجرام احترافية ومساعد هندسي للمشاريع."
)
SYSTEM_PROMPT_ENGINE_NOTE_AR: str = (
    "لا تسحب مستودعات ولا تعدّل ملفات بنفسك — التنفيذ دائمًا على محركات Lumen."
)

# ── Forbidden legacy brands (must never reappear) ──────────────────────────
FORBIDDEN_BRAND_TOKENS: tuple[str, ...] = (
    "maestro",
    "ميسترو",
    "maya",
    "capability_maestro",
    "capability-maestro",
    "ai_agent_7h",
    "ai-agent-7h",
    "ai agent 7h",
)


def contains_forbidden_brand(text: str) -> bool:
    low = (text or "").lower()
    for tok in FORBIDDEN_BRAND_TOKENS:
        if tok.lower() in low:
            return True
    return False


def system_identity_line(*, long: bool = False) -> str:
    return SYSTEM_PROMPT_IDENTITY_LONG_AR if long else SYSTEM_PROMPT_IDENTITY_AR
