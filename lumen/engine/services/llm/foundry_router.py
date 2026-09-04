"""Microsoft Foundry Model Router — production primary when Azure is configured.

Calls the real Foundry / Azure OpenAI chat-completions deployment named
``model-router`` (or env override). Routing mode is selected by mapping the
agent task to a deployment profile:

  plan / critique / reason  → Quality  (AZURE_FOUNDRY_DEPLOYMENT_QUALITY)
  build / fast              → Cost     (AZURE_FOUNDRY_DEPLOYMENT_COST)
  default                   → Balanced (AZURE_FOUNDRY_DEPLOYMENT)

Docs: https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/model-router
"""
from __future__ import annotations

import logging
import os
from typing import Any, Literal

logger = logging.getLogger(__name__)

RoutingMode = Literal["balanced", "cost", "quality"]


def foundry_configured() -> bool:
    key = (
        (os.getenv("AZURE_FOUNDRY_KEY") or "").strip()
        or (os.getenv("AZURE_OPENAI_API_KEY") or "").strip()
    )
    endpoint = (
        (os.getenv("AZURE_FOUNDRY_ENDPOINT") or "").strip()
        or (os.getenv("AZURE_OPENAI_ENDPOINT") or "").strip()
    )
    return bool(key and endpoint)


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
    task_l = (task or "build").strip().lower()
    if task_l in {"plan", "planner", "architect", "critique", "critic", "review", "qa", "reason"}:
        return "quality"
    if task_l in {"build", "worker", "fast", "repair", "fix"}:
        # Agent coding steps: prefer cost unless explicitly overridden
        forced = (os.getenv("AZURE_FOUNDRY_ROUTING_MODE") or "").strip().lower()
        if forced in {"balanced", "cost", "quality"}:
            return forced  # type: ignore[return-value]
        return "cost"
    return "balanced"


def deployment_for_mode(mode: RoutingMode) -> str:
    """Map routing mode → Foundry deployment name.

    Mode is primarily configured on the Azure deployment itself; we select
    among optional per-mode deployment names when the operator created
    separate routers (router-quality / router-cost / router-balanced).
    """
    if mode == "quality":
        return (
            (os.getenv("AZURE_FOUNDRY_DEPLOYMENT_QUALITY") or "").strip()
            or (os.getenv("AZURE_FOUNDRY_DEPLOYMENT") or "").strip()
            or "model-router"
        )
    if mode == "cost":
        return (
            (os.getenv("AZURE_FOUNDRY_DEPLOYMENT_COST") or "").strip()
            or (os.getenv("AZURE_FOUNDRY_DEPLOYMENT") or "").strip()
            or "model-router"
        )
    return (
        (os.getenv("AZURE_FOUNDRY_DEPLOYMENT_BALANCED") or "").strip()
        or (os.getenv("AZURE_FOUNDRY_DEPLOYMENT") or "").strip()
        or "model-router"
    )


def api_version() -> str:
    return (os.getenv("AZURE_FOUNDRY_API_VERSION") or os.getenv("AZURE_OPENAI_API_VERSION") or "2024-12-01-preview").strip()


def chat_completions(
    *,
    system: str,
    user: str,
    task: str = "build",
    deployment: str | None = None,
    temperature: float = 0.2,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Call Foundry Model Router via Azure chat completions.

    Returns dict: content, model (underlying model selected by router),
    deployment, mode, usage.
    """
    import requests

    if not foundry_configured():
        raise RuntimeError("foundry_not_configured")

    key = resolve_key()
    endpoint = resolve_endpoint()
    mode = mode_for_task(task)
    deployment = (deployment or "").strip() or deployment_for_mode(mode)
    ver = api_version()
    to = float(timeout if timeout is not None else (os.getenv("CLINE_LLM_TIMEOUT") or "90"))

    # Azure OpenAI deployment path (canonical for Foundry model-router)
    url = f"{endpoint}/openai/deployments/{deployment}/chat/completions?api-version={ver}"
    headers = {
        "api-key": key,
        "Content-Type": "application/json",
    }
    # Some Foundry endpoints also accept Bearer
    if key.startswith("eyJ") or (os.getenv("AZURE_FOUNDRY_AUTH") or "").strip().lower() == "bearer":
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }

    payload: dict[str, Any] = {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
    }
    # model field: deployment name for router
    payload["model"] = deployment

    resp = requests.post(url, headers=headers, json=payload, timeout=to)
    if resp.status_code >= 400:
        # Fallback: OpenAI-compatible base path used by some Foundry endpoints
        alt = f"{endpoint}/openai/v1/chat/completions"
        headers2 = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        if not key.startswith("eyJ"):
            headers2 = {"api-key": key, "Content-Type": "application/json"}
        resp2 = requests.post(alt, headers=headers2, json=payload, timeout=to)
        if resp2.status_code >= 400:
            raise RuntimeError(
                f"foundry_http_{resp.status_code}:{(resp.text or '')[:300]} | "
                f"compat_{resp2.status_code}:{(resp2.text or '')[:200]}"
            )
        body = resp2.json()
    else:
        body = resp.json()

    choices = body.get("choices") or []
    if not choices:
        raise RuntimeError("foundry_empty_choices")
    msg = choices[0].get("message") or {}
    content = str(msg.get("content") or "").strip()
    if not content:
        content = str(msg.get("reasoning_content") or "").strip()
    if not content:
        raise RuntimeError("foundry_empty_content")

    underlying = str(body.get("model") or deployment)
    usage = body.get("usage") or {}
    logger.info(
        "foundry model-router mode=%s deployment=%s underlying=%s",
        mode,
        deployment,
        underlying,
    )
    return {
        "content": content,
        "model": underlying,
        "deployment": deployment,
        "mode": mode,
        "usage": usage,
        "raw_body": body,
    }


__all__ = [
    "foundry_configured",
    "mode_for_task",
    "deployment_for_mode",
    "chat_completions",
    "resolve_key",
    "resolve_endpoint",
]
