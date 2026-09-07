"""Phase 3 — workspace readiness after GitHub bind.

Connection layer stops at auth + list.
Workspace layer (bind) produces active_repo.
This module decides what is still missing before trial/host runtime.

Does NOT deploy. Hosting/trial buttons appear only when gaps are empty
or only the bot token remains (handled by pending_run / token_handler).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("lumen.connections.readiness")

# Env names supplied by Lumen runtime / token flow — not asked again here
_RUNTIME_PROVIDED = frozenset(
    {
        "TELEGRAM_BOT_TOKEN",
        "BOT_TOKEN",
        "TOKEN",
        "PORT",
        "HOST",
        "WEBHOOK_URL",
        "PYTHONUNBUFFERED",
    }
)


@dataclass
class ReadinessResult:
    ready: bool
    missing_env: list[str] = field(default_factory=list)
    summary_ar: str = ""
    can_show_trial: bool = False
    can_show_host: bool = False


def missing_env_from_contract(contract: Any) -> list[str]:
    names: list[str] = []
    env_vars = getattr(contract, "env_vars", None)
    if env_vars is None and isinstance(contract, dict):
        env_vars = contract.get("env_vars") or []
    for item in env_vars or []:
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
        else:
            name = str(getattr(item, "name", "") or "").strip()
        if not name or not name.isupper():
            continue
        if name in _RUNTIME_PROVIDED:
            continue
        if name not in names:
            names.append(name)
    return names[:20]


def evaluate_readiness(
    *,
    active_repo: dict[str, Any] | None,
    collected_env: dict[str, str] | None = None,
) -> ReadinessResult:
    active = active_repo or {}
    path = str(active.get("path") or "").strip()
    if not path:
        return ReadinessResult(
            ready=False,
            summary_ar="لا يوجد مستودع مربوط في مساحة العمل.",
            can_show_trial=False,
            can_show_host=False,
        )

    contract = active.get("contract")
    missing = missing_env_from_contract(contract)
    collected = {str(k).upper(): str(v) for k, v in (collected_env or {}).items() if v}
    # Also accept env already stored on active_repo
    stored = active.get("env") if isinstance(active.get("env"), dict) else {}
    for k, v in stored.items():
        if v:
            collected[str(k).upper()] = str(v)

    still = [n for n in missing if n not in collected]
    if still:
        return ReadinessResult(
            ready=False,
            missing_env=still,
            summary_ar="ناقص متغيرات بيئة: " + ", ".join(still[:8]),
            can_show_trial=False,
            can_show_host=False,
        )

    is_bot = False
    if isinstance(contract, dict):
        is_bot = bool(contract.get("is_telegram_bot"))
    return ReadinessResult(
        ready=True,
        missing_env=[],
        summary_ar="المستودع جاهز لمساحة العمل.",
        can_show_trial=True,
        can_show_host=True if is_bot or True else True,
    )


def apply_collected_env(active_repo: dict[str, Any], name: str, value: str) -> dict[str, Any]:
    out = dict(active_repo or {})
    env = dict(out.get("env") or {})
    env[str(name).upper()] = value
    out["env"] = env
    return out
