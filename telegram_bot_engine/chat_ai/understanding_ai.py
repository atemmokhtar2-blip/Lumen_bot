"""
Understanding-AI — g4f layer for SPEC enrichment only.

Allowed:
  - Rewrite messy natural language into a structured specification text
    (commands / entities / buttons / rules / flows) grounded in the user words.

Forbidden:
  - Generating Python code
  - Touching formal_engine internals
  - Inventing domain packs (shop/ticket/edu skeletons)

Pipeline position:
  user text → [optional Understanding-AI] → extract_dsl → grounding_gate → infer → transpile

Latency note:
  Local formal path is ~1–3s. Adding g4f typically adds several seconds
  (often 3–20s depending on provider). Free models are not guaranteed <2s.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("ai_agent_7h_bot.understanding_ai")

# Prefer models that handle structured extraction well (g4f routes by name).
_MODEL_CANDIDATES = (
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "claude-3.5-sonnet",
    "claude-3-haiku",
    "gpt-4o-mini",
    "gpt-4o",
)

_SYSTEM = """أنت محرك فهم مواصفات بوتات تليجرام فقط (Understanding).

المهمة: حوّل وصف المستخدم إلى مواصفة منظمة بالعربية أو الإنجليزية.
استخرج فقط ما ورد أو ما يُستنتج مباشرة من النص — ممنوع اختراع أوامر/كيانات من قوالب جاهزة.

أرجع JSON فقط بهذا الشكل:
{
  "bot_name": "string",
  "commands": [{"name": "register", "description": "...", "admin_only": false}],
  "buttons": ["label1", "label2"],
  "entities": [{"name": "Student", "fields": ["id", "name", "email"]}],
  "rules": ["لو ... يفعل ..."],
  "flows": [{"command": "register", "steps": ["name", "email"]}],
  "notes": ""
}

قواعد صارمة:
1) name للأمر بدون شرطة مائلة (register وليس /register).
2) لا تضف أوامر لم يذكرها المستخدم إلا start و help إن لزم الهيكل.
3) admin_only=true فقط إذا ذكر أدمن/admin.
4) الحقول من النص فقط.
5) لا تكتب كودًا ولا Markdown خارج JSON.
"""


@dataclass
class UnderstandingAIResult:
    ok: bool
    structured_text: str = ""
    model_used: str = ""
    elapsed_ms: float = 0.0
    error: str = ""
    raw_json: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "model_used": self.model_used,
            "elapsed_ms": self.elapsed_ms,
            "error": self.error,
            "has_structured_text": bool(self.structured_text),
            "commands": len((self.raw_json or {}).get("commands") or []),
            "entities": len((self.raw_json or {}).get("entities") or []),
            "rules": len((self.raw_json or {}).get("rules") or []),
        }


def _enabled() -> bool:
    # HF is the supported provider for this optional enrichment layer.
    # It can still be disabled explicitly for a formal-only deployment.
    v = (os.environ.get("UNDERSTANDING_AI") or ("1" if os.environ.get("HF_TOKEN") else "0")).strip().lower()
    return v not in ("0", "false", "no", "off")


def _parse_json(content: str) -> dict[str, Any] | None:
    content = (content or "").strip()
    if not content:
        return None
    try:
        data = json.loads(content)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[\s\S]*\}", content)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def _spec_to_text(data: dict[str, Any], original: str) -> str:
    """Canonical sectioned text that extract_dsl already understands."""
    lines: list[str] = []
    name = str(data.get("bot_name") or "").strip()
    if name:
        lines.append(f"اعمل بوت تليجرام باسم {name}")
    else:
        lines.append((original or "").strip().splitlines()[0][:200] if original else "اعمل بوت تليجرام")

    cmds = data.get("commands") or []
    if isinstance(cmds, list) and cmds:
        lines.append("")
        lines.append("الأوامر:")
        for c in cmds:
            if not isinstance(c, dict):
                continue
            n = str(c.get("name") or "").strip().lstrip("/").replace(" ", "_")
            if not n:
                continue
            desc = str(c.get("description") or n).strip()
            admin = bool(c.get("admin_only"))
            if admin and "أدمن" not in desc and "admin" not in desc.lower():
                desc = f"{desc} (أدمن)"
            lines.append(f"/{n} - {desc}")

    buttons = data.get("buttons") or []
    if isinstance(buttons, list) and buttons:
        lines.append("")
        lines.append("الأزرار:")
        for b in buttons:
            lab = str(b if not isinstance(b, dict) else b.get("label") or "").strip()
            if lab:
                lines.append(f"- {lab}")

    ents = data.get("entities") or []
    if isinstance(ents, list) and ents:
        lines.append("")
        lines.append("الكيانات:")
        for e in ents:
            if not isinstance(e, dict):
                continue
            en = str(e.get("name") or "").strip()
            if not en:
                continue
            fields = e.get("fields") or e.get("attributes") or []
            if isinstance(fields, list) and fields:
                fl = ", ".join(str(x).strip() for x in fields if str(x).strip())
                lines.append(f"- {en} ({fl})")
            else:
                lines.append(f"- {en}")

    rules = data.get("rules") or []
    if isinstance(rules, list) and rules:
        lines.append("")
        lines.append("القواعد:")
        for r in rules:
            rs = str(r).strip()
            if rs:
                lines.append(f"- {rs}")

    flows = data.get("flows") or []
    if isinstance(flows, list) and flows:
        # embed flow hints into command descriptions already; also keep explicit lines
        lines.append("")
        lines.append("التدفقات:")
        for f in flows:
            if not isinstance(f, dict):
                continue
            cmd = str(f.get("command") or "").strip().lstrip("/")
            steps = f.get("steps") or []
            if cmd and isinstance(steps, list) and steps:
                step_s = " و ".join(str(s) for s in steps if str(s).strip())
                lines.append(f"- /{cmd} يجمع {step_s}")

    notes = str(data.get("notes") or "").strip()
    if notes:
        lines.append("")
        lines.append(notes)

    # Keep original as appendix for grounding (names must appear in combined text)
    body = "\n".join(lines).strip()
    return body + "\n\n---\nالأصل:\n" + (original or "")[:4000]


def enrich_spec(
    user_text: str,
    *,
    timeout: int | None = None,
    models: tuple[str, ...] | None = None,
) -> UnderstandingAIResult:
    """
    Call g4f to produce a structured specification text.
    On any failure → ok=False and empty structured_text (caller falls back to raw text).
    """
    import time

    text = (user_text or "").strip()
    if not text:
        return UnderstandingAIResult(ok=False, error="empty_text")

    if not _enabled():
        return UnderstandingAIResult(ok=False, error="disabled")

    # Short specs that are already sectioned: still try AI, but caller may skip
    timeout = timeout if timeout is not None else int(os.environ.get("UNDERSTANDING_AI_TIMEOUT", "25"))
    candidates = models or _MODEL_CANDIDATES
    # Allow override: UNDERSTANDING_AI_MODEL=claude-3.5-sonnet
    forced = (os.environ.get("UNDERSTANDING_AI_MODEL") or "").strip()
    if forced:
        candidates = (forced,) + tuple(c for c in candidates if c != forced)

    t0 = time.perf_counter()
    messages = [
        {"role": "system", "content": _SYSTEM},
        {
            "role": "user",
            "content": (
                "حوّل الوصف التالي إلى JSON المواصفة المطلوب فقط.\n\n"
                f"{text[:6000]}"
            ),
        },
    ]
    try:
        from .hf_provider import chat

        requested_model = forced or (models[0] if models else None)
        content, model = chat(
            messages,
            timeout=timeout,
            model=requested_model,
            max_tokens=1800,
            temperature=0,
            json_mode=True,
        )
        data = _parse_json(content)
        if not data:
            raise ValueError("hf_invalid_json")
        cmds = data.get("commands")
        if not isinstance(cmds, list) or not cmds:
            raise ValueError("hf_no_commands")
        structured = _spec_to_text(data, text)
        elapsed = (time.perf_counter() - t0) * 1000
        logger.info(
            "understanding_ai provider=huggingface model=%s cmds=%s ents=%s ms=%.0f",
            model,
            len(cmds),
            len(data.get("entities") or []),
            elapsed,
        )
        return UnderstandingAIResult(
            ok=True,
            structured_text=structured,
            model_used=f"huggingface:{model}",
            elapsed_ms=round(elapsed, 1),
            raw_json=data,
        )
    except Exception as e:
        elapsed = (time.perf_counter() - t0) * 1000
        error = f"huggingface:{type(e).__name__}:{e}"[:1200]
        logger.warning("understanding_ai failed %s", error)
        return UnderstandingAIResult(ok=False, error=error, elapsed_ms=round(elapsed, 1))


def prepare_generation_text(user_text: str) -> tuple[str, UnderstandingAIResult]:
    """
    Returns (text_for_formal_pipeline, ai_result).
    Falls back to original text when AI is off/failed.
    """
    original = user_text or ""
    if not _enabled():
        return original, UnderstandingAIResult(ok=False, error="disabled")
    result = enrich_spec(original)
    if result.ok and result.structured_text.strip():
        return result.structured_text, result
    return original, result
