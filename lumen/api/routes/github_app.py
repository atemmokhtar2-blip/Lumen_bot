"""GitHub App install/setup callback — binds installation_id to Telegram user.

Configure the GitHub App "Setup URL" to:

  {PUBLIC_BASE_URL}/v1/integrations/github/app/setup

GitHub redirects here after install/update with:
  installation_id, setup_action, state (HMAC-signed, single-use)
"""
from __future__ import annotations

import html
import logging
import os
import time

from aiohttp import web

logger = logging.getLogger("api.github_app")

# Simple per-IP setup rate limit (in-process; Redis preferred via platform limiter when available)
_setup_hits: dict[str, list[float]] = {}


def _public_base() -> str:
    from lumen.platform.runtime_config import public_base_url
    return public_base_url()


def _client_ip(request: web.Request) -> str:
    forwarded = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
    if forwarded:
        return forwarded
    peer = request.remote
    return str(peer or "unknown")


def _rate_limit_setup(ip: str, *, limit: int = 30, window: float = 60.0) -> bool:
    now = time.time()
    bucket = _setup_hits.setdefault(ip, [])
    _setup_hits[ip] = [t for t in bucket if now - t < window]
    if len(_setup_hits[ip]) >= limit:
        return False
    _setup_hits[ip].append(now)
    return True


def _html_page(title: str, body: str, *, ok: bool = True, redirect_url: str = "") -> web.Response:
    color = "#0a7" if ok else "#c33"
    meta = ""
    if redirect_url and ok:
        meta = f'<meta http-equiv="refresh" content="3;url={html.escape(redirect_url, quote=True)}"/>'
    doc = f"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  {meta}
  <title>{html.escape(title)}</title>
  <style>
    body{{font-family:system-ui,sans-serif;background:#0b1020;color:#e8eefc;
      display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0}}
    .card{{max-width:440px;padding:1.75rem;border-radius:16px;background:#141a2e;
      border:1px solid #243056;box-shadow:0 12px 40px rgba(0,0,0,.35)}}
    h1{{margin:0 0 .75rem;font-size:1.25rem;color:{color}}}
    p{{margin:.4rem 0;line-height:1.55;color:#b7c3e0;font-size:.95rem}}
    a.btn{{display:inline-block;margin-top:1rem;padding:.7rem 1.1rem;border-radius:10px;
      background:#2b6cff;color:#fff;text-decoration:none;font-weight:600}}
    code{{background:#0b1020;padding:.15rem .35rem;border-radius:6px;font-size:.85rem}}
  </style>
</head>
<body><div class="card"><h1>{html.escape(title)}</h1>{body}</div></body>
</html>"""
    return web.Response(text=doc, content_type="text/html", charset="utf-8")


async def github_app_setup(request: web.Request) -> web.Response:
    """GET /v1/integrations/github/app/setup — post-install redirect from GitHub."""
    ip = _client_ip(request)
    if not _rate_limit_setup(ip):
        return _html_page(
            "محاولات كثيرة",
            "<p>أبطئ قليلاً ثم أعد المحاولة من تيليجرام.</p>",
            ok=False,
        )

    qs = request.rel_url.query
    installation_id = (qs.get("installation_id") or "").strip()
    setup_action = (qs.get("setup_action") or qs.get("action") or "").strip().lower()
    state = (qs.get("state") or "").strip()

    if setup_action in {"request"} and not installation_id:
        return _html_page(
            "بانتظار الموافقة",
            "<p>طُلب تثبيت على مؤسسة — بعد موافقة المسؤول أعد «اتصل بـ GitHub» من البوت.</p>",
            ok=False,
        )

    if not installation_id:
        logger.warning("github_app setup missing installation_id ip=%s", ip)
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
            bind_installation_to_user,
            telegram_return_url,
            verify_install_state,
        )

        payload = verify_install_state(state, consume=True)
        uid = int(payload["uid"])
    except ValueError as exc:
        logger.warning("github_app setup bad state: %s ip=%s", exc, ip)
        return _html_page(
            "انتهت صلاحية الرابط أو اُستخدم مسبقاً",
            "<p>افتح «اتصل بـ GitHub» من البوت مرة أخرى لتحصل على رابط جديد.</p>",
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

    if ok:
        try:
            bind_installation_to_user(installation_id, uid)
        except Exception:
            logger.debug("bind installation index soft-fail", exc_info=True)
        try:
            from lumen.platform.security_events import emit

            emit(
                "github_app.connected",
                severity="info",
                detail={
                    "uid": uid,
                    "installation_id": str(installation_id),
                    "login": login,
                    "setup_action": setup_action,
                },
            )
        except Exception:
            pass

    if not ok:
        return _html_page(
            "فشل حفظ الاتصال",
            "<p>تم التثبيت على GitHub لكن تعذر حفظه في Lumen. أعد المحاولة.</p>",
            ok=False,
        )

    logger.info(
        "github_app linked uid=%s install=%s login=%s action=%s",
        uid,
        installation_id,
        login or "—",
        setup_action or "—",
    )

    return_url = telegram_return_url(start_payload="gh_connected")
    who = f"@{html.escape(login)}" if login else "حسابك"
    btn = ""
    if return_url:
        btn = f'<p><a class="btn" href="{html.escape(return_url, quote=True)}">العودة إلى تيليجرام</a></p>'
    body = (
        f"<p>تم ربط <strong>{who}</strong> بنجاح مع Lumen عبر GitHub App.</p>"
        f"<p>رقم التثبيت: <code>{html.escape(str(installation_id))}</code></p>"
        + (f"<p>المستودعات: <code>{html.escape(repo_selection or '—')}</code></p>" if repo_selection else "")
        + btn
        + ("<p>سيتم تحويلك تلقائياً خلال ثوانٍ…</p>" if return_url else
           "<p>ارجع إلى البوت وافتح شاشة الاتصالات / GitHub.</p>")
    )
    return _html_page("تم ربط GitHub", body, ok=True, redirect_url=return_url)


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
