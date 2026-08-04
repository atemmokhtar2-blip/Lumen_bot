"""
Stage 9 — Missing information detection.

Responsibilities:
    * Identify information that the user did not provide but that the
      downstream engines need.
    * Generate clear questions to ask the user.
    * For each missing piece, provide suggested options and a sensible
      default where possible.
    * Mark each missing piece as required or optional.
    * **Never guess** — only detect absence and ask.

Missing information categories:
    * ``bot_name`` — no project name was specified.
    * ``bot_token`` — no Telegram bot token was mentioned (always required
      but usually supplied at runtime).
    * ``update_mode`` — no polling vs webhook choice was made.
    * ``database_choice`` — features need a database but none was
      explicitly chosen.
    * ``language_choice`` — no human language for bot responses.
    * ``ai_api_key`` — AI features detected but no API key mentioned.
    * ``payment_provider`` — payments feature detected but no provider
      named.
"""

from __future__ import annotations

from typing import Dict, List

from ..analysis_report import AnalysisReport, MissingInfo


# ---------------------------------------------------------------------------#
# Main entry
# ---------------------------------------------------------------------------#

def run(state: Dict, report: AnalysisReport) -> List[str]:
    """Detect missing information and generate questions.

    Writes:
        report.missing_info ← list of MissingInfo objects.
        report.questions    ← list of question strings (for convenience).
    """
    warnings: List[str] = []

    missing: List[MissingInfo] = []
    keyword_canonicals: set = state.get("keyword_canonicals", set())
    feature_names: set = state.get("feature_names", set())
    bot_type: str = state.get("primary_bot_type", "general")

    # 1. Bot name — usually the user doesn't specify a project name
    # We can derive a default from the bot type, so this is optional.
    missing.append(MissingInfo(
        field="bot_name",
        question="What should the bot project be called?",
        options=[
            f"{bot_type}_bot",
            "my_telegram_bot",
            "telegram_bot",
        ],
        default=f"{bot_type}_bot",
        required=False,
    ))

    # 2. Bot token — always required at runtime, but we don't hardcode it.
    if "authentication" not in feature_names:
        missing.append(MissingInfo(
            field="bot_token",
            question=(
                "What is the Telegram bot token? "
                "(This is required to run the bot. You can get it from @BotFather.)"
            ),
            options=["Set via environment variable BOT_TOKEN"],
            default="env:BOT_TOKEN",
            required=False,  # Not needed for code generation, only runtime
        ))

    # 3. Update mode — polling vs webhook
    # Default to polling for Telegram bots when the user did not specify.
    # Blocking generation solely for this is wrong: every simple bot can
    # ship with polling, and webhook remains an explicit production choice.
    has_polling = "polling" in keyword_canonicals
    has_webhook = "webhook" in keyword_canonicals
    if not has_polling and not has_webhook:
        missing.append(MissingInfo(
            field="update_mode",
            question="How should the bot receive updates from Telegram?",
            options=["polling (recommended for development)", "webhook (recommended for production)"],
            default="polling",
            required=False,
        ))

    # 4. Database choice — if features need a database but none was chosen
    db_techs = [
        t for t in report.technologies if t.category == "database"
    ]
    db_needing_features = [
        f for f in report.features if f.name in [
            "user_management", "admin_panel", "order_management",
            "shopping_cart", "product_catalog", "payments",
            "subscription", "analytics", "logging", "ban", "welcome",
            "ai_chat", "scheduling", "database",
        ]
    ]
    if db_needing_features and not any(t.explicit for t in db_techs):
        missing.append(MissingInfo(
            field="database_choice",
            question=(
                "Which database should the bot use for persistent storage? "
                f"The following features need a database: "
                f"{', '.join(f.name for f in db_needing_features)}."
            ),
            options=["SQLite (recommended for small bots)", "PostgreSQL", "MySQL", "MongoDB"],
            default="SQLite",
            required=True,
        ))

    # 5. Language for bot responses — if multi_language is not a feature
    if "multi_language" not in feature_names:
        language = state.get("language", "en")
        if language == "ar":
            missing.append(MissingInfo(
                field="response_language",
                question="What language should the bot respond in?",
                options=["Arabic", "English", "Both Arabic and English"],
                default="Arabic",
                required=False,
            ))
        elif language == "en":
            missing.append(MissingInfo(
                field="response_language",
                question="What language should the bot respond in?",
                options=["English", "Arabic", "Both Arabic and English"],
                default="English",
                required=False,
            ))

    # 6. AI API key — if AI features detected
    if "ai_assistant" in bot_type or "ai_chat" in feature_names:
        ai_techs = [
            t for t in report.technologies
            if t.category == "external_api" and "openai" in t.name.lower()
        ]
        if not ai_techs:
            missing.append(MissingInfo(
                field="ai_provider",
                question=(
                    "Which AI provider should the bot use for AI features?"
                ),
                options=["OpenAI", "Anthropic Claude", "Google Gemini", "Local LLM"],
                default="OpenAI",
                required=True,
            ))
        missing.append(MissingInfo(
            field="ai_api_key",
            question=(
                "What is the API key for the AI provider? "
                "(This is required to run AI features. It will be read from "
                "an environment variable.)"
            ),
            options=["Set via environment variable OPENAI_API_KEY"],
            default="env:OPENAI_API_KEY",
            required=False,  # Not needed for code generation, only runtime
        ))

    # 7. Payment provider — if payments feature detected
    if "payments" in feature_names:
        payment_techs = [
            t for t in report.technologies
            if t.category == "external_api" and "payment" in t.role.lower()
        ]
        if not payment_techs:
            missing.append(MissingInfo(
                field="payment_provider",
                question=(
                    "Which payment provider should the bot use?"
                ),
                options=["Stripe", "PayPal", "Square", "Crypto"],
                default="Stripe",
                required=True,
            ))

    # 8. Group context — if group_admin features detected
    if bot_type == "group_admin":
        if "ban" in feature_names:
            missing.append(MissingInfo(
                field="moderation_rules",
                question=(
                    "What are the moderation rules? "
                    "(e.g., how many warnings before a ban?)"
                ),
                options=[
                    "3 warnings then ban",
                    "1 warning then mute, then ban",
                    "Immediate ban for spam",
                ],
                default="3 warnings then ban",
                required=False,
            ))

    # 9. Download sources — if downloader bot
    if bot_type == "downloader":
        yt_techs = [
            t for t in report.technologies if "yt-dlp" in t.name.lower()
        ]
        if not yt_techs:
            missing.append(MissingInfo(
                field="download_sources",
                question=(
                    "Which platforms should the downloader support?"
                ),
                options=["YouTube", "Instagram", "TikTok", "All supported by yt-dlp"],
                default="YouTube",
                required=False,
            ))

    report.missing_info = missing

    # Build the questions list for convenience
    report.questions = [m.question for m in missing if m.required]

    return warnings


__all__ = ["run"]
