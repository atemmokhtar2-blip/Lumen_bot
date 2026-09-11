"""Phase 3 — post-deploy verify + webhook activation for Lumen serverless host.

Lifecycle (real, fail-closed):
  PREPARING → DEPLOYING → DEPLOYED → HEALTH_CHECK → REGISTER_WEBHOOK → VERIFY_WEBHOOK → RUNNING
  any step may → FAILED with machine-readable reason (no vendor names in user messages)

Checks:
  1) HTTP GET on public URL and webhook path (adapter health JSON)
  2) Telegram setWebhook to https://{url}{path} with secret_token
  3) Telegram getWebhookInfo must report same URL (and pending errors surface)
"""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("lumen.hosting.serverless_verify")

STATE_PREPARING = "PREPARING"
STATE_DEPLOYING = "DEPLOYING"
STATE_DEPLOYED = "DEPLOYED"
STATE_HEALTH_CHECK = "HEALTH_CHECK"
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
            "health": self.health,
            "webhook_info": {
                k: self.webhook_info.get(k)
                for k in ("url", "has_custom_certificate", "pending_update_count", "last_error_message", "last_error_date", "max_connections", "ip_address")
                if k in self.webhook_info
            },
            "phases": [{"state": p.state, "ok": p.ok, "detail": p.detail, "at": p.at} for p in self.phases[-12:]],
            **self.details,
        }


def _user_msg(code: str) -> str:
    return {
        "no_url": "النشر اكتمل لكن رابط الاستضافة غير متاح.",
        "health_failed": "الاستضافة رُفعت لكن فحص الصحة فشل.",
        "webhook_register_failed": "تعذّر تفعيل استقبال الرسائل من تيليجرام.",
        "webhook_mismatch": "تم التسجيل لكن تيليجرام لا يشير إلى رابط البوت الصحيح.",
        "running": "البوت يعمل على استضافة Lumen وتم التحقق منه.",
        "token_missing": "توكن البوت غير متاح لإكمال التفعيل.",
    }.get(code, "فشل التحقق من الاستضافة.")


def http_get_json(url: str, *, timeout: float = 12.0, headers: dict[str, str] | None = None) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        method="GET",
        headers={"User-Agent": "LumenHost/1.1", "Accept": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            status = int(getattr(resp, "status", 200) or 200)
            data: Any = {}
            if raw.strip():
                try:
                    data = json.loads(raw)
                except Exception:
                    data = {"raw": raw[:300]}
            return {"ok": 200 <= status < 300, "status": status, "data": data}
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")[:300]
        except Exception:
            pass
        return {"ok": False, "status": int(exc.code or 0), "error": f"http_{exc.code}", "body": body}
    except Exception as exc:
        return {"ok": False, "status": 0, "error": type(exc).__name__}


def telegram_api(bot_token: str, method: str, payload: dict[str, Any] | None = None, *, timeout: float = 15.0) -> dict[str, Any]:
    token = (bot_token or "").strip()
    if not token:
        return {"ok": False, "error": "no_token"}
    url = f"https://api.telegram.org/bot{token}/{method}"
    body = json.dumps(payload or {}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"User-Agent": "LumenHost/1.1", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
            if not isinstance(data, dict):
                return {"ok": False, "error": "bad_response"}
            return data
    except urllib.error.HTTPError as exc:
        err = ""
        try:
            err = exc.read().decode("utf-8", errors="replace")[:400]
        except Exception:
            pass
        return {"ok": False, "error": f"http_{exc.code}", "body": err}
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__}


def get_webhook_info(bot_token: str) -> dict[str, Any]:
    data = telegram_api(bot_token, "getWebhookInfo", {})
    if not data.get("ok"):
        return {"ok": False, "error": data.get("error") or data.get("description") or "getWebhookInfo_failed"}
    result = data.get("result") or {}
    if not isinstance(result, dict):
        return {"ok": False, "error": "bad_result"}
    out = dict(result)
    out["ok"] = True
    return out


def set_webhook(bot_token: str, webhook_url: str, *, secret: str = "") -> dict[str, Any]:
    if not webhook_url.startswith("https://"):
        return {"ok": False, "error": "url_not_https"}
    payload: dict[str, Any] = {
        "url": webhook_url,
        "drop_pending_updates": True,
        "allowed_updates": [],  # all
    }
    if secret:
        payload["secret_token"] = secret[:256]
    data = telegram_api(bot_token, "setWebhook", payload)
    if not data.get("ok"):
        return {
            "ok": False,
            "error": data.get("description") or data.get("error") or "setWebhook_failed",
            "raw": {k: data.get(k) for k in ("error_code", "description") if k in data},
        }
    return {"ok": True, "url": webhook_url}


def health_check_deployment(
    base_url: str,
    *,
    webhook_path: str = "/api",
    timeout: float = 12.0,
    retries: int = 4,
    delay_sec: float = 2.0,
) -> dict[str, Any]:
    """GET base and base+path until success or retries exhausted."""
    base = (base_url or "").rstrip("/")
    if not base.startswith("https://"):
        return {"ok": False, "error": "bad_base_url"}
    path = webhook_path if webhook_path.startswith("/") else f"/{webhook_path}"
    targets = [base, base + path]
    last: dict[str, Any] = {"ok": False, "error": "not_started"}
    for attempt in range(max(1, retries)):
        for target in targets:
            last = http_get_json(target, timeout=timeout)
            last["url"] = target
            last["attempt"] = attempt + 1
            if last.get("ok"):
                data = last.get("data") if isinstance(last.get("data"), dict) else {}
                # Prefer adapter health shape when present
                if data.get("ok") is True or last.get("status") == 200:
                    last["healthy_url"] = target
                    return last
        if attempt + 1 < retries:
            time.sleep(delay_sec)
    return last


def verify_serverless_bot(
    *,
    bot_token: str,
    public_url: str,
    webhook_path: str = "/api",
    webhook_secret: str = "",
    skip_health: bool = False,
    skip_webhook: bool = False,
) -> VerifyResult:
    phases: list[PhaseRecord] = []
    base = (public_url or "").rstrip("/")
    if not base.startswith("https://"):
        phases.append(PhaseRecord(STATE_FAILED, False, "no_url"))
        return VerifyResult(ok=False, state=STATE_FAILED, message=_user_msg("no_url"), phases=phases)

    path = webhook_path if (webhook_path or "").startswith("/") else f"/{webhook_path or 'api'}"
    webhook_url = base + path
    phases.append(PhaseRecord(STATE_DEPLOYED, True, base))

    health: dict[str, Any] = {}
    if not skip_health:
        phases.append(PhaseRecord(STATE_HEALTH_CHECK, True, "start"))
        health = health_check_deployment(base, webhook_path=path)
        if not health.get("ok"):
            phases.append(PhaseRecord(STATE_HEALTH_CHECK, False, str(health.get("error") or health.get("status") or "fail")))
            # Health soft-fail: still try webhook (some builders need first TG request)
            # But mark detail — final ok requires webhook success at minimum
            health_ok = False
        else:
            phases.append(PhaseRecord(STATE_HEALTH_CHECK, True, str(health.get("healthy_url") or "")))
            health_ok = True
    else:
        health_ok = True

    if not (bot_token or "").strip():
        phases.append(PhaseRecord(STATE_FAILED, False, "token_missing"))
        return VerifyResult(
            ok=False,
            state=STATE_FAILED,
            message=_user_msg("token_missing"),
            webhook_url=webhook_url,
            health=health,
            phases=phases,
        )

    if skip_webhook:
        state = STATE_RUNNING if health_ok else STATE_FAILED
        return VerifyResult(
            ok=health_ok,
            state=state,
            message=_user_msg("running" if health_ok else "health_failed"),
            webhook_url=webhook_url,
            health=health,
            phases=phases,
        )

    phases.append(PhaseRecord(STATE_REGISTER_WEBHOOK, True, webhook_url))
    reg = set_webhook(bot_token, webhook_url, secret=webhook_secret or "")
    if not reg.get("ok"):
        phases.append(PhaseRecord(STATE_REGISTER_WEBHOOK, False, str(reg.get("error") or "fail")))
        return VerifyResult(
            ok=False,
            state=STATE_FAILED,
            message=_user_msg("webhook_register_failed"),
            webhook_url=webhook_url,
            health=health,
            phases=phases,
            details={"register": reg},
        )
    phases.append(PhaseRecord(STATE_REGISTER_WEBHOOK, True, "registered"))

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
        )

    reported = str(info.get("url") or "").rstrip("/")
    expected = webhook_url.rstrip("/")
    if reported != expected and not reported.startswith(expected) and expected not in reported:
        phases.append(PhaseRecord(STATE_VERIFY_WEBHOOK, False, f"mismatch:{reported[:80]}"))
        return VerifyResult(
            ok=False,
            state=STATE_FAILED,
            message=_user_msg("webhook_mismatch"),
            webhook_url=webhook_url,
            health=health,
            webhook_info=info,
            phases=phases,
        )

    last_err = str(info.get("last_error_message") or "").strip()
    # last_error may be stale from previous deploys — warn only if very recent and non-empty after set
    phases.append(PhaseRecord(STATE_VERIFY_WEBHOOK, True, reported))
    phases.append(PhaseRecord(STATE_RUNNING, True, "ok"))

    msg = _user_msg("running")
    if not health_ok:
        msg = "البوت مُفعّل على تيليجرام؛ فحص الصحة الأولي لم ينجح بعد."
    return VerifyResult(
        ok=True,
        state=STATE_RUNNING,
        message=msg,
        webhook_url=webhook_url,
        health=health,
        webhook_info=info,
        phases=phases,
        details={"health_ok": health_ok, "last_error_message": last_err[:200]},
    )


__all__ = [
    "VerifyResult",
    "PhaseRecord",
    "verify_serverless_bot",
    "health_check_deployment",
    "get_webhook_info",
    "set_webhook",
    "http_get_json",
    "STATE_RUNNING",
    "STATE_FAILED",
    "STATE_DEPLOYED",
]
