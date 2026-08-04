"""
AI Agent 7h Bot — Telegram interface for the Generation Engine.

Runs on Railway (or any host). Requires:
  TELEGRAM_BOT_TOKEN  — BotFather token
  Optional:
  ALLOWED_USER_IDS    — comma-separated Telegram user IDs (empty = allow all)
  OUTPUT_DIR          — where generated projects are written (default: /tmp/generated)
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import tempfile
import zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

load_dotenv()

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("ai_agent_7h_bot")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
ALLOWED_USER_IDS = {
    int(x.strip())
    for x in os.getenv("ALLOWED_USER_IDS", "").split(",")
    if x.strip().isdigit()
}
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "/tmp/generated"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
PORT = int(os.getenv("PORT", "8080"))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_allowed(user_id: int | None) -> bool:
    if not ALLOWED_USER_IDS:
        return True
    return user_id is not None and user_id in ALLOWED_USER_IDS


def _looks_like_bot_token(text: str) -> bool:
    import re
    return bool(re.match(r"^\d{6,12}:[A-Za-z0-9_-]{30,}$", (text or "").strip()))


async def _handle_live_deploy_token(message, context, token: str, pending: dict) -> None:
    """Spec 065: validate token, deploy, health-check, functional tests."""
    status = await message.reply_text(
        "🔐 جاري التحقق من التوكن وتشغيل Live Deployment..."
    )
    project_path = pending.get("project_path")
    owner_id = pending.get("owner_user_id")

    def _run():
        from telegram_bot_engine.engines.generators.live_deployment import (
            LiveDeploymentEngine,
        )
        engine = LiveDeploymentEngine()
        return engine.run_live_deployment(
            project_path=project_path,
            bot_token=token,
            owner_user_id=owner_id,
        )

    try:
        report = await asyncio.to_thread(_run)
    except Exception as e:
        logger.exception("Live deployment failed")
        await status.edit_text(f"❌ فشل Live Deployment: {type(e).__name__}")
        return
    finally:
        # Drop token from any local vars as soon as possible
        token = ""  # noqa: F841

    context.user_data.pop("pending_deploy", None)

    tv = report.token_validation
    dep = report.deployment
    health = report.health
    lines = [
        f"{'✅' if report.passed else '⚠️'} *تقرير Live Deployment*",
        f"• الحكم: `{_escape_md(report.verdict)}`",
        f"• الجودة: {report.quality_score:.0%}",
    ]
    if tv:
        lines.append(
            f"• التوكن: {'صالح' if tv.valid else 'غير صالح'}"
            + (f" (@{_escape_md(tv.bot_username)})" if tv.bot_username else "")
        )
    if dep:
        lines.append(
            f"• التشغيل: `{_escape_md(dep.status)}`"
            + (" (dry-run)" if dep.dry_run else " — عملية حقيقية")
        )
        if dep.message:
            lines.append(f"  {_escape_md(dep.message[:200])}")
    if health:
        lines.append(
            f"• الصحة: {'Online' if health.online else 'Offline'}"
            f" ({health.latency_ms:.0f}ms)"
        )
    lines.append(
        f"• الاختبارات: {report.tests_passed}/{report.tests_total} ناجحة"
    )
    for t in report.functional_tests[:5]:
        mark = {"pass": "✅", "fail": "❌", "skip": "⏭", "error": "💥"}.get(t.status, "•")
        lines.append(f"  {mark} {_escape_md(t.name)}: {_escape_md(t.message[:80])}")
    if report.findings:
        lines.append("• ملاحظات:")
        for f in report.findings[:4]:
            lines.append(f"  - {_escape_md(f.message[:120])}")
    if tv and tv.bot_username and dep and dep.status == "running":
        lines.append(
            f"\n🚀 البوت شغال — افتح @{_escape_md(tv.bot_username)} وأرسل /start"
        )

    await _safe_edit_text(status, "\n".join(lines), use_markdown=True)


def _escape_md(text: object) -> str:
    """Escape Telegram legacy Markdown special characters in dynamic text."""
    s = str(text) if text is not None else ""
    for ch in ("\\", "`", "*", "_", "[", "]", "(", ")"):
        s = s.replace(ch, f"\\{ch}")
    return s


async def _safe_edit_text(message, text: str, *, use_markdown: bool = True) -> None:
    """edit_text with Markdown; fall back to plain text if Telegram rejects entities."""
    if use_markdown:
        try:
            await message.edit_text(text, parse_mode=ParseMode.MARKDOWN)
            return
        except Exception as e:
            err = str(e).lower()
            if "can't parse entities" in err or "parse entities" in err:
                logger.warning("Markdown parse failed, retrying as plain text: %s", e)
            else:
                raise
    # Plain text fallback (strip simple md markers for readability)
    plain = (
        text.replace("\\", "")
        .replace("*", "")
        .replace("`", "")
        .replace("_", "")
    )
    await message.edit_text(plain)


def _make_zip_from_path(project_path: str | Path) -> Path | None:
    """Create a zip of the generated project. Returns zip path or None."""
    project_path = Path(project_path)
    if not project_path.exists():
        return None

    zip_path = project_path.parent / f"{project_path.name}.zip"
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(project_path):
                for name in files:
                    full = Path(root) / name
                    arc = full.relative_to(project_path)
                    zf.write(full, arc)
        return zip_path
    except Exception as e:
        logger.exception("Failed to create zip: %s", e)
        return None


def _run_generation(request: str, work_dir: Path):
    """Synchronous call into the generation engine (runs in a thread)."""
    from telegram_bot_engine import generate_bot

    return generate_bot(request, work_dir=str(work_dir))


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not _is_allowed(user.id if user else None):
        await update.message.reply_text("⛔ غير مصرح لك باستخدام هذا البوت.")
        return

    text = (
        "👋 *مرحباً بك في AI Agent 7h Bot*\n\n"
        "أنا محرك توليد بوتات تليجرام.\n"
        "أرسل لي وصفاً باللغة العربية أو الإنجليزية لما تريده، وسأولّد مشروعاً جاهزاً.\n\n"
        "*أمثلة:*\n"
        "• اعمل بوت متجر إلكتروني\n"
        "• بوت إدارة مجموعات مع نظام نقاط\n"
        "• Telegram bot for customer support with tickets\n\n"
        "الأوامر:\n"
        "/start — هذه الرسالة\n"
        "/status — حالة النظام\n"
        "/help — مساعدة\n\n"
        "⚠️ ملاحظة: المحركات ما زالت قيد التطوير، قد تكون النتيجة جزئية."
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start_cmd(update, context)


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not _is_allowed(user.id if user else None):
        await update.message.reply_text("⛔ غير مصرح.")
        return

    try:
        from telegram_bot_engine import bootstrap
        registry, orchestrator, manager = bootstrap()
        engine_count = len(getattr(registry, "_engines", {}) or getattr(registry, "engines", {}) or {})
        # fallback count
        if not engine_count:
            try:
                engine_count = len(manager._engines) if hasattr(manager, "_engines") else "?"
            except Exception:
                engine_count = "?"
        msg = (
            f"✅ النظام يعمل\n"
            f"• المحركات المسجّلة: {engine_count}\n"
            f"• مجلد الإخراج: `{OUTPUT_DIR}`\n"
            f"• ملاحظة: لا تزال هناك محركات قيد الإضافة."
        )
    except Exception as e:
        msg = f"⚠️ خطأ أثناء فحص الحالة:\n`{e}`"
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.message
    if not message or not message.text:
        return

    if not _is_allowed(user.id if user else None):
        await message.reply_text("⛔ غير مصرح لك باستخدام هذا البوت.")
        return

    request = message.text.strip()
    if not request or request.startswith("/"):
        return

    # Spec 065 — if user is sending a bot token after successful generation
    pending = (context.user_data or {}).get("pending_deploy")
    if pending and _looks_like_bot_token(request):
        await _handle_live_deploy_token(message, context, request, pending)
        return

    if len(request) < 5:
        await message.reply_text("الوصف قصير جداً. أرسل وصفاً أوضح للبوت المطلوب.")
        return

    status_msg = await message.reply_text(
        "⏳ جاري تحليل الطلب وتشغيل المحركات...\n"
        "قد يستغرق الأمر دقيقة أو أكثر (خاصة في الطلب الأول لأن المحركات تُحمَّل).\n"
        "ملاحظة: لا تزال هناك محركات قيد الإضافة."
    )
    await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.TYPING)

    work_dir = Path(tempfile.mkdtemp(prefix="botgen_", dir=str(OUTPUT_DIR)))

    try:
        result = await asyncio.to_thread(_run_generation, request, work_dir)

        if result is None:
            await status_msg.edit_text("❌ فشل التوليد (نتيجة فارغة).")
            return

        success = getattr(result, "success", False)
        project_path = getattr(result, "project_path", None)
        errors = getattr(result, "errors", []) or []
        stages = getattr(result, "stages", []) or []

        ok_stages = sum(1 for s in stages if getattr(s, "success", False))
        total_stages = len(stages)

        summary_lines = [
            f"{'✅' if success else '⚠️'} *نتيجة التوليد*",
            f"• النجاح: {'نعم' if success else 'جزئي / فشل'}",
            f"• المراحل الناجحة: {ok_stages}/{total_stages}",
        ]
        if project_path:
            summary_lines.append(f"• المسار: `{_escape_md(project_path)}`")
        if errors:
            summary_lines.append("• أخطاء:")
            for e in errors[:5]:
                # Dynamic engine errors often contain _, *, ` — escape them
                summary_lines.append(f"  - {_escape_md(e)}")

        summary_lines.append(
            "\n_ملاحظة: لا تزال هناك محركات قيد التطوير، قد تكون بعض الأجزاء غير مكتملة._"
        )

        await _safe_edit_text(status_msg, "\n".join(summary_lines), use_markdown=True)

        # Try to send zip if project exists
        if project_path and Path(project_path).exists():
            zip_path = _make_zip_from_path(project_path)
            if zip_path and zip_path.exists() and zip_path.stat().st_size > 0:
                size_mb = zip_path.stat().st_size / (1024 * 1024)
                if size_mb < 48:  # Telegram limit ~50MB
                    await message.reply_document(
                        document=zip_path.open("rb"),
                        filename=zip_path.name,
                        caption="📦 المشروع المُولَّد (zip)",
                    )
                else:
                    await message.reply_text(
                        f"📦 تم إنشاء المشروع لكن حجم الـ zip كبير ({size_mb:.1f} MB). "
                        "يمكنك الوصول إليه من السيرفر."
                    )
            else:
                await message.reply_text("تم التوليد لكن تعذر إنشاء ملف zip.")

            # Spec 065: after successful project, offer live deploy via token
            if success:
                context.user_data["pending_deploy"] = {
                    "project_path": str(project_path),
                    "owner_user_id": user.id if user else None,
                }
                await message.reply_text(
                    "✅ تم إنشاء المشروع بنجاح.\n\n"
                    "إذا أردت تجربة البوت مباشرة، أرسل:\n"
                    "Telegram Bot Token\n\n"
                    "(من @BotFather — لن يتم حفظ التوكن في الكود أو اللوجات)"
                )
        elif not success:
            await message.reply_text(
                "لم يُنشأ مشروع. جرّب وصفاً أبسط أو أوضح."
            )

    except Exception as e:
        logger.exception("Generation failed")
        err_text = _escape_md(str(e)[:400])
        await _safe_edit_text(
            status_msg,
            f"❌ حدث خطأ أثناء التوليد:\n`{err_text}`\n\n"
            "قد يكون السبب محركات غير مكتملة بعد. حاول لاحقاً.",
            use_markdown=True,
        )
    finally:
        # Optional cleanup of very old temp dirs can be added later.
        # Keep the last result for inspection on the server.
        pass


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Exception while handling update: %s", context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "حدث خطأ داخلي. حاول مرة أخرى لاحقاً."
            )
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Health server (Railway expects a process listening on $PORT)
# ---------------------------------------------------------------------------

class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, format, *args):
        return  # silence access logs


def _start_health_server(port: int) -> None:
    try:
        server = HTTPServer(("0.0.0.0", port), _HealthHandler)
        logger.info("Health server listening on 0.0.0.0:%s", port)
        server.serve_forever()
    except Exception as e:
        logger.warning("Health server failed: %s", e)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        logger.error(
            "TELEGRAM_BOT_TOKEN is not set. "
            "Set it in Railway Variables or a local .env file."
        )
        raise SystemExit(1)

    logger.info("Starting AI Agent 7h Bot...")
    logger.info(
        "OUTPUT_DIR=%s | ALLOWED_USER_IDS=%s | PORT=%s",
        OUTPUT_DIR,
        ALLOWED_USER_IDS or "ALL",
        PORT,
    )

    # Railway / container health check
    threading.Thread(target=_start_health_server, args=(PORT,), daemon=True).start()

    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .build()
    )

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    logger.info("Bot is running (polling)...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
