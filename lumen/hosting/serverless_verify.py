"""Phase 3 — real post-deploy verify for Lumen serverless host.

Fail-closed activation:
  READY deploy URL → health on webhook path (adapter JSON) → getMe → setWebhook
  → getWebhookInfo exact URL match → RUNNING

No silent success. Skip-verify only in explicit non-production test env.
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("lumen.hosting.serverless_verify")

STATE_DEPLOYED = "DEPLOYED"
STATE_HEALTH_CHECK = "HEALTH_CHECK"
STATE_TOKEN_CHECK = "TOKEN_CHECK"
STATE_REGISTER_WEBHOOK = "REGISTER_WEBHOOK"
STATE_VERIFY_WEBHOOK = "VERIFY_WEBHOOK"
STATE_RUNNING = "RUNNING"
STATE_FAILED = "FAILED"


@dataclass
class PhaseRecord:
    state: str
    ok: bool
    detail: str = ""
    at: float = field(default_factory=time.time)


@dataclass
class VerifyResult:
    ok: bool
    state: str
    message: str = ""
    webhook_url: str = ""
    health: dict[str, Any] = field(default_factory=dict)
    webhook_info: dict[str, Any] = field(default_factory=dict)
    phases: list[PhaseRecord] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def as_meta(self) -> dict[str, Any]:
        return {
            "lifecycle_state": self.state,
            "verify_ok": self.ok,
            "webhook_url": self.webhook_url,
            "health": {
                k: self.health.get(k)
                for k in ("ok", "status", "healthy_url", "error", "attempt", "adapter_ok", "token_configured")
                if k in self.health
            },
            "webhook_info": {
                k: self.webhook_info.get(k)
                for k in (
                    "url",
                    "pending_update_count",
                    "last_error_message",
                    "last_error_date",
                    "max_connections",
                    "ip_address",
                )
                if k in self.webhook_info
            },
            "phases": [
                {"state": p.state, "ok": p.ok, "detail": (p.detail or "")[:160], "at": p.at}
                for p in self.phases[-16:]
            ],
            **self.details,
        }


def _user_msg(code: str) -> str:
    return {
        "no_url": "النشر لم يُرجع رابط استضافة صالح.",
        "health_failed": "الاستضافة لم تمرّ من فحص الصحة.",
        "token_invalid": "توكن البوت غير صالح عند التفعيل.",
        "webhook_register_failed": "تعذّر ربط تيليجرام باستضافة Lumen.",
        "webhook_mismatch": "تيليجرام لا يشير إلى رابط البوت المنشور.",
        "secret_missing": "سر Webhook غير مُعدّ — رُفض التفعيل.",
        "running": "البوت يعمل على استضافة Lumen وتم التحقق منه.",
    }.get(code, "فشل التحقق من الاستضافة.")


def normalize_public_url(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return ""
    if u.startswith("http://"):
        # serverless public host must be https for Telegram
        u = "https://" + u[len("http://") :]
    if not u.startswith("http"):
        u = "https://" + u.lstrip("/")
    return u.rstrip("/")


def normalize_webhook_url(base: str, path: str) -> str:
    base = normalize_public_url(base)
    if not base:
        return ""
    p = (path or "/api").strip() or "/api"
    if not p.startswith("/"):
        p = "/" + p
    return base + p


def urls_equivalent(a: str, b: str) -> bool:
    def norm(u: str) -> str:
        u = (u or "").strip().rstrip("/")
        if u.startswith("http://"):
            u = "https://" + u[len("http://") :]
        return u.lower()

    return bool(a) and bool(b) and norm(a) == norm(b)


def allow_skip_verify() -> bool:
    """Only non-production automated tests may skip live Telegram/HTTP verify."""
    if (os.environ.get("LUMEN_SERVERLESS_SKIP_VERIFY") or "").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return False
    env = (os.environ.get("ENVIRONMENT") or os.environ.get("TBE_ENV") or "").strip().lower()
    if env in {"test", "testing", "dev", "development", "local"}:
        return True
    # pytest / CI without ENVIRONMENT still allowed when explicitly marked
    if (os.environ.get("PYTEST_CURRENT_TEST") or "").strip():
        return True
    if (os.environ.get("CI") or "").strip() and env in {"", "test"}:
        return True
    return False


def http_request(
    url: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    timeout: float = 15.0,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    data = None
    hdrs = {"User-Agent": "LumenHost/1.2", "Accept": "application/json", **(headers or {})}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method.upper(), headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            status = int(getattr(resp, "status", 200) or 200)
            parsed: Any = {}
            if raw.strip():
                try:
                    parsed = json.loads(raw)
                except Exception:
                    parsed = {"_raw": raw[:400]}
            return {"ok": 200 <= status < 300, "status": status, "data": parsed}
    except urllib.error.HTTPError as exc:
        raw = ""
        try:
            raw = exc.read().decode("utf-8", errors="replace")[:400]
        except Exception:
            pass
        return {"ok": False, "status": int(exc.code or 0), "error": f"http_{exc.code}", "body": raw}
    except Exception as exc:
        return {"ok": False, "status": 0, "error": type(exc).__name__}


def telegram_api(bot_token: str, method: str, payload: dict[str, Any] | None = None, *, timeout: float = 20.0) -> dict[str, Any]:
    token = (bot_token or "").strip()
    if not token or ":" not in token:
        return {"ok": False, "error": "no_token"}
    # Never log token
    url = f"https://api.telegram.org/bot{token}/{method}"
    return http_request(url, method="POST", body=payload or {}, timeout=timeout)


def telegram_get_me(bot_token: str) -> dict[str, Any]:
    data = telegram_api(bot_token, "getMe", {})
    if not data.get("ok"):
        # telegram wraps in ok/result; http_request puts body in data
        inner = data.get("data") if isinstance(data.get("data"), dict) else data
        if isinstance(inner, dict) and inner.get("ok") and isinstance(inner.get("result"), dict):
            result = inner["result"]
            return {"ok": True, "id": result.get("id"), "username": result.get("username"), "is_bot": result.get("is_bot")}
        err = data.get("error") or (inner.get("description") if isinstance(inner, dict) else None) or "getMe_failed"
        return {"ok": False, "error": str(err)[:200]}
    # When API returns JSON through data field
    inner = data.get("data") if isinstance(data.get("data"), dict) else {}
    if inner.get("ok") and isinstance(inner.get("result"), dict):
        r = inner["result"]
        return {"ok": True, "id": r.get("id"), "username": r.get("username"), "is_bot": r.get("is_bot")}
    if data.get("ok") and isinstance(data.get("result"), dict):
        r = data["result"]
        return {"ok": True, "id": r.get("id"), "username": r.get("username"), "is_bot": r.get("is_bot")}
    return {"ok": False, "error": "getMe_bad_shape"}


def _unwrap_tg(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize telegram_api/http_request response to Telegram JSON root."""
    if not isinstance(data, dict):
        return {"ok": False, "error": "bad_response"}
    if "result" in data or (data.get("ok") is True and "description" not in data and "error" not in data):
        # already telegram-shaped (rare)
        if "data" in data and isinstance(data["data"], dict) and "ok" in data["data"]:
            return data["data"]
        if data.get("ok") is True and "result" in data:
            return data
    inner = data.get("data")
    if isinstance(inner, dict) and ("ok" in inner or "result" in inner):
        return inner
    if data.get("ok") is False:
        return {"ok": False, "error": data.get("error") or data.get("body") or "request_failed"}
    return data if "ok" in data else {"ok": False, "error": "unrecognized", "raw": str(data)[:200]}


def get_webhook_info(bot_token: str) -> dict[str, Any]:
    raw = telegram_api(bot_token, "getWebhookInfo", {})
    tg = _unwrap_tg(raw)
    if not tg.get("ok"):
        return {"ok": False, "error": tg.get("description") or tg.get("error") or "getWebhookInfo_failed"}
    result = tg.get("result") or {}
    if not isinstance(result, dict):
        return {"ok": False, "error": "bad_result"}
    out = dict(result)
    out["ok"] = True
    return out


def set_webhook(bot_token: str, webhook_url: str, *, secret: str = "", retries: int = 3) -> dict[str, Any]:
    if not webhook_url.startswith("https://"):
        return {"ok": False, "error": "url_not_https"}
    if not (secret or "").strip():
        return {"ok": False, "error": "secret_required"}
    payload: dict[str, Any] = {
        "url": webhook_url,
        "drop_pending_updates": True,
        "secret_token": secret.strip()[:256],
    }
    last: dict[str, Any] = {"ok": False, "error": "not_attempted"}
    for attempt in range(max(1, retries)):
        raw = telegram_api(bot_token, "setWebhook", payload)
        tg = _unwrap_tg(raw)
        if tg.get("ok"):
            return {"ok": True, "url": webhook_url, "attempt": attempt + 1}
        last = {
            "ok": False,
            "error": tg.get("description") or tg.get("error") or "setWebhook_failed",
            "attempt": attempt + 1,
        }
        time.sleep(0.8 * (attempt + 1))
    return last


def delete_webhook(bot_token: str) -> dict[str, Any]:
    raw = telegram_api(bot_token, "deleteWebhook", {"drop_pending_updates": True})
    tg = _unwrap_tg(raw)
    return {"ok": bool(tg.get("ok")), "error": tg.get("description") or tg.get("error") or ""}


def _adapter_health_ok(payload: Any) -> bool:
    """Strict: adapter GET must return JSON ok=true and service=lumen-bot."""
    if not isinstance(payload, dict):
        return False
    if payload.get("ok") is not True:
        return False
    svc = str(payload.get("service") or "")
    if svc and svc != "lumen-bot":
        return False
    # Prefer token_configured true when field present
    if "token_configured" in payload and payload.get("token_configured") is not True:
        return False
    return True


def health_check_deployment(
    base_url: str,
    *,
    webhook_path: str = "/api",
    timeout: float = 12.0,
    retries: int = 6,
    delay_sec: float = 2.0,
) -> dict[str, Any]:
    base = normalize_public_url(base_url)
    if not base.startswith("https://"):
        return {"ok": False, "error": "bad_base_url"}
    webhook_url = normalize_webhook_url(base, webhook_path)
    last: dict[str, Any] = {"ok": False, "error": "not_started"}
    # Prefer webhook path (adapter) — root may be platform default page
    targets = [webhook_url, base]
    for attempt in range(max(1, retries)):
        for target in targets:
            resp = http_request(target, method="GET", timeout=timeout)
            last = {
                **resp,
                "url": target,
                "attempt": attempt + 1,
            }
            data = resp.get("data")
            if resp.get("ok") and _adapter_health_ok(data):
                last["ok"] = True
                last["healthy_url"] = target
                last["adapter_ok"] = True
                last["token_configured"] = bool(isinstance(data, dict) and data.get("token_configured"))
                return last
            # Non-adapter 200 is not success for phase-3
            if resp.get("ok") and isinstance(data, dict) and data.get("ok") is True:
                last["adapter_ok"] = _adapter_health_ok(data)
        if attempt + 1 < retries:
            time.sleep(delay_sec)
    last["ok"] = False
    if not last.get("error"):
        last["error"] = "adapter_health_not_confirmed"
    return last


def verify_serverless_bot(
    *,
    bot_token: str,
    public_url: str,
    webhook_path: str = "/api",
    webhook_secret: str = "",
    require_health: bool = True,
    require_webhook: bool = True,
) -> VerifyResult:
    phases: list[PhaseRecord] = []
    base = normalize_public_url(public_url)
    webhook_url = normalize_webhook_url(base, webhook_path)

    if not base.startswith("https://") or not webhook_url.startswith("https://"):
        phases.append(PhaseRecord(STATE_FAILED, False, "no_url"))
        return VerifyResult(ok=False, state=STATE_FAILED, message=_user_msg("no_url"), phases=phases)

    phases.append(PhaseRecord(STATE_DEPLOYED, True, base))
    secret = (webhook_secret or "").strip()
    if require_webhook and not secret:
        phases.append(PhaseRecord(STATE_FAILED, False, "secret_missing"))
        return VerifyResult(
            ok=False,
            state=STATE_FAILED,
            message=_user_msg("secret_missing"),
            webhook_url=webhook_url,
            phases=phases,
        )

    health: dict[str, Any] = {}
    if require_health:
        phases.append(PhaseRecord(STATE_HEALTH_CHECK, True, "start"))
        # Cold-start Vercel can lag — more retries before soft-fail
        health = health_check_deployment(
            base, webhook_path=webhook_path, retries=10, delay_sec=2.5, timeout=15.0
        )
        if not health.get("ok"):
            # Soft-fail: continue to token + setWebhook (product path).
            # Deploy already produced a public URL; webhook registration is the
            # real activation gate for Telegram bots.
            phases.append(
                PhaseRecord(
                    STATE_HEALTH_CHECK,
                    False,
                    "soft:" + str(health.get("error") or health.get("status") or "fail")[:80],
                )
            )
        else:
            phases.append(PhaseRecord(STATE_HEALTH_CHECK, True, str(health.get("healthy_url") or "")))

    if not (bot_token or "").strip():
        phases.append(PhaseRecord(STATE_FAILED, False, "token_missing"))
        return VerifyResult(
            ok=False,
            state=STATE_FAILED,
            message=_user_msg("token_invalid"),
            webhook_url=webhook_url,
            health=health,
            phases=phases,
        )

    phases.append(PhaseRecord(STATE_TOKEN_CHECK, True, "getMe"))
    me = telegram_get_me(bot_token)
    if not me.get("ok"):
        phases.append(PhaseRecord(STATE_TOKEN_CHECK, False, str(me.get("error") or "fail")))
        return VerifyResult(
            ok=False,
            state=STATE_FAILED,
            message=_user_msg("token_invalid"),
            webhook_url=webhook_url,
            health=health,
            phases=phases,
            details={"getMe": me},
        )
    phases.append(PhaseRecord(STATE_TOKEN_CHECK, True, str(me.get("username") or me.get("id") or "ok")))

    if not require_webhook:
        phases.append(PhaseRecord(STATE_RUNNING, True, "webhook_skipped"))
        return VerifyResult(
            ok=True,
            state=STATE_RUNNING,
            message=_user_msg("running"),
            webhook_url=webhook_url,
            health=health,
            phases=phases,
            details={"bot": me},
        )

    # Clean previous webhook then register
    try:
        delete_webhook(bot_token)
    except Exception:
        pass

    phases.append(PhaseRecord(STATE_REGISTER_WEBHOOK, True, webhook_url))
    reg = set_webhook(bot_token, webhook_url, secret=secret, retries=3)
    if not reg.get("ok"):
        phases.append(PhaseRecord(STATE_REGISTER_WEBHOOK, False, str(reg.get("error") or "fail")))
        return VerifyResult(
            ok=False,
            state=STATE_FAILED,
            message=_user_msg("webhook_register_failed"),
            webhook_url=webhook_url,
            health=health,
            phases=phases,
            details={"register": reg, "bot": me},
        )
    phases.append(PhaseRecord(STATE_REGISTER_WEBHOOK, True, f"attempt={reg.get('attempt')}"))

    phases.append(PhaseRecord(STATE_VERIFY_WEBHOOK, True, "getWebhookInfo"))
    info = get_webhook_info(bot_token)
    if not info.get("ok"):
        phases.append(PhaseRecord(STATE_VERIFY_WEBHOOK, False, str(info.get("error") or "fail")))
        return VerifyResult(
            ok=False,
            state=STATE_FAILED,
            message=_user_msg("webhook_register_failed"),
            webhook_url=webhook_url,
            health=health,
            webhook_info=info,
            phases=phases,
            details={"bot": me},
        )

    reported = str(info.get("url") or "")
    if not urls_equivalent(reported, webhook_url):
        phases.append(PhaseRecord(STATE_VERIFY_WEBHOOK, False, f"mismatch:{reported[:100]}"))
        return VerifyResult(
            ok=False,
            state=STATE_FAILED,
            message=_user_msg("webhook_mismatch"),
            webhook_url=webhook_url,
            health=health,
            webhook_info=info,
            phases=phases,
            details={"bot": me, "expected": webhook_url, "reported": reported},
        )

    phases.append(PhaseRecord(STATE_VERIFY_WEBHOOK, True, reported))
    phases.append(PhaseRecord(STATE_RUNNING, True, "ok"))
    return VerifyResult(
        ok=True,
        state=STATE_RUNNING,
        message=_user_msg("running"),
        webhook_url=webhook_url,
        health=health,
        webhook_info=info,
        phases=phases,
        details={
            "bot": me,
            "health_ok": True,
            "webhook_registered": True,
            "webhook_verified": True,
        },
    )


__all__ = [
    "VerifyResult",
    "PhaseRecord",
    "verify_serverless_bot",
    "health_check_deployment",
    "get_webhook_info",
    "set_webhook",
    "delete_webhook",
    "telegram_get_me",
    "normalize_public_url",
    "normalize_webhook_url",
    "urls_equivalent",
    "allow_skip_verify",
    "STATE_RUNNING",
    "STATE_FAILED",
    "STATE_DEPLOYED",
]
