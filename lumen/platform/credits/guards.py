"""Central cost & generation guards — single place for pre-flight checks.

All LLM/generation entry points must call assert_generation_allowed /
assert_llm_metering_context before spending provider money.
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


class GenerationBlockedError(RuntimeError):
    """Raised when generation must not start (balance/lifecycle)."""

    def __init__(self, reason: str = "blocked", *, tenant_id: str = ""):
        self.reason = str(reason or "blocked")
        self.tenant_id = str(tenant_id or "")
        super().__init__(f"generation_blocked:{self.reason}")


def resolve_tenant_id(*, tenant_id: str = "", user_id: int | str = 0) -> str:
    tid = str(tenant_id or "").strip()
    if tid:
        return tid
    try:
        from lumen.platform.credits.llm_live import tenant_id_from_user
        return tenant_id_from_user(user_id)
    except Exception:
        try:
            uid = int(user_id or 0)
        except (TypeError, ValueError):
            uid = 0
        return f"tg:{uid}" if uid else ""


def require_tenant_for_llm() -> bool:
    """Default ON: refuse unmetered LLM when no tenant can be bound."""
    return (os.getenv("LUMEN_LLM_REQUIRE_TENANT") or "1").strip().lower() not in {
        "0", "false", "no", "off",
    }


def assert_generation_allowed(
    *,
    tenant_id: str = "",
    user_id: int | str = 0,
) -> str:
    """Pre-flight: balance lifecycle must allow generation. Returns tenant_id.

    Raises GenerationBlockedError when blocked.
    """
    tid = resolve_tenant_id(tenant_id=tenant_id, user_id=user_id)
    if not tid:
        if require_tenant_for_llm():
            raise GenerationBlockedError("no_tenant", tenant_id="")
        return ""
    try:
        from lumen.platform.balance_lifecycle import get_balance_lifecycle

        ok, reason = get_balance_lifecycle().is_generation_allowed(tid)
        if not ok:
            raise GenerationBlockedError(reason or "insufficient_credits", tenant_id=tid)
    except GenerationBlockedError:
        raise
    except Exception as exc:
        # Fail closed when lifecycle cannot be evaluated
        if (os.getenv("LUMEN_GENERATION_GATE_FAIL_CLOSED") or "1").strip().lower() not in {
            "0", "false", "no", "off",
        }:
            logger.error("generation gate unavailable: %s", type(exc).__name__)
            raise GenerationBlockedError("gate_unavailable", tenant_id=tid) from exc
        logger.debug("generation gate soft-skip: %s", type(exc).__name__)
    return tid


def assert_hosting_allowed(
    *,
    tenant_id: str = "",
    user_id: int | str = 0,
) -> str:
    """Pre-flight for start host."""
    tid = resolve_tenant_id(tenant_id=tenant_id, user_id=user_id)
    if not tid:
        if require_tenant_for_llm():
            raise GenerationBlockedError("no_tenant", tenant_id="")
        return ""
    try:
        from lumen.platform.balance_lifecycle import get_balance_lifecycle

        ok, reason = get_balance_lifecycle().is_hosting_allowed(tid)
        if not ok:
            raise GenerationBlockedError(reason or "hosting_blocked", tenant_id=tid)
    except GenerationBlockedError:
        raise
    except Exception as exc:
        if (os.getenv("LUMEN_HOSTING_GATE_FAIL_CLOSED") or "1").strip().lower() not in {
            "0", "false", "no", "off",
        }:
            raise GenerationBlockedError("hosting_gate_unavailable", tenant_id=tid) from exc
    return tid


def assert_llm_spend_allowed(
    *,
    tenant_id: str = "",
    user_id: int | str = 0,
    credit_service: Any = None,
) -> str:
    """Combined: generation allowed + optional daily cap remaining > 0."""
    tid = assert_generation_allowed(tenant_id=tenant_id, user_id=user_id)
    if not tid:
        return ""
    try:
        daily_cap = int(os.getenv("LUMEN_DAILY_CREDIT_CAP") or "0")
    except ValueError:
        daily_cap = 0
    if daily_cap > 0:
        try:
            from lumen.platform.credits.llm_live import _tenant_llm_spent_today

            spent = int(_tenant_llm_spent_today(tid, credit_service) or 0)
            if spent >= daily_cap:
                raise GenerationBlockedError("daily_credit_cap", tenant_id=tid)
        except GenerationBlockedError:
            raise
        except Exception:
            logger.debug("daily cap precheck soft-fail", exc_info=True)
    return tid


__all__ = [
    "GenerationBlockedError",
    "resolve_tenant_id",
    "require_tenant_for_llm",
    "assert_generation_allowed",
    "assert_hosting_allowed",
    "assert_llm_spend_allowed",
]
