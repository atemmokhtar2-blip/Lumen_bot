"""Live run and live deployment token handlers."""

from __future__ import annotations

import asyncio

from .config import logger
from .helpers import escape_md, safe_edit_text


async def handle_live_run_token(message, context, token: str, pending: dict) -> None:
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


async def handle_live_deploy_token(message, context, token: str, pending: dict) -> None:
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
        token = ""  # noqa: F841

    context.user_data.pop("pending_deploy", None)

    tv = report.token_validation
    dep = report.deployment
    health = report.health
    lines = [
        f"{'✅' if report.passed else '⚠️'} *تقرير Live Deployment*",
        f"• الحكم: `{escape_md(report.verdict)}`",
        f"• الجودة: {report.quality_score:.0%}",
    ]
    if tv:
        lines.append(
            f"• التوكن: {'صالح' if tv.valid else 'غير صالح'}"
            + (f" (@{escape_md(tv.bot_username)})" if tv.bot_username else "")
        )
    if dep:
        lines.append(
            f"• التشغيل: `{escape_md(dep.status)}`"
            + (" (dry-run)" if dep.dry_run else " — عملية حقيقية")
        )
        if dep.message:
            lines.append(f"  {escape_md(dep.message[:200])}")
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
        lines.append(f"  {mark} {escape_md(t.name)}: {escape_md(t.message[:80])}")
    if report.findings:
        lines.append("• ملاحظات:")
        for f in report.findings[:4]:
            lines.append(f"  - {escape_md(f.message[:120])}")
    if tv and tv.bot_username and dep and dep.status == "running":
        lines.append(
            f"\n🚀 البوت شغال — افتح @{escape_md(tv.bot_username)} وأرسل /start"
        )

    await safe_edit_text(status, "\n".join(lines), use_markdown=True)
