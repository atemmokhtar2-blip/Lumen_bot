"""GitHub App install/setup callback — binds installation_id to Telegram user.

Configure the GitHub App "Setup URL" (and optionally Callback URL) to:

  {PUBLIC_BASE_URL}/v1/integrations/github/app/setup

GitHub redirects here after install with:
  installation_id, setup_action, state (our signed telegram uid binding)
"""
from __future__ import annotations

import html
import logging
import os

from aiohttp import web

logger = logging.getLogger("api.github_app")


def _public_base() -> str:
    return (
        (os.getenv("PUBLIC_BASE_URL") or os.getenv("API_PUBLIC_URL") or "").strip().rstrip("/")
    )


def _html_page(title: str, body: str, *, ok: bool = True) -> web.Response:
    color = "#0a7" if ok else "#c33"
    doc = f"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>{html.escape(title)}</title>
  <style>
    body{{font-family:system-ui,sans-serif;background:#0b1020;color:#e8eefc;
      display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0}}
    .card{{max-width:420px;padding:1.75rem;border-radius:16px;background:#141a2e;
      border:1px solid #243056;box-shadow:0 12px 40px rgba(0,0,0,.35)}}
    h1{{margin:0 0 .75rem;font-size:1.25rem;color:{color}}}
    p{{margin:.4rem 0;line-height:1.55;color:#b7c3e0;font-size:.95rem}}
    .ok{{color:#8dffc1}}
  </style>
</head>
<body><div class="card"><h1>{html.escape(title)}</h1>{body}</div></body>
</html>"""
    return web.Response(text=doc, content_type="text/html", charset="utf-8")


async def github_app_setup(request: web.Request) -> web.Response:
    """GET /v1/integrations/github/app/setup — post-install redirect from GitHub."""
    qs = request.rel_url.query
    installation_id = (qs.get("installation_id") or "").strip()
    setup_action = (qs.get("setup_action") or qs.get("action") or "").strip().lower()
    state = (qs.get("state") or "").strip()

    if not installation_id:
        logger.warning("github_app setup missing installation_id")
        return _html_page(
            "تعذر إكمال الربط",
            "<p>لم يصل رقم التثبيت من GitHub. أعد المحاولة من تيليجرام.</p>",
            ok=False,
        )

    if not state:
        logger.warning("github_app setup missing state install=%s", installation_id)
        return _html_page(
            "تعذر إكمال الربط",
            "<p>رابط غير مكتمل (state). افتح «اتصل بـ GitHub» من جديد داخل البوت.</p>",
            ok=False,
        )

    try:
        from lumen.engine.services.integrations.github.app_oauth_state import (
            verify_install_state,
        )

        payload = verify_install_state(state)
        uid = int(payload["uid"])
    except ValueError as exc:
        logger.warning("github_app setup bad state: %s", exc)
        return _html_page(
            "انتهت صلاحية الرابط",
            f"<p>أعد الاتصال من تيليجرام. ({html.escape(str(exc))})</p>",
            ok=False,
        )
    except Exception:
        logger.exception("github_app setup state verify failed")
        return _html_page(
            "خطأ في التحقق",
            "<p>تعذر التحقق من الجلسة. حاول مرة أخرى من البوت.</p>",
            ok=False,
        )

    login = ""
    account_type = ""
    repo_selection = ""
    try:
        from lumen.engine.services.integrations.github.app_auth import get_installation

        inst = get_installation(installation_id)
        account = inst.get("account") or {}
        login = str(account.get("login") or "").strip()
        account_type = str(account.get("type") or "").strip()
        repo_selection = str(inst.get("repository_selection") or "").strip()
    except Exception:
        logger.exception(
            "github_app setup get_installation failed install=%s uid=%s",
            installation_id,
            uid,
        )
        # Still bind installation_id — profile can enrich later

    try:
        from lumen.bot.ui.github_connection_store import write_github_app_connection

        ok = write_github_app_connection(
            uid,
            installation_id,
            login=login,
            account_login=login,
            account_type=account_type,
            repo_selection=repo_selection,
        )
    except Exception:
        logger.exception("github_app setup persist failed uid=%s", uid)
        ok = False

    if not ok:
        return _html_page(
            "فشل حفظ الاتصال",
            "<p>تم التثبيت على GitHub لكن تعذر حفظه في Lumen. أعد المحاولة أو راجع الإعدادات.</p>",
            ok=False,
        )

    logger.info(
        "github_app linked uid=%s install=%s login=%s action=%s",
        uid,
        installation_id,
        login or "—",
        setup_action or "—",
    )

    bot_hint = (os.getenv("TELEGRAM_BOT_USERNAME") or os.getenv("BOT_USERNAME") or "").strip().lstrip("@")
    back = ""
    if bot_hint:
        back = (
            f'<p class="ok">ارجع إلى '
            f'<a href="https://t.me/{html.escape(bot_hint)}" style="color:#8cf">@{html.escape(bot_hint)}</a>'
            f' وافتح شاشة الاتصالات.</p>'
        )
    else:
        back = '<p class="ok">ارجع إلى تيليجرام وافتح شاشة GitHub في Lumen.</p>'

    who = f"@{html.escape(login)}" if login else "حسابك"
    return _html_page(
        "تم ربط GitHub",
        f"<p>تم ربط {who} بنجاح مع Lumen.</p>"
        f"<p>التثبيت: <code>{html.escape(str(installation_id))}</code></p>"
        f"{back}",
        ok=True,
    )


async def github_app_status(request: web.Request) -> web.Response:
    """GET /v1/integrations/github/app/status — ops check (no secrets)."""
    from lumen.engine.services.integrations.github.app_auth import github_app_configured

    return web.json_response(
        {
            "ok": True,
            "configured": github_app_configured(),
            "setup_path": "/v1/integrations/github/app/setup",
            "public_base_configured": bool(_public_base()),
        }
    )


__all__ = ["github_app_setup", "github_app_status"]
