"""
Stage 5 — Feature extraction.

Responsibilities:
    * Identify independent features from the keyword matches.
    * Each feature is atomic — never a composite of multiple features.
    * Produce a list of :class:`Feature` objects with name, display name,
      description, keywords, confidence, and related entities.
    * Do NOT merge features.  If the user says "warning and mute system",
      two separate features are produced.

A feature is triggered when one or more keywords in the ``"feature"``
category are present in the request.  Each canonical feature keyword
maps to exactly one :class:`Feature`.
"""

from __future__ import annotations

from typing import Dict, List

from ..analysis_report import AnalysisReport, Feature


# ---------------------------------------------------------------------------#
# Feature definitions
# ---------------------------------------------------------------------------#
# Maps keyword canonical → (machine_name, display_name, description,
#   related_entities)

_FEATURE_DEFS: Dict[str, tuple] = {
    "database": (
        "database",
        "Database / Persistent Storage",
        "Stores data persistently in a database.",
        [],
    ),
    "admin_panel": (
        "admin_panel",
        "Admin Panel / Dashboard",
        "Provides an administrative dashboard for managing the bot.",
        ["users"],
    ),
    "payments": (
        "payments",
        "Payment Processing",
        "Handles payments, billing, and checkout.",
        ["orders", "products"],
    ),
    "authentication": (
        "authentication",
        "User Authentication",
        "Verifies user identity via login, OTP, or 2FA.",
        ["users"],
    ),
    "scheduling": (
        "scheduling",
        "Scheduled Tasks / Cron Jobs",
        "Runs tasks on a schedule using cron-like mechanisms.",
        [],
    ),
    "notifications": (
        "notifications",
        "Push Notifications / Alerts",
        "Sends notifications and alerts to users.",
        ["users"],
    ),
    "file_upload": (
        "file_upload",
        "File Upload / Attachments",
        "Allows users to upload files and attachments.",
        [],
    ),
    "search": (
        "search",
        "Search Functionality",
        "Provides search and query capabilities.",
        [],
    ),
    "multi_language": (
        "multi_language",
        "Multi-language / i18n Support",
        "Supports multiple languages and translations.",
        [],
    ),
    "rate_limit": (
        "rate_limit",
        "Rate Limiting / Throttling",
        "Limits the rate of requests to prevent abuse.",
        ["users"],
    ),
    "logging": (
        "logging",
        "Logging / Audit Trail",
        "Logs actions and events for audit purposes.",
        [],
    ),
    "user_management": (
        "user_management",
        "User Management",
        "Manages users, members, and their roles.",
        ["users"],
    ),
    "content_management": (
        "content_management",
        "Content Management",
        "Manages posts, articles, and other content.",
        [],
    ),
    "analytics": (
        "analytics",
        "Analytics / Statistics",
        "Collects and displays analytics and statistics.",
        [],
    ),
    "webhook": (
        "webhook",
        "Webhook Integration",
        "Receives updates via webhook instead of polling.",
        [],
    ),
    "polling": (
        "polling",
        "Long Polling",
        "Receives updates via long polling.",
        [],
    ),
    "inline_mode": (
        "inline_mode",
        "Inline Mode",
        "Supports Telegram inline mode for in-chat queries.",
        [],
    ),
    "welcome": (
        "welcome",
        "Welcome / Greeting System",
        "Welcomes new users and sends greeting messages.",
        ["users"],
    ),
    "ban": (
        "ban",
        "Moderation (Ban / Kick / Mute / Warn)",
        "Bans, kicks, mutes, or warns users for rule violations.",
        ["users", "groups"],
    ),
    "subscription": (
        "subscription",
        "Subscription / Newsletter Management",
        "Manages user subscriptions and newsletter sign-ups.",
        ["users"],
    ),
    "shopping_cart": (
        "shopping_cart",
        "Shopping Cart",
        "Manages a shopping cart for e-commerce.",
        ["products", "orders"],
    ),
    "product_catalog": (
        "product_catalog",
        "Product Catalog",
        "Displays and manages a catalog of products.",
        ["products"],
    ),
    "order_management": (
        "order_management",
        "Order Management",
        "Manages orders, their status, and fulfillment.",
        ["orders"],
    ),
    "ai_chat": (
        "ai_chat",
        "AI Chat / Conversation",
        "Provides AI-powered chat and conversation capabilities.",
        [],
    ),
    "media_download": (
        "media_download",
        "Media Download",
        "Downloads media (videos, audio, images) from external sources.",
        [],
    ),
    "message_handler": (
        "message_handler",
        "Message Handler / Echo Reply",
        "Handles incoming text messages and sends a reply.",
        [],
    ),
}


# ---------------------------------------------------------------------------#
# Related-feature inference
# ---------------------------------------------------------------------------#

# When feature A is present, these features are likely related.
_FEATURE_RELATIONS: Dict[str, List[str]] = {
    "payments": ["shopping_cart", "order_management", "database"],
    "shopping_cart": ["product_catalog", "order_management", "database"],
    "order_management": ["payments", "database"],
    "admin_panel": ["user_management", "analytics"],
    "user_management": ["authentication", "admin_panel"],
    "welcome": ["user_management"],
    "ban": ["user_management", "logging"],
    "ai_chat": ["database"],
    "media_download": ["file_upload"],
    "notifications": ["user_management"],
    "subscription": ["notifications"],
    "authentication": ["user_management"],
    "rate_limit": ["logging"],
}


def run(state: Dict, report: AnalysisReport) -> List[str]:
    """Extract independent features from the keyword matches.

    Writes:
        report.features ← list of Feature objects (each independent).
        state["feature_names"] ← set of feature machine names.
    """
    warnings: List[str] = []

    keyword_canonicals: set = state.get("keyword_canonicals", set())
    kw_by_name = {kw.keyword: kw for kw in report.keywords}

    features: List[Feature] = []
    # NOTE: populated below; if still empty after keyword scan, a
    # minimal message_handler feature is injected so simple bot
    # requests (e.g. "اعمل بوت بيرد ب هاي") are not blocked.

    for canonical, (machine_name, display_name, description, related_entities) in _FEATURE_DEFS.items():
        if canonical in keyword_canonicals:
            kw = kw_by_name[canonical]
            features.append(Feature(
                name=machine_name,
                display_name=display_name,
                description=description,
                keywords=[canonical],
                confidence=kw.confidence,
                related_entities=list(related_entities),
                related_features=[],
            ))

    # Post-process: fill in related_features based on co-occurrence
    feature_names = [f.name for f in features]
    for feat in features:
        relations = _FEATURE_RELATIONS.get(feat.name, [])
        for rel in relations:
            if rel in feature_names and rel != feat.name:
                feat.related_features.append(rel)

    # Fallback: any Telegram-bot request without matched feature keywords
    # still needs at least one feature or the blueprint validator blocks.
    if not features:
        machine_name, display_name, description, related_entities = _FEATURE_DEFS[
            "message_handler"
        ]
        features.append(Feature(
            name=machine_name,
            display_name=display_name,
            description=description,
            keywords=["message_handler"],
            confidence=0.7,
            related_entities=list(related_entities),
            related_features=[],
        ))
        feature_names = [f.name for f in features]
        warnings.append(
            "No explicit features matched; defaulted to message_handler "
            "for a basic Telegram reply bot."
        )

    report.features = features
    state["feature_names"] = set(feature_names)

    return warnings


__all__ = ["run"]
