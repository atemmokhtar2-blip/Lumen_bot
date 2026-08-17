"""
LiveRunner — real dependency install + bot process execution + error capture.

Install strategy (robust):
  1) try venv + ensure pip works
  2) if venv/pip broken → pip install --target .tbe_deps (isolated)
  3) surface real pip ERROR lines to the user (no opaque "pip install failed")
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import ast


def _is_transient_telegram_failure(http_code: int | None, body_or_desc: str) -> bool:
    """502/503/504 and Cloudflare/gateway blips are Telegram-side — retry."""
    if http_code in {429, 500, 502, 503, 504}:
        return True
    t = (body_or_desc or "").lower()
    return any(
        x in t
        for x in (
            "bad gateway",
            "gateway timeout",
            "service unavailable",
            "temporarily unavailable",
            "error_code\":502",
            "error_code\":503",
            "error_code\":504",
            "error_code\":429",
        )
    )


def validate_telegram_token(
    token: str,
    timeout: float | None = None,
    *,
    retries: int | None = None,
) -> tuple[bool, dict[str, Any], str]:
    """Call Telegram getMe with bounded retries.

    Important: total wall-clock is capped (~45s by default). A previous
    policy of timeout=30 × retries=5 could burn ~170s before soft-continue,
    which made live-run appear hung and the bot \"not starting\".
    """
    token = (token or "").strip()
    if not re.match(r"^\d{6,12}:[A-Za-z0-9_-]{30,}$", token):
        return False, {}, "شكل التوكن غير صالح"

    if timeout is None:
        try:
            # Per-attempt read timeout (keep modest — 502s return fast)
            timeout = float(os.environ.get("TELEGRAM_API_TIMEOUT", "12") or "12")
        except ValueError:
            timeout = 12.0
    if retries is None:
        try:
            retries = int(os.environ.get("TELEGRAM_API_RETRIES", "3") or "3")
        except ValueError:
            retries = 3
    try:
        budget = float(os.environ.get("TELEGRAM_VALIDATE_BUDGET", "45") or "45")
    except ValueError:
        budget = 45.0

    retries = max(1, min(retries, 5))
    timeout = max(5.0, min(float(timeout), 25.0))
    budget = max(15.0, min(budget, 90.0))

    url = f"https://api.telegram.org/bot{token}/getMe"
    last_err = ""
    transient = False
    transient_hits = 0
    t0 = time.perf_counter()

    for attempt in range(1, retries + 1):
        if (time.perf_counter() - t0) >= budget:
            last_err = last_err or "validate_budget_exhausted"
            break
        # Shrink timeout on later attempts so we stay inside budget
        remaining = max(5.0, budget - (time.perf_counter() - t0))
        attempt_timeout = min(timeout, remaining)
        try:
            req = urllib.request.Request(
                url,
                method="GET",
                headers={
                    "User-Agent": "AI-Agent-7h-LiveRunner/1.0",
                    "Accept": "application/json",
                    "Connection": "close",
                },
            )
            with urllib.request.urlopen(req, timeout=attempt_timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if not data.get("ok"):
                desc = str((data.get("description") or data) if isinstance(data, dict) else data)
                code = data.get("error_code") if isinstance(data, dict) else None
                if _is_transient_telegram_failure(code if isinstance(code, int) else None, desc):
                    transient = True
                    transient_hits += 1
                    last_err = f"Telegram transient: {desc}"
                else:
                    return False, data if isinstance(data, dict) else {}, f"getMe failed: {desc}"
            else:
                return True, data.get("result") or {}, "ok"
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore")[:300]
            if e.code in {401, 403, 404}:
                return False, {}, f"Telegram HTTP {e.code}: {body}"
            if _is_transient_telegram_failure(e.code, body):
                transient = True
                transient_hits += 1
            last_err = f"Telegram HTTP {e.code}: {body}"
        except TimeoutError as e:
            transient = True
            transient_hits += 1
            last_err = f"TimeoutError: {e}"
        except urllib.error.URLError as e:
            transient = True
            transient_hits += 1
            reason = getattr(e, "reason", e)
            last_err = f"URLError: {reason}"
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"

        # Early soft-fail: 2 transient hits is enough — don't burn the budget
        if transient_hits >= 2 and attempt >= 2:
            break

        if attempt < retries and (time.perf_counter() - t0) < budget:
            # Short backoff only (502 is usually instant)
            time.sleep(min(1.0 * float(attempt), 3.0))

    elapsed = time.perf_counter() - t0
    if transient:
        return (
            False,
            {"transient": True, "elapsed_s": round(elapsed, 1)},
            "Telegram API غير مستقر مؤقتًا (502/503/timeout). "
            "شكل التوكن صحيح — المشكلة من Telegram/الشبكة. "
            f"({last_err}; {elapsed:.0f}ث)",
        )
    return (
        False,
        {},
        "فشل الاتصال بـ Telegram بعد عدة محاولات: "
        f"{last_err}. تحقق من اتصال السيرفر بـ api.telegram.org "
        f"(timeout={timeout:.0f}ث, budget={budget:.0f}ث).",
    )


def _delete_telegram_webhook(token: str, timeout: float | None = None) -> tuple[bool, str]:
    """Clear webhook so polling can start (fixes Conflict with getUpdates)."""
    token = (token or "").strip()
    if not token:
        return False, "empty_token"
    if timeout is None:
        try:
            timeout = float(os.environ.get("TELEGRAM_API_TIMEOUT", "12") or "12")
        except ValueError:
            timeout = 12.0
    timeout = max(5.0, min(float(timeout), 25.0))
    url = f"https://api.telegram.org/bot{token}/deleteWebhook?drop_pending_updates=true"
    last_err = ""
    t0 = time.perf_counter()
    for attempt in range(1, 3):
        if (time.perf_counter() - t0) > 20.0:
            break
        try:
            req = urllib.request.Request(
                url,
                method="GET",
                headers={"User-Agent": "AI-Agent-7h-LiveRunner/1.0"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if data.get("ok"):
                return True, "webhook_deleted"
            return False, str(data)[:200]
        except Exception as e:
            last_err = f"{type(e).__name__}:{e}"
            if attempt < 2:
                time.sleep(1.0)
    return False, last_err


