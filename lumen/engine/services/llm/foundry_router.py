"""Microsoft Foundry Model Router — production primary LLM path.

Official Azure/Foundry Chat Completions against a ``model-router`` deployment.
Routing mode (Balanced / Cost / Quality) is chosen per agent task by selecting
the matching deployment name (mode is configured on the Azure deployment).

Reference:
https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/model-router
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Any, Literal

logger = logging.getLogger(__name__)

RoutingMode = Literal["balanced", "cost", "quality"]

_LAST_LOCK = threading.Lock()
_LAST: dict[str, Any] = {}


def foundry_configured() -> bool:
    return bool(resolve_key() and resolve_endpoint())


def resolve_key() -> str:
    return (
        (os.getenv("AZURE_FOUNDRY_KEY") or "").strip()
        or (os.getenv("AZURE_OPENAI_API_KEY") or "").strip()
    )


def resolve_endpoint() -> str:
    return (
        (os.getenv("AZURE_FOUNDRY_ENDPOINT") or "").strip()
        or (os.getenv("AZURE_OPENAI_ENDPOINT") or "").strip()
    ).rstrip("/")


def mode_for_task(task: str) -> RoutingMode:
    forced = (os.getenv("AZURE_FOUNDRY_ROUTING_MODE") or "").strip().lower()
    if forced in {"balanced", "cost", "quality"}:
        return forced  # type: ignore[return-value]
    task_l = (task or "build").strip().lower()
    if task_l in {"plan", "planner", "architect", "critique", "critic", "review", "qa", "reason"}:
        return "quality"
    if task_l in {"build", "worker", "fast", "repair", "fix"}:
        return "cost"
    return "balanced"


def deployment_for_mode(mode: RoutingMode) -> str:
    """Mode → deployment name (operator may create three routers with different modes)."""
    env_map = {
        "quality": "AZURE_FOUNDRY_DEPLOYMENT_QUALITY",
        "cost": "AZURE_FOUNDRY_DEPLOYMENT_COST",
        "balanced": "AZURE_FOUNDRY_DEPLOYMENT_BALANCED",
    }
    specific = (os.getenv(env_map[mode]) or "").strip()
    if specific:
        return specific
    return (
        (os.getenv("AZURE_FOUNDRY_DEPLOYMENT") or "").strip()
        or (os.getenv("AZURE_OPENAI_DEPLOYMENT") or "").strip()
        or "model-router"
    )


def api_version() -> str:
    return (
        os.getenv("AZURE_FOUNDRY_API_VERSION")
        or os.getenv("AZURE_OPENAI_API_VERSION")
        or "2024-12-01-preview"
    ).strip()


def get_last_result() -> dict[str, Any]:
    with _LAST_LOCK:
        return dict(_LAST)


def _set_last(data: dict[str, Any]) -> None:
    with _LAST_LOCK:
        _LAST.clear()
        _LAST.update(data)


def _headers(key: str) -> dict[str, str]:
    auth = (os.getenv("AZURE_FOUNDRY_AUTH") or "").strip().lower()
    if auth == "bearer" or key.startswith("eyJ"):
        return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    return {"api-key": key, "Content-Type": "application/json"}


def chat_completions(
    *,
    system: str,
    user: str,
    task: str = "build",
    deployment: str | None = None,
    temperature: float = 0.2,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Call Foundry model-router deployment; return content + underlying model.

    Tries Azure deployment URL first, then OpenAI-compatible Foundry path.
    """
    import requests

    if not foundry_configured():
        raise RuntimeError("foundry_not_configured")

    key = resolve_key()
    endpoint = resolve_endpoint()
    mode = mode_for_task(task)
    dep = (deployment or "").strip() or deployment_for_mode(mode)
    ver = api_version()
    to = float(timeout if timeout is not None else (os.getenv("CLINE_LLM_TIMEOUT") or "90"))
    headers = _headers(key)

    payload: dict[str, Any] = {
        "model": dep,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
    }

    urls = [
        f"{endpoint}/openai/deployments/{dep}/chat/completions?api-version={ver}",
        f"{endpoint}/openai/v1/chat/completions",
        f"{endpoint}/v1/chat/completions",
    ]
    last_err = ""
    body: dict[str, Any] | None = None
    used_url = ""
    for url in urls:
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=to)
            if resp.status_code >= 400:
                last_err = f"{resp.status_code}:{(resp.text or '')[:280]}"
                logger.debug("foundry url fail %s → %s", url, last_err)
                continue
            body = resp.json()
            used_url = url
            break
        except Exception as exc:
            last_err = f"{type(exc).__name__}:{exc}"
            logger.debug("foundry url error %s → %s", url, last_err)
            continue

    if body is None:
        raise RuntimeError(f"foundry_http_failed:{last_err}")

    choices = body.get("choices") or []
    if not choices:
        raise RuntimeError("foundry_empty_choices")
    msg = choices[0].get("message") or {}
    content = str(msg.get("content") or msg.get("reasoning_content") or "").strip()
    if not content:
        raise RuntimeError("foundry_empty_content")

    underlying = str(body.get("model") or dep)
    usage = body.get("usage") or {}
    result = {
        "content": content,
        "model": underlying,
        "deployment": dep,
        "mode": mode,
        "usage": usage,
        "url": used_url,
    }
    _set_last(result)
    logger.info(
        "foundry router mode=%s deployment=%s underlying=%s",
        mode,
        dep,
        underlying,
    )
    return result


__all__ = [
    "foundry_configured",
    "mode_for_task",
    "deployment_for_mode",
    "chat_completions",
    "get_last_result",
    "resolve_key",
    "resolve_endpoint",
]
