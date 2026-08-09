"""Inline keyboards for the Spec Builder bot."""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from telegram_bot_engine.spec_core.builder import BuilderSession
from telegram_bot_engine.spec_core.registry import by_category


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("1) اسم البوت", callback_data="b:name")],
            [InlineKeyboardButton("2) وصف البوت", callback_data="b:desc")],
            [InlineKeyboardButton("3) القدرات", callback_data="b:cats")],
            [InlineKeyboardButton("4) ملخص", callback_data="b:summary")],
            [InlineKeyboardButton("✅ توليد المشروع", callback_data="b:build")],
            [InlineKeyboardButton("🔄 إعادة ضبط", callback_data="b:reset")],
        ]
    )


def categories_menu() -> InlineKeyboardMarkup:
    rows = []
    for cat in by_category().keys():
        rows.append([InlineKeyboardButton(f"📁 {cat}", callback_data=f"b:cat:{cat}")])
    rows.append([InlineKeyboardButton("« القائمة", callback_data="b:home")])
    return InlineKeyboardMarkup(rows)


def capabilities_menu(session: BuilderSession, category: str) -> InlineKeyboardMarkup:
    rows = []
    caps = by_category().get(category) or []
    for cap in caps:
        mark = "✅" if session.is_on(cap.key) else "⬜"
        rows.append(
            [
                InlineKeyboardButton(
                    f"{mark} {cap.key} — {cap.description_ar}",
                    callback_data=f"b:tog:{cap.key}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton("« التصنيفات", callback_data="b:cats"),
            InlineKeyboardButton("القائمة", callback_data="b:home"),
        ]
    )
    return InlineKeyboardMarkup(rows)


def after_build_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("الملخص", callback_data="b:summary")],
            [InlineKeyboardButton("القائمة", callback_data="b:home")],
        ]
    )
