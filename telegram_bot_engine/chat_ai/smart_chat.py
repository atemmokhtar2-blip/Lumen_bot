"""
SmartChat — Hugging Face guidance layer (chat only).

Responsibilities:
  - Understand user intent from minimal wording (Arabic / English).
  - Ask clarifying questions when needed.
  - Recommend the correct system capability (or return a helpful reply).
  - NEVER generate code, NEVER touch formal_engine, NEVER invent success.

Uses Hugging Face Inference Providers only. Never inside formal_engine.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("ai_agent_7h_bot.chat_ai")

# ---------------------------------------------------------------------------
# System knowledge (mirrors ChatRouter capabilities — keep in sync)
# ---------------------------------------------------------------------------

_CAPABILITIES_TEXT = """
System capabilities (route only when intent is clear; never invent success):
generate_bot, clone_repo, host_start, host_stop, host_status, host_diagnose,
static_analysis, package_health, upgrade_recommend, upgrade_apply,
repo_develop, live_run, help
"""

_SYSTEM_PROMPT = f"""You are a senior software engineer collaborating with the user inside a Telegram bot builder system.

Hard rules (never break):
1. You do NOT write project code or claim files were generated. Engines do that.
2. You talk like a real professional developer partner: precise, honest, technical when needed, natural Arabic (or English if the user writes English).
3. NEVER use canned scripts, fixed question lists, or marketing phrases. Every reply must be computed from THIS user's message + the dynamic context you receive (memory, prior projects, resolved paths).
4. If the request is vague, ask ONE focused clarifying question derived only from what is missing in their text — not a generic questionnaire.
5. If they refer to prior work and context provides a path/label, treat that as the working project and discuss changes against it.
6. When intent is clear enough for an engine, return type=route with the right capability_id and a short natural acknowledgment (not a template).
7. You may challenge weak architecture or missing requirements briefly, like a senior dev would — still no fixed phrases.
8. Forbidden: domain bot templates, default command packs, pretending work is done.

{_CAPABILITIES_TEXT}

Respond with JSON only:
{{"type":"reply","text":"..."}}
or
{{"type":"route","capability_id":"generate_bot","confidence":0.0,"params":{{}},"text":"..."}}
or
{{"type":"recommend","capability_id":"...","confidence":0.0,"text":"..."}}
"""


@dataclass
class SmartChatResult:
    """Result from the smart chat layer."""
    type: str  # "reply" | "route" | "error"
    text: str = ""
    capability_id: str = ""
    confidence: float = 0.0
    params: dict[str, Any] = field(default_factory=dict)
    raw: str = ""


def _parse_response(content: str) -> SmartChatResult:
    """Extract JSON from model output robustly."""
    content = (content or "").strip()
    if not content:
        return SmartChatResult(type="error", text="")

    # Try direct JSON
    try:
        data = json.loads(content)
        return _from_dict(data, content)
    except json.JSONDecodeError:
        pass

    # Try extract first JSON object
    match = re.search(r"\{[\s\S]*\}", content)
    if match:
        try:
            data = json.loads(match.group(0))
            return _from_dict(data, content)
        except json.JSONDecodeError:
            pass

    # Fallback: treat whole text as a helpful reply
    return SmartChatResult(type="reply", text=content[:1500], raw=content)


def _from_dict(data: dict, raw: str) -> SmartChatResult:
    t = str(data.get("type", "reply")).lower().strip()
    if t == "route":
        cap = str(data.get("capability_id", "")).strip()
        conf = float(data.get("confidence", 0.7) or 0.7)
        params = data.get("params") or {}
        if not isinstance(params, dict):
            params = {}
        text = str(data.get("text", "") or "")
        if not cap:
            return SmartChatResult(type="reply", text=text, raw=raw)
        return SmartChatResult(
            type="route",
            text=text,
            capability_id=cap,
            confidence=min(1.0, max(0.0, conf)),
            params=params,
            raw=raw,
        )
    if t in ("recommend", "route"):
        cap = str(data.get("capability_id", "")).strip()
        conf = float(data.get("confidence", 0.6) or 0.6)
        params = data.get("params") or {}
        if not isinstance(params, dict):
            params = {}
        text = str(data.get("text", "") or "")
        return SmartChatResult(
            type=t if t == "recommend" else "route",
            text=text,
            capability_id=cap,
            confidence=min(1.0, max(0.0, conf)),
            params=params,
            raw=raw,
        )
    text = str(data.get("text", "") or data.get("message", "") or "")
    return SmartChatResult(type="reply", text=text, raw=raw)


def smart_chat_reply(
    user_text: str,
    *,
    conversation_hint: str = "",
    memory_context: str = "",
    timeout: int = 45,
) -> SmartChatResult:
    """
    Call Hugging Face Inference Providers and return a structured result.

    memory_context: dynamic per-user history/projects (from UserMemory) —
    not a template; only real prior interaction with this user.
    """
    user_text = (user_text or "").strip()
    if len(user_text) < 1:
        return SmartChatResult(type="reply", text="")

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
    ]
    # Dynamic user memory first (projects, recent turns, last intent)
    if memory_context and memory_context.strip():
        messages.append({
            "role": "system",
            "content": (
                "سياق هذا المستخدم فقط (ديناميكي من تفاعله السابق، ليست قوالب):\n"
                + memory_context.strip()[:3500]
            ),
        })
    if conversation_hint:
        messages.append({
            "role": "system",
            "content": f"سياق إضافي: {conversation_hint[:400]}",
        })
    messages.append({"role": "user", "content": user_text})

    try:
        from .hf_provider import chat

        content, model = chat(
            messages,
            timeout=timeout,
            max_tokens=900,
            temperature=0.1,
            json_mode=True,
        )
        result = _parse_response(content)
        logger.info("smart_chat provider=huggingface model=%s", model)
        logger.info(
            "smart_chat type=%s cap=%s conf=%.2f",
            result.type,
            result.capability_id,
            result.confidence,
        )
        return result
    except Exception as e:
        logger.exception("Hugging Face smart_chat failed: %s", e)
        return SmartChatResult(
            type="error",
            text="",
            raw=str(e)[:200],
        )
