"""Hugging Face execution-plan service.

This module turns user requirements into a validated, implementation-oriented
plan. It does not contain domain templates and never writes project files.
The downstream generator consumes the plan as its single source of truth.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any


_PLAN_SYSTEM = r"""You are the execution architect for a custom Telegram bot.
Return ONE JSON object only. Do not write Python code and do not use domain
packs or pre-made ecommerce/booking/support templates. Extract only what the
user requested; when a technical detail is required but unspecified, record it
in unresolved_questions instead of inventing it.

The JSON object MUST have this shape:
{
  "bot_name": "string",
  "summary": "string",
  "language": "ar|en|mixed",
  "commands": [{"name":"snake_case","description":"string","admin_only":false,"roles":["user"]}],
  "buttons": [{"label":"string","callback_id":"snake_case"}],
  "entities": [{"name":"string","fields":[{"name":"string","type":"str|int|bool|float|list|dict"}],"relations":[{"target":"string","type":"one_to_many|many_to_one|one_to_one"}]}],
  "flows": [{"name":"string","trigger":"command or callback","steps":[{"id":"string","action":"string","label":"string","next_id":"string|null","collects_field":"string|null","branches":[]}]}],
  "permissions": [{"role":"user|admin|owner|custom","allows":["command or callback"]}],
  "conversation_states": [{"name":"string","prompt":"string","next_state":"string|null","collects_field":"string|null"}],
  "services": [{"name":"string","responsibility":"string"}],
  "integrations": ["telegram"],
  "tech":{"database":"sqlite|postgres|none","payments":false,"admin_panel":false,"async_queue":false,"file_handling":false,"state_management":true},
  "quality":{"high_performance":true,"full_error_handling":true,"concurrent_users":false,"modular_code":true},
  "architecture":{"style":"string","framework":"python-telegram-bot","ptb_version":"21+","layers":["string"],"dependency_injection":false},
  "files":[{"path":"relative/path","purpose":"string","dependencies":["relative/path"],"required":true}],
  "acceptance_tests":[{"name":"string","steps":["string"],"expected":"string"}],
  "hard_constraints":["string"],
  "unresolved_questions":["string"]
}

Rules:
- framework MUST be python-telegram-bot with ptb_version 21+ (never legacy Updater API).
- Create a dedicated flow for every non-trivial command; steps must be ordered and unique ids.
- Do not share conversation state names across unrelated flows.
- Every button callback_id must map to a real command or flow trigger.
- Preserve every explicit entity field, rule, permission, and integration from the user text.
- Always include these required files in "files": main.py, requirements.txt, .env.example, README.md
  plus modular modules justified by the architecture (e.g. handlers/, services/, models/, db/).
- language must reflect the user text (ar if Arabic dominates).
- Do not add commands merely because an entity exists. /start and /help may be added as runtime essentials only.
- Never claim a feature is implemented; this is a plan for a later code-generation stage.
"""

@dataclass
class ExecutionPlanResult:
    ok: bool
    plan: dict[str, Any] = field(default_factory=dict)
    model_used: str = ""
    error: str = ""
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "plan": self.plan,
            "model_used": self.model_used,
            "error": self.error,
            "warnings": self.warnings,
        }


def _json_object(text: str) -> dict[str, Any] | None:
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except Exception:
        match = re.search(r"\{[\s\S]*\}", text or "")
        if not match:
            return None
        try:
            value = json.loads(match.group(0))
            return value if isinstance(value, dict) else None
        except Exception:
            return None


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _normalize(plan: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    out = dict(plan)
    out["commands"] = [x for x in _list(plan.get("commands")) if isinstance(x, dict) and x.get("name")]
    out["entities"] = [x for x in _list(plan.get("entities")) if isinstance(x, dict) and x.get("name")]
    out["flows"] = [x for x in _list(plan.get("flows")) if isinstance(x, dict) and x.get("name")]
    out["services"] = [x for x in _list(plan.get("services")) if isinstance(x, dict) and x.get("name")]
    out["files"] = [x for x in _list(plan.get("files")) if isinstance(x, dict) and x.get("path")]
    out["acceptance_tests"] = [x for x in _list(plan.get("acceptance_tests")) if isinstance(x, dict)]
    out["buttons"] = [x for x in _list(plan.get("buttons")) if isinstance(x, dict) and x.get("label")]
    out["permissions"] = [x for x in _list(plan.get("permissions")) if isinstance(x, dict)]
    out["conversation_states"] = [x for x in _list(plan.get("conversation_states")) if isinstance(x, dict)]
    out["unresolved_questions"] = [str(x) for x in _list(plan.get("unresolved_questions")) if str(x).strip()]
    for flow in out["flows"]:
        flow["steps"] = [s for s in _list(flow.get("steps")) if isinstance(s, dict) and s.get("id") and s.get("action")]
        if not flow["steps"]:
            warnings.append(f"flow_without_steps:{flow.get('name')}")
    if not out.get("bot_name"):
        warnings.append("bot_name_empty")
    if not out["commands"]:
        return out, warnings + ["no_commands"]
    if out["flows"] and any(not f.get("steps") for f in out["flows"]):
        warnings.append("incomplete_flow_steps")
    return out, warnings


def plan_from_text(user_text: str, *, timeout: int = 120, max_tokens: int | None = None) -> ExecutionPlanResult:
    from . import multi_provider as mp

    if not mp.any_enabled():
        return ExecutionPlanResult(
            False,
            error="No AI provider configured (set OPENAI_API_KEY and/or HF_TOKEN)",
        )
    tokens = max_tokens or int(
        __import__("os").environ.get(
            "PLAN_MAX_TOKENS",
            __import__("os").environ.get("HF_PLAN_MAX_TOKENS", "10000"),
        )
    )
    try:
        content, model = mp.chat(
            [
                {"role": "system", "content": _PLAN_SYSTEM},
                {"role": "user", "content": "USER REQUIREMENTS:\n" + (user_text or "")[:30000]},
            ],
            timeout=timeout,
            max_tokens=tokens,
            temperature=0.0,
            json_mode=True,
        )
    except Exception as exc:
        return ExecutionPlanResult(False, model_used="", error=f"plan_failed:{type(exc).__name__}:{exc}"[:1200])
    raw = _json_object(content)
    if raw is None:
        return ExecutionPlanResult(False, model_used=model, error="hf_plan_json_parse_failed")
    plan, warnings = _normalize(raw)
    if "no_commands" in warnings:
        return ExecutionPlanResult(False, plan=plan, model_used=model, error="hf_plan_has_no_commands", warnings=warnings)
    return ExecutionPlanResult(True, plan=plan, model_used=model, warnings=warnings)


def plan_to_formal_text(plan: dict[str, Any]) -> str:
    """Serialize the plan into explicit, parser-friendly requirements text."""
    lines = [f"بوت {plan.get('bot_name') or 'custom_bot'}", str(plan.get("summary") or "")]
    for c in plan.get("commands") or []:
        lines.append(f"/{c.get('name')} - {c.get('description') or c.get('name')}")
    for e in plan.get("entities") or []:
        fields = " و ".join(str(f.get("name")) for f in (e.get("fields") or []) if isinstance(f, dict))
        lines.append(f"كيان {e.get('name')} يحتاج {fields}" if fields else f"كيان {e.get('name')}")
    for f in plan.get("flows") or []:
        steps = " ثم ".join(str(s.get("action")) for s in (f.get("steps") or []))
        lines.append(f"تدفق {f.get('name')} للأمر {f.get('trigger')}: {steps}")
    for p in plan.get("permissions") or []:
        lines.append(f"صلاحية {p.get('role')}: {', '.join(map(str, p.get('allows') or []))}")
    for q in plan.get("hard_constraints") or []:
        lines.append(f"قاعدة إلزامية: {q}")
    tech = plan.get("tech") or {}
    if tech.get("database") and tech.get("database") != "none":
        lines.append(f"قاعدة بيانات {tech.get('database')}")
    if tech.get("payments"):
        lines.append("تكامل دفع")
    if tech.get("file_handling"):
        lines.append("رفع ملفات")
    return "\n".join(x for x in lines if x.strip())


__all__ = ["ExecutionPlanResult", "plan_from_text", "plan_to_formal_text"]
