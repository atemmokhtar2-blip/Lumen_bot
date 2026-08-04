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



def _chat_route(text: str):
    """Single entry: natural language → capability (chat never writes code)."""
    try:
        from telegram_bot_engine.formal_engine.services.chat_router import route_message
        return route_message(text or "")
    except Exception:
        return None


def _detect_host_intent(text: str) -> str:
    """Return host action via ChatRouter."""
    r = _chat_route(text)
    if r is None or not getattr(r, "ok", False):
        t = (text or "").strip().lower()
        if any(k in t for k in ("استضف", "استضافة", "host")):
            return "start"
        return "none"
    return {
        "host_start": "start",
        "host_stop": "stop",
        "host_status": "status",
        "host_diagnose": "diagnose",
    }.get(r.capability_id, "none")


def _looks_like_bot_token(text: str) -> bool:
    import re
    return bool(re.match(r"^\d{6,12}:[A-Za-z0-9_-]{30,}$", (text or "").strip()))



async def _handle_live_run_token(message, context, token: str, pending: dict) -> None:
    """Real install + run via LiveRunnerService (no fake success)."""
    status = await message.reply_text(
        "🔐 جاري التحقق من التوكن ثم تثبيت التبعيات وتشغيل البوت..."
    )
    project_path = pending.get("project_path")
    entry = pending.get("entry_point") or ""

    def _run():
        from telegram_bot_engine.formal_engine.services.live_runner import run_bot_project
        return run_bot_project(
            project_path=project_path,
            bot_token=token,
            entry_hint=entry or None,
            run_seconds=float(pending.get("run_seconds") or 8),
        )

    try:
        report = await asyncio.to_thread(_run)
    except Exception as e:
        logger.exception("Live run failed")
        await status.edit_text(f"❌ فشل التشغيل الحي: {type(e).__name__}: {str(e)[:200]}")
        context.user_data.pop("pending_run", None)
        return
    finally:
        token = ""  # noqa: F841

    context.user_data.pop("pending_run", None)
    text_out = report.to_user_text()
    if len(text_out) > 3500:
        text_out = text_out[:3500] + "\n…"
    await status.edit_text(text_out)


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
        "✅ المحرك الرسمي (Formal Engine) يعمل — فهم حتمي + توليد كود نظيف."
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
            f"• المحرك النشط: Formal Engine (فهم + توليد)."
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
    pending_host = (context.user_data or {}).get("pending_host")
    if pending_host and _looks_like_bot_token(request):
        context.user_data.pop("pending_host", None)
        status = await message.reply_text("🚀 جاري بدء الاستضافة (عملية طويلة الأمد)...")
        await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.TYPING)

        def _do_host():
            from telegram_bot_engine.formal_engine.services.hosting import get_hosting_service
            svc = get_hosting_service(OUTPUT_DIR)
            return svc.start(
                user_id=message.from_user.id if message.from_user else 0,
                project_path=pending_host.get("project_path") or "",
                bot_token=request,
            )

        try:
            result = await asyncio.to_thread(_do_host)
        except Exception as e:
            logger.exception("hosting start failed")
            await status.edit_text(f"❌ فشل الاستضافة: {type(e).__name__}: {str(e)[:200]}")
            return
        await status.edit_text(result.to_user_text())
        return

    pending_run = (context.user_data or {}).get("pending_run")
    if _looks_like_bot_token(request):
        if not pending_run:
            active = (context.user_data or {}).get("active_repo") or {}
            if active.get("path") and Path(active["path"]).exists():
                entry = ""
                try:
                    cdict = active.get("contract") or {}
                    eps = cdict.get("entry_points") or []
                    if eps:
                        entry = (eps[0] or {}).get("path") or ""
                except Exception:
                    entry = ""
                if not entry:
                    for cand in ("bot.py", "main.py", "app.py"):
                        if (Path(active["path"]) / cand).exists():
                            entry = cand
                            break
                pending_run = {
                    "project_path": active["path"],
                    "entry_point": entry,
                    "run_seconds": 8,
                }
                context.user_data["pending_run"] = pending_run
        if pending_run:
            await _handle_live_run_token(message, context, request, pending_run)
            return

    # Private repo: user sends GitHub PAT after auth failure
    pending_clone = (context.user_data or {}).get("pending_clone_auth")
    if pending_clone:
        from telegram_bot_engine.engines.generators.git_operations.smart_clone import (
            extract_token,
            smart_clone,
        )
        git_tok = extract_token(request)
        if git_tok:
            status = await message.reply_text("🔑 جاري إعادة سحب المستودع بالتوكن...")
            await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.TYPING)
            dest = Path(OUTPUT_DIR) / "clones"
            dest.mkdir(parents=True, exist_ok=True)
            url = pending_clone.get("url") or ""

            def _reclone():
                return smart_clone(
                    text=url,
                    dest_dir=dest,
                    token=git_tok,
                    url_override=url,
                    depth=1,
                )

            try:
                result = await asyncio.to_thread(_reclone)
            except Exception as e:
                logger.exception("private reclone failed")
                await status.edit_text(f"❌ فشل السحب بالتوكن: {type(e).__name__}: {str(e)[:200]}")
                return
            finally:
                git_tok = ""  # noqa: F841

            if not result.ok:
                err_msg = f"❌ {result.message}"
                if result.stderr:
                    err_msg += f"\n`{result.stderr[:250]}`"
                await status.edit_text(err_msg)
                if not result.needs_auth:
                    context.user_data.pop("pending_clone_auth", None)
                return

            context.user_data.pop("pending_clone_auth", None)
            lines = [
                "✅ تم سحب المستودع الخاص بنجاح",
                f"• الرابط: `{result.url or ''}`",
                f"• المسار: `{result.path or ''}`",
            ]
            try:
                await status.edit_text("\n".join(lines + ["", "🔍 جاري فهم المستودع..."]))
                from telegram_bot_engine.formal_engine.services.repo_understanding import understand_repo

                def _do_u():
                    return understand_repo(result.path, remote_url=result.url or "")

                repo_contract = await asyncio.to_thread(_do_u)
                context.user_data["active_repo"] = {
                    "path": result.path,
                    "url": result.url,
                    "contract": repo_contract.model_dump(mode="json"),
                }
                lines.append("")
                lines.append(repo_contract.to_user_summary())
                _tg_fws = ("python-telegram-bot", "aiogram", "pyTelegramBotAPI", "pyrogram")
                _is_runnable = (
                    repo_contract.is_telegram_bot
                    or repo_contract.architecture_style in ("telegram_bot", "generation_engine")
                    or any(f in _tg_fws for f in (repo_contract.frameworks or []))
                    or any(
                        str(d).lower().replace("_", "-").startswith(
                            ("python-telegram-bot", "aiogram", "pytelegrambotapi", "telebot", "pyrogram")
                        )
                        for d in (repo_contract.dependencies or [])
                    )
                )
                if _is_runnable:
                    entry = repo_contract.entry_points[0].path if repo_contract.entry_points else ""
                    context.user_data["pending_run"] = {
                        "project_path": result.path,
                        "entry_point": entry,
                        "run_seconds": 8,
                    }
                    lines.append("")
                    lines.append("🚀 *للتشغيل الحقيقي:* أرسل توكن البوت من @BotFather")
                await status.edit_text("\n".join(lines))
            except Exception as e:
                logger.exception("understand after private clone failed")
                await status.edit_text("\n".join(lines + [f"⚠️ الفهم فشل: {type(e).__name__}"]))
            return

    pending = (context.user_data or {}).get("pending_deploy")
    if pending and _looks_like_bot_token(request):
        await _handle_live_deploy_token(message, context, request, pending)
        return

    # --- Smart Git: clone repo from natural language + URL ---
    try:
        from telegram_bot_engine.engines.generators.git_operations.smart_clone import (
            looks_like_clone_request,
            smart_clone,
            extract_repo_url,
        )
    except Exception:
        looks_like_clone_request = None  # type: ignore

    # ChatRouter: natural "اسحب المستودع..." → clone path only
    try:
        from telegram_bot_engine.formal_engine.services.chat_router import route_message as _route_msg
        _cr = _route_msg(request)
        _clone_via_router = (
            _cr.ok
            and _cr.capability_id == "clone_repo"
            and (bool(_cr.params.get("url")) or "github.com" in request.lower() or "gitlab.com" in request.lower())
        )
    except Exception:
        _clone_via_router = False

    if (looks_like_clone_request and looks_like_clone_request(request)) or _clone_via_router:
        status = await message.reply_text("📥 جاري سحب المستودع...")
        await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.TYPING)
        dest = Path(OUTPUT_DIR) / "clones"
        dest.mkdir(parents=True, exist_ok=True)

        def _do_clone():
            return smart_clone(request, dest_dir=dest)

        try:
            result = await asyncio.to_thread(_do_clone)
        except Exception as e:
            logger.exception("Clone failed")
            await status.edit_text(f"❌ فشل سحب المستودع: {type(e).__name__}: {str(e)[:200]}")
            return

        if result.ok:
            lines = [
                "✅ تم سحب المستودع بنجاح",
                f"• الرابط: `{result.url or ''}`",
                f"• المسار: `{result.path or ''}`",
            ]
            # Auto-understand repository
            repo_contract = None
            if result.path and Path(result.path).exists():
                try:
                    await status.edit_text("\n".join(lines + ["", "🔍 جاري فهم المستودع..."]))
                    from telegram_bot_engine.formal_engine.services.repo_understanding import (
                        understand_repo,
                    )

                    def _do_understand():
                        return understand_repo(result.path, remote_url=result.url or "")

                    repo_contract = await asyncio.to_thread(_do_understand)
                    # Keep context for future development turns
                    context.user_data["active_repo"] = {
                        "path": result.path,
                        "url": result.url,
                        "contract": repo_contract.model_dump(mode="json"),
                    }
                    lines.append("")
                    lines.append(repo_contract.to_user_summary())
                    lines.append("")
                    lines.append(
                        "يمكنك الآن طلب تطوير على هذا المستودع، مثال:\n"
                        "• أضف أمر /stats\n"
                        "• اشرح هيكل المشروع\n"
                        "• قائمة الملفات / ابحث عن X"
                    )
                    _tg_fws = ("python-telegram-bot", "aiogram", "pyTelegramBotAPI", "pyrogram")
                    _is_runnable = (
                        repo_contract.is_telegram_bot
                        or repo_contract.architecture_style in ("telegram_bot", "generation_engine")
                        or any(f in _tg_fws for f in (repo_contract.frameworks or []))
                        or any(
                            str(d).lower().replace("_", "-").startswith(
                                ("python-telegram-bot", "aiogram", "pytelegrambotapi", "telebot", "pyrogram")
                            )
                            for d in (repo_contract.dependencies or [])
                        )
                    )
                    if _is_runnable:
                        entry = ""
                        if repo_contract.entry_points:
                            entry = repo_contract.entry_points[0].path
                        context.user_data["pending_run"] = {
                            "project_path": result.path,
                            "entry_point": entry,
                            "run_seconds": 8,
                        }
                        lines.append("")
                        lines.append(
                            "🚀 *للتشغيل الحقيقي:* أرسل الآن توكن البوت من @BotFather\n"
                            "(تحقق + تثبيت تبعيات + تشغيل — بدون نجاح وهمي)"
                        )
                except Exception as e:
                    logger.exception("Repo understanding failed")
                    lines.append(f"⚠️ السحب نجح لكن الفهم فشل: {type(e).__name__}")

            await status.edit_text("\n".join(lines))
            # zip and send if small enough
            if result.path and Path(result.path).exists():
                try:
                    zip_path = _make_zip_from_path(result.path)
                    if zip_path and zip_path.exists() and zip_path.stat().st_size < 45 * 1024 * 1024:
                        with open(zip_path, "rb") as f:
                            await message.reply_document(
                                document=f,
                                filename=f"{Path(result.path).name}.zip",
                                caption="📦 نسخة من المستودع المسحوب",
                            )
                except Exception:
                    logger.exception("Failed to zip cloned repo")
        else:
            if getattr(result, "needs_auth", False):
                context.user_data["pending_clone_auth"] = {
                    "url": result.url or "",
                }
                await status.edit_text(
                    "🔒 المستودع خاص أو يحتاج صلاحية.\n\n"
                    "أرسل الآن *توكن GitHub* (PAT) بصلاحية `repo`:\n"
                    "• Classic: ghp_...\n"
                    "• Fine-grained: github_pat_...\n\n"
                    "بعدها هُعاد السحب تلقائياً."
                )
            else:
                err = (result.message or "فشل غير معروف")
                if result.stderr:
                    err += f"\n`{result.stderr[:300]}`"
                await status.edit_text(f"❌ {err}")
        return

    # --- Hosting (owner-only foundation; no billing yet) ---
    host_action = _detect_host_intent(request)
    if host_action != "none":
        from telegram_bot_engine.formal_engine.services.hosting import get_hosting_service
        svc = get_hosting_service(OUTPUT_DIR)
        uid = message.from_user.id if message.from_user else 0
        active = (context.user_data or {}).get("active_repo") or {}

        if host_action == "start":
            project_path = active.get("path") or ""
            if not project_path or not Path(project_path).exists():
                await message.reply_text(
                    "ما فيش مشروع نشط للاستضافة.\n"
                    "اسحب مستودع أو ولّد بوت أولاً، بعدين اكتب: استضف"
                )
                return
            context.user_data["pending_host"] = {
                "project_path": project_path,
                "user_id": uid,
            }
            await message.reply_text(
                "🚀 *استضافة المشروع النشط*\n"
                f"• المسار: `{project_path}`\n\n"
                "أرسل الآن توكن البوت من @BotFather لبدء التشغيل الطويل الأمد.\n"
                "(الأساس جاهز — بدون طبقة دفع حالياً)"
            )
            return

        if host_action == "status":
            result = svc.status(user_id=uid)
            await message.reply_text(result.to_user_text())
            return

        if host_action == "stop":
            items = svc.list_for_user(uid)
            running = [i for i in items if i.status == "running"]
            if not running:
                await message.reply_text("ما فيش مثيل استضافة شغال لإيقافه.")
                return
            # stop the most recent running
            target = sorted(running, key=lambda x: x.started_at, reverse=True)[0]
            result = await asyncio.to_thread(
                lambda: svc.stop(instance_id=target.instance_id, user_id=uid)
            )
            await message.reply_text(result.to_user_text())
            return

        if host_action == "diagnose":
            items = svc.list_for_user(uid)
            if not items:
                await message.reply_text("ما فيش مثيلات لتشخيصها.")
                return
            target = sorted(items, key=lambda x: x.started_at, reverse=True)[0]
            result = await asyncio.to_thread(
                lambda: svc.diagnose(user_id=uid, instance_id=target.instance_id)
            )
            await message.reply_text(result.to_user_text())
            return

    # --- Active repo development (must run before generate_bot) ---
    active = (context.user_data or {}).get("active_repo")
    if active and active.get("path") and Path(active["path"]).exists():
        from telegram_bot_engine.formal_engine.services.repo_dev import (
            handle_repo_request,
            detect_repo_intent,
        )
        action, _ = detect_repo_intent(request)
        # ChatRouter knows system capabilities — prefer it for routing only
        _rt = _chat_route(request)
        _cap = getattr(_rt, "capability_id", "") if _rt and getattr(_rt, "ok", False) else ""
        _repo_caps = {
            "static_analysis", "package_health", "upgrade_recommend",
            "upgrade_apply", "repo_develop",
        }
        develop_hints = (
            "أضف", "اضف", "ضيف", "عدل", "عدّل", "اشرح", "الأوامر", "الاوامر",
            "امسح", "أعد", "طور", "طوّر", "هيكل", "command", "add", "explain",
            "stats", "fix", "modify", "ساعد", "تقدر",
            "خطة تطوير", "فجوات", "أين أعد", "تطوير المستودع", "سد فجوات",
        )
        if (
            _cap in _repo_caps
            or action != "unknown"
            or any(h in request.lower() for h in develop_hints)
            or any(h in request for h in develop_hints)
        ):
            status = await message.reply_text("🛠 جاري التنفيذ على المستودع النشط...")
            await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.TYPING)

            # Canonical phrase when ChatRouter recognized capability but wording was soft
            _cap_to_phrase = {
                "static_analysis": "تحليل استاتيكي",
                "package_health": "صحة الحزم",
                "upgrade_recommend": "توصيات الترقية",
                "upgrade_apply": "طبّق الترقيات الآمنة",
                "repo_develop": request,
            }
            _dev_text = request
            if _cap in _cap_to_phrase and action == "unknown":
                _dev_text = _cap_to_phrase[_cap]

            def _run_dev():
                return handle_repo_request(
                    _dev_text,
                    active["path"],
                    contract_dict=active.get("contract"),
                )

            try:
                dev = await asyncio.to_thread(_run_dev)
            except Exception as e:
                logger.exception("RepoDev failed")
                await status.edit_text(f"❌ فشل التنفيذ على المستودع: {type(e).__name__}: {str(e)[:200]}")
                return

            if dev.contract is not None:
                context.user_data["active_repo"] = {
                    "path": active["path"],
                    "url": active.get("url"),
                    "contract": dev.contract.model_dump(mode="json"),
                }

            text_out = dev.message
            if dev.changed_files:
                text_out += "\n• ملفات تغيّرت: " + ", ".join(f"`{f}`" for f in dev.changed_files)
            await status.edit_text(text_out)

            # If file changed, offer zip of repo
            if dev.ok and dev.changed_files and Path(active["path"]).exists():
                try:
                    zip_path = _make_zip_from_path(active["path"])
                    if zip_path and zip_path.exists() and zip_path.stat().st_size < 45 * 1024 * 1024:
                        with open(zip_path, "rb") as f:
                            await message.reply_document(
                                document=f,
                                filename=f"{Path(active['path']).name}_updated.zip",
                                caption="📦 المستودع بعد التعديل",
                            )
                except Exception:
                    logger.exception("zip after repo dev failed")
            return


    # ChatRouter: help / list capabilities (route only)
    _rt_help = _chat_route(request)
    if _rt_help and getattr(_rt_help, "ok", False) and _rt_help.capability_id == "help":
        try:
            from telegram_bot_engine.formal_engine.services.chat_router import get_router
            await message.reply_text(get_router().help_text())
        except Exception:
            await message.reply_text("مساعدة: اسحب مستودع | ولّد بوت | استضافة | تحليل استاتيكي")
        return

    if len(request) < 5:
        await message.reply_text("الوصف قصير جداً. أرسل وصفاً أوضح للبوت المطلوب.")
        return

    status_msg = await message.reply_text(
        "⏳ جاري الفهم الرسمي وتوليد المشروع (Formal Engine)..."
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
        meta = getattr(result, "metadata", None) or {}
        if meta.get("button_count") is not None:
            summary_lines.append(f"• الأزرار في /start: {meta.get('button_count')}")
        if meta.get("buttons"):
            summary_lines.append(f"• نصوص الأزرار: {', '.join(meta.get('buttons') or [])}")
        if meta.get("commands"):
            summary_lines.append(f"• الأوامر: {'/' + ' /'.join(meta.get('commands') or [])}")
        if errors:
            summary_lines.append("• أخطاء:")
            for e in errors[:5]:
                # Dynamic engine errors often contain _, *, ` — escape them
                summary_lines.append(f"  - {_escape_md(e)}")

        summary_lines.append(
            "\n_المحرك: Formal Engine — بدون نماذج لغوية._"
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

            # Structural review report + token request only if gate passed
            ready = bool(success) and bool(meta.get("ready_for_token", success))
            gate = meta.get("static_gate") or {}
            if gate:
                g_lines = [
                    "🔬 مراجعة StaticDevGate",
                    "• النتيجة: " + ("نجاح" if gate.get("ok") else "فشل"),
                    f"• أخطاء: {gate.get('errors', 0)} | تحذيرات: {gate.get('warnings', 0)}",
                ]
                for f in (gate.get("findings") or [])[:8]:
                    if f.get("severity") == "error":
                        g_lines.append(f"  🔴 {f.get('code')}: {str(f.get('msg', ''))[:80]}")
                await message.reply_text("\n".join(g_lines))

            if ready:
                context.user_data["pending_deploy"] = {
                    "project_path": str(project_path),
                    "owner_user_id": user.id if user else None,
                }
                context.user_data["pending_live_run"] = {
                    "project_path": str(project_path),
                    "owner_user_id": user.id if user else None,
                }
                await message.reply_text(
                    "✅ المشروع عدّى الفهم + التوليد + المراجعة الاستاتيكية + py_compile.\n\n"
                    "🔑 أرسل توكن البوت الآن لتجربة حية (من @BotFather).\n"
                    "التوكن لا يُحفظ في الكود أو اللوجات.\n\n"
                    "بعد التشغيل: اضبط الصلاحيات حسب نوع البوت (خاص / مجموعة / قناة)."
                )
            else:
                await message.reply_text(
                    "⚠️ المشروع اتولّد لكن المراجعة الاستاتيكية/الترجمة لم تمر بالكامل.\n"
                    "راجع الأخطاء قبل إرسال التوكن."
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
            "راجع السجلات أو أعد المحاولة. المحرك الرسمي نشط.",
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
