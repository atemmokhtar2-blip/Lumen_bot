"""
SpecTranslator v2 — multi-pass AI translator that emits RichSpec JSON directly.

Pipeline (4 passes, each adds fidelity):
  PASS 1 — Extraction:   user text → flat command/entity/button/rule JSON
  PASS 2 — Fidelity audit: compare JSON against original text, add/remove
  PASS 3 — Deep inference: enrich each command with kind, collects_fields,
           post_action, entity, flow_steps, and type each entity field
  PASS 4 — Grounding: drop any item whose evidence is not traceable to the
           original user text (semantic similarity fallback, no synonym lists)

KEY DIFFERENCES from v1:
  - Output is a RichSpec dict (deeply typed) — never converted to lossy text.
  - No _SYN synonym dictionary — grounding uses verbatim evidence + similarity.
  - No spec_to_text() — the engine consumes the RichSpec directly.
  - The AI classifies commands (kind) instead of hardcoded verb/stem lists.

AI never generates code. The formal engine is the only code generator.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any

from ..formal_engine.schemas.rich_spec import (
    CommandKind,
    PostAction,
    RichSpec,
    validate_rich_spec,
    rich_spec_from_dict,
)

logger = logging.getLogger("ai_agent_7h_bot.spec_translator_v2")

_MODEL_CANDIDATES = (
    "gemini-2.0-flash",
    "gpt-4o-mini",
    "claude-3.5-sonnet",
    "gemini-1.5-flash",
    "claude-3-haiku",
    "gpt-4o",
)

# ─────────────────────────── system prompts ──────────────────────────────

_EXTRACT_SYSTEM = """You are a Spec Translator for Telegram bots. You output ONLY valid JSON.

ABSOLUTE OUTPUT RULES:
- Reply with a single JSON object. Nothing else.
- No markdown. No code fences. No ```json. No explanations. No greetings.
- First character must be { and last character must be }.
- Use double quotes for all keys and string values (strict JSON).

ROLE:
- Translate the user's natural language into a structured bot specification.
- Do NOT write Python or any code.
- Do NOT invent features the user did not mention or clearly imply.
- Extract ALL functions the user mentioned (lists, "and", "فيه X و Y", "زرار X وزرار Y").
- CRITICAL: Create a button in buttons[] for EVERY command the user mentions as a
  button ("زرار", "button", "زر"). Each button's target_command must match a command name.
- If the user mentions "زرار X" (button X), create BOTH a command AND a button for it.
- The user is the ONLY source of truth — never add commands/buttons they didn't ask for.

SCHEMA (output exactly this shape):
{
  "bot_name": "",
  "bot_kind": "custom",
  "description": "",
  "language": "ar",
  "commands": [
    {
      "name": "register",
      "description": "تسجيل",
      "admin_only": false,
      "evidence": {"quote": "تسجيل", "confidence": 0.9}
    }
  ],
  "buttons": [
    {"label": "تسجيل", "callback_id": "register", "target_command": "register", "evidence": {"quote": "تسجيل"}}
  ],
  "entities": [
    {"name": "Customer", "fields": [{"name": "name", "field_type": "str"}, {"name": "phone", "field_type": "str"}], "evidence": {"quote": "عملاء"}}
  ],
  "rules": [
    {"condition": "if registered then save", "effect": "save record", "evidence": {"quote": "يحفظ"}}
  ],
  "tech": {"database": "sqlite", "payments": false, "admin_panel": false, "notifications": false},
  "needs_clarification": false,
  "clarification_questions": []
}

FIELD RULES:
- commands[].name: lowercase English [a-z0-9_], no slash, never start/help.
- commands[].description: keep user language when possible.
- entities[].name: PascalCase English identifier.
- entities[].fields[].name: lowercase English field id.
- entities[].fields[].field_type: one of str, int, bool, float, list.
- evidence.quote: short verbatim phrase from the user text.
- If the user message is too vague: needs_clarification=true with 1-3 questions in the user's language.
"""

_AUDIT_SYSTEM = """You are a fidelity auditor for bot specs.
Given the original user text and a JSON spec, output ONLY a corrected JSON object (same schema as input).
- Add commands/entities/fields clearly present in the user text but missing in JSON.
- CRITICAL: Ensure every "زرار" / "button" / "زر" the user mentioned has BOTH a command
  AND a button in buttons[] with target_command matching the command name.
- Remove items with no support in the user text.
- Improve evidence.quote to short verbatim spans from the user text.
- No markdown, no prose, no code fences. First char { last char }.
"""

_INFER_SYSTEM = """You are a deep inference engine for Telegram bot specs.
Given a JSON spec, enrich EVERY command with its behavioral semantics. Output ONLY JSON (same overall shape, but commands are deeper).

For EACH command add/complete these fields:
- "kind": one of: start, help, collect, lookup, list, stats, broadcast, action, info, navigate, custom
    * collect  = gathers several fields from the user (a wizard / form)
    * lookup   = queries one record by id/key
    * list     = lists / browses multiple records
    * stats    = aggregate numbers / dashboard
    * broadcast= admin sends to many users
    * action   = performs a side-effect (send, notify, toggle, delete)
    * info     = static informational reply
    * navigate = opens a menu / keyboard
- "entity": the entity name this command operates on (empty if none)
- "collects_fields": list of field keys the command gathers from the user (empty if none)
- "post_action": one of: store, confirm, notify, compute, none
    * store   = persist collected data into the entity store
    * confirm = echo back the collected data
    * notify  = send a notification
    * compute = run a calculation and reply
- "reply_text": a short reply message (for info/start/help/action commands)
- "flow_steps": for collect commands, an ordered list of {"key": field, "prompt": message, "action": "ask"}

Also ensure every entity has typed fields (field_type: str/int/bool/float).
Do NOT invent new commands or entities — only enrich existing ones.
No markdown, no prose. First char { last char }.
"""

_RETRY_SYSTEM = """You previously returned invalid JSON. Output ONLY one corrected JSON object.
No markdown, no fences, no prose. First char { last char }. Same schema. Fix the errors listed."""


# ─────────────────────────── result type ─────────────────────────────────

@dataclass
class TranslatorV2Result:
    ok: bool
    rich_spec: RichSpec | None = None
    raw_json: dict[str, Any] = field(default_factory=dict)
    model_used: str = ""
    elapsed_ms: float = 0.0
    error: str = ""
    needs_clarification: bool = False
    clarification_questions: list[str] = field(default_factory=list)
    passes_done: int = 0
    dropped: dict[str, list[str]] = field(default_factory=dict)
    validation_warnings: list[str] = field(default_factory=list)
    retries: int = 0

    def to_dict(self) -> dict[str, Any]:
        spec = self.rich_spec
        return {
            "ok": self.ok,
            "model_used": self.model_used,
            "elapsed_ms": self.elapsed_ms,
            "error": self.error,
            "needs_clarification": self.needs_clarification,
            "clarification_questions": list(self.clarification_questions),
            "passes_done": self.passes_done,
            "commands": len(spec.commands) if spec else 0,
            "entities": len(spec.entities) if spec else 0,
            "buttons": len(spec.buttons) if spec else 0,
            "rules": len(spec.rules) if spec else 0,
            "dropped": dict(self.dropped),
            "validation_warnings": list(self.validation_warnings)[:12],
            "retries": self.retries,
            "schema_version": "2.0",
        }


# ─────────────────────────── config helpers ──────────────────────────────

def _enabled() -> bool:
    v = (os.environ.get("SPEC_TRANSLATOR") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def _repair_enabled() -> bool:
    v = (os.environ.get("SPEC_TRANSLATOR_REPAIR") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def _infer_enabled() -> bool:
    v = (os.environ.get("SPEC_TRANSLATOR_INFER") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def _max_retries() -> int:
    try:
        return int(os.environ.get("SPEC_TRANSLATOR_RETRIES", "2"))
    except ValueError:
        return 2


# ─────────────────────────── JSON extraction ─────────────────────────────

def _extract_json_object(content: str) -> str | None:
    """Extract the first balanced JSON object from a model response."""
    if not content:
        return None
    content = content.strip()
    if content.startswith("```"):
        # strip code fences
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
        content = content.strip()
    # find first { ... last }
    start = content.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(content)):
        ch = content[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return content[start : i + 1]
    return None


def _parse_json(content: str) -> dict[str, Any] | None:
    raw = _extract_json_object(content or "")
    if not raw:
        return None
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, ValueError):
        pass
    # last resort: try the whole content
    try:
        data = json.loads(content)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, ValueError):
        pass
    return None


# ─────────────────────────── model call ──────────────────────────────────

def _call_model(client: Any, model: str, messages: list[dict[str, str]]) -> str:
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "web_search": False,
    }
    for extra in ({"temperature": 0}, {"temperature": 0.05}, {}):
        try:
            response = client.chat.completions.create(**kwargs, **extra)
            if response and response.choices:
                return (response.choices[0].message.content or "").strip()
            return ""
        except TypeError:
            continue
        except Exception as e:
            logger.debug("model call extra failed: %s", e)
            continue
    return ""


def _call_for_json(
    client: Any,
    model: str,
    system_prompt: str,
    user_content: str,
    *,
    retry_errors: str | None = None,
) -> dict[str, Any] | None:
    """Call the model with a system prompt and parse JSON from the response."""
    if retry_errors:
        messages = [
            {"role": "system", "content": _RETRY_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"Fix the JSON. Validation problems:\n{retry_errors}\n\n"
                    f"Original user text:\n{user_content[:5000]}\n\n"
                    "Return ONLY the corrected JSON object."
                ),
            },
        ]
    else:
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    "Translate the following user text into the required JSON schema.\n"
                    "JSON only. No markdown. No prose.\n\n"
                    f"{user_content[:7000]}"
                ),
            },
        ]
    content = _call_model(client, model, messages)
    return _parse_json(content)


# ─────────────────────────── evidence grounding ──────────────────────────

def _normalize_text(s: str) -> str:
    """Light normalization for Arabic + English similarity comparison."""
    if not s:
        return ""
    s = s.lower()
    # Arabic normalization
    s = re.sub(r"[إأآا]", "ا", s)
    s = s.replace("ى", "ي").replace("ؤ", "و").replace("ئ", "ي")
    s = re.sub(r"[\u064b-\u0652]", "", s)  # remove tashkeel
    s = re.sub(r"\s+", " ", s)
    # remove punctuation for word-level comparison
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _token_set(s: str) -> set[str]:
    return set(_normalize_text(s).split()) if s else set()


def _evidence_grounded(evidence_quote: str, original_norm: str, original_tokens: set[str]) -> bool:
    """
    Decide whether an item's evidence is traceable to the original user text.
    Strategy (no synonym dictionary):
      1. If the evidence quote appears (normalized) as a substring → grounded.
      2. Else if the quote shares enough tokens with the original → grounded.
      3. Else if the quote is very short (≤2 tokens) and at least one token
         appears in the original → grounded (single-word evidence is common).
      4. Otherwise → not grounded.
    """
    quote = evidence_quote or ""
    if not quote:
        # No evidence at all — allow it only if it's a structural minimum
        return False
    qn = _normalize_text(quote)
    if not qn:
        return False
    # 1. substring match
    if qn in original_norm:
        return True
    # 2. token overlap
    q_tokens = set(qn.split())
    if not q_tokens:
        return False
    overlap = q_tokens & original_tokens
    # If most of the quote's tokens appear in the original, it's grounded
    if len(overlap) >= max(1, len(q_tokens) // 2):
        return True
    # 2b. Arabic prefix/substring containment: "طلبيه" shares root "طلب" with
    # original tokens — check if any quote token is a prefix of (or is prefixed
    # by) any original token (length ≥ 3 to avoid noise).
    if len(q_tokens) <= 3:
        for qt in q_tokens:
            if len(qt) >= 3:
                for ot in original_tokens:
                    if len(ot) >= 3 and (qt.startswith(ot[:3]) or ot.startswith(qt[:3])):
                        return True
    # 3. very short evidence — one shared token is enough
    if len(q_tokens) <= 2 and overlap:
        return True
    return False


def _ground_spec(data: dict[str, Any], original: str) -> tuple[dict[str, Any], dict[str, list[str]]]:
    """
    Drop commands/buttons/entities/rules whose evidence is not traceable to the
    original user text. Returns (grounded_data, dropped_report).
    Never drops /start or /help (structural minima).
    """
    original_norm = _normalize_text(original)
    original_tokens = _token_set(original)
    dropped: dict[str, list[str]] = {"commands": [], "buttons": [], "entities": [], "rules": []}

    def _ev_quote(ev: Any) -> str:
        if isinstance(ev, dict):
            return ev.get("quote", "") or ev.get("text", "") or ""
        if isinstance(ev, str):
            return ev
        return ""

    # commands
    cmds = data.get("commands") or []
    kept_cmds = []
    for c in cmds:
        if not isinstance(c, dict):
            continue
        name = (c.get("name") or "").lower().lstrip("/")
        if name in ("start", "help"):
            kept_cmds.append(c)
            continue
        ev = _ev_quote(c.get("evidence"))
        if _evidence_grounded(ev, original_norm, original_tokens):
            kept_cmds.append(c)
        else:
            dropped["commands"].append(name or "?")
    data["commands"] = kept_cmds

    # buttons
    btns = data.get("buttons") or []
    kept_btns = []
    for b in btns:
        if not isinstance(b, dict):
            continue
        ev = _ev_quote(b.get("evidence"))
        if _evidence_grounded(ev, original_norm, original_tokens):
            kept_btns.append(b)
        else:
            dropped["buttons"].append(b.get("label") or b.get("callback_id") or "?")
    data["buttons"] = kept_btns

    # ── Button-completeness safety net ──
    # If the user mentioned buttons ("زرار"/"button"/"زر") in their text, ensure
    # every grounded command (except start/help) has a matching button. This is a
    # data-level fix — NOT a hardcoded template. The commands themselves come 100%
    # from the AI translator; we only ensure the UI surface is complete.
    has_buttons_in_text = any(
        kw in original_norm for kw in ("زرار", "زر ", "زر.", "زرار", "button", "buttons", "زرّار")
    )
    if has_buttons_in_text and kept_cmds:
        existing_btn_targets = {
            (b.get("target_command") or "").lower().lstrip("/")
            for b in kept_btns
            if isinstance(b, dict)
        }
        for c in kept_cmds:
            cname = (c.get("name") or "").lower().lstrip("/")
            if cname in ("start", "help"):
                continue
            if cname in existing_btn_targets:
                continue
            # Auto-create a button for this command using its description as label
            label = c.get("description") or cname
            kept_btns.append({
                "label": label,
                "callback_id": cname,
                "target_command": cname,
                "evidence": c.get("evidence") or {"quote": label},
            })
        data["buttons"] = kept_btns

    # entities
    ents = data.get("entities") or []
    kept_ents = []
    for e in ents:
        if not isinstance(e, dict):
            continue
        ev = _ev_quote(e.get("evidence"))
        if _evidence_grounded(ev, original_norm, original_tokens):
            kept_ents.append(e)
        else:
            dropped["entities"].append(e.get("name") or "?")
    data["entities"] = kept_ents

    # rules
    rules = data.get("rules") or []
    kept_rules = []
    for r in rules:
        if not isinstance(r, dict):
            continue
        ev = _ev_quote(r.get("evidence"))
        if _evidence_grounded(ev, original_norm, original_tokens):
            kept_rules.append(r)
        else:
            dropped["rules"].append(r.get("condition") or r.get("name") or "?")
    data["rules"] = kept_rules

    return data, dropped


# ─────────────────────────── main entry ──────────────────────────────────

def translate_rich_spec(user_text: str, *, timeout: int | None = None) -> TranslatorV2Result:
    """
    Multi-pass AI translation: user text → RichSpec.

    Pass 1: Extraction (flat spec)
    Pass 2: Fidelity audit (correct against original)
    Pass 3: Deep inference (enrich commands with kind/fields/post_action/flow)
    Pass 4: Evidence grounding (drop untraceable items)
    """
    text = (user_text or "").strip()
    if not text:
        return TranslatorV2Result(ok=False, error="empty")
    if not _enabled():
        return TranslatorV2Result(ok=False, error="disabled")

    timeout = timeout if timeout is not None else int(
        os.environ.get("SPEC_TRANSLATOR_TIMEOUT", "90")
    )
    forced = (os.environ.get("SPEC_TRANSLATOR_MODEL") or "").strip()
    candidates = (forced,) if forced else _MODEL_CANDIDATES
    retries_max = _max_retries()

    t0 = time.perf_counter()
    last_err = ""
    try:
        from g4f.client import Client
        client = Client()
    except Exception as e:
        return TranslatorV2Result(ok=False, error=f"g4f_import:{e}")

    for model in candidates:
        if (time.perf_counter() - t0) > timeout:
            last_err = "timeout"
            break
        retries_used = 0
        passes_done = 0
        try:
            # ── PASS 1: Extraction ──
            data = _call_for_json(client, model, _EXTRACT_SYSTEM, text)
            if data is None:
                # retry parse failures
                while retries_used < retries_max and (time.perf_counter() - t0) < timeout:
                    retries_used += 1
                    data = _call_for_json(
                        client, model, _EXTRACT_SYSTEM, text,
                        retry_errors="invalid JSON or not an object — return pure JSON only",
                    )
                    if data is not None:
                        break
                if data is None:
                    last_err = f"bad_json:{model}"
                    continue
            passes_done = 1

            # If empty commands on rich text, one retry
            if not data.get("commands") and len(text) >= 80 and retries_used < retries_max:
                retries_used += 1
                data2 = _call_for_json(
                    client, model, _EXTRACT_SYSTEM, text,
                    retry_errors=(
                        "commands array is empty but user text is detailed. "
                        "Extract all mentioned functions into commands[]."
                    ),
                )
                if data2 and data2.get("commands"):
                    data = data2
            passes_done = 1

            # ── PASS 2: Fidelity audit ──
            if _repair_enabled() and (time.perf_counter() - t0) < timeout - 8:
                try:
                    payload = json.dumps(data, ensure_ascii=False)[:8000]
                    audited = _call_for_json(
                        client, model, _AUDIT_SYSTEM,
                        f"Original text:\n{text[:5000]}\n\nCurrent JSON:\n{payload}\n\nReturn ONLY corrected JSON.",
                    )
                    if audited and audited.get("commands"):
                        data = audited
                        passes_done = 2
                except Exception as aud_e:
                    logger.warning("fidelity audit skipped: %s", aud_e)

            # ── PASS 3: Deep inference ──
            if _infer_enabled() and (time.perf_counter() - t0) < timeout - 6:
                try:
                    payload = json.dumps(data, ensure_ascii=False)[:8000]
                    inferred = _call_for_json(
                        client, model, _INFER_SYSTEM,
                        f"Enrich this spec JSON. For each command add kind, entity, collects_fields, post_action, reply_text, flow_steps. Ensure entity fields are typed.\n\n{payload}",
                    )
                    if inferred and inferred.get("commands"):
                        data = inferred
                        passes_done = 3
                except Exception as inf_e:
                    logger.warning("deep inference skipped: %s", inf_e)

            # ── PASS 4: Evidence grounding ──
            grounded, dropped = _ground_spec(data, text)
            passes_done = 4

            # ── Parse into RichSpec ──
            try:
                spec = rich_spec_from_dict(grounded)
            except Exception as spec_e:
                last_err = f"richspec_parse:{type(spec_e).__name__}:{spec_e}"
                logger.warning("richspec parse failed: %s", last_err)
                continue

            val = validate_rich_spec(spec)
            if not val.ok:
                last_err = f"validation:{';'.join(val.errors)}"
                logger.warning("richspec validation failed: %s", last_err)
                continue

            elapsed = (time.perf_counter() - t0) * 1000
            logger.info(
                "spec_translator_v2 ok model=%s passes=%d cmds=%d ents=%d ms=%.0f",
                model, passes_done, len(spec.commands), len(spec.entities), elapsed,
            )
            return TranslatorV2Result(
                ok=True,
                rich_spec=spec,
                raw_json=grounded,
                model_used=model,
                elapsed_ms=round(elapsed, 1),
                needs_clarification=bool(grounded.get("needs_clarification")),
                clarification_questions=list(grounded.get("clarification_questions") or []),
                passes_done=passes_done,
                dropped=dropped,
                validation_warnings=val.warnings,
                retries=retries_used,
            )
        except Exception as e:
            last_err = f"{model}:{type(e).__name__}:{e}"
            logger.warning("spec_translator_v2 failed %s", last_err)
            continue

    elapsed = (time.perf_counter() - t0) * 1000
    return TranslatorV2Result(
        ok=False,
        error=last_err or "all_models_failed",
        elapsed_ms=round(elapsed, 1),
    )


def prepare_rich_spec(user_text: str) -> tuple[RichSpec | None, TranslatorV2Result]:
    """
    Entry point: translate user text into a RichSpec.
    Returns (rich_spec_or_None, result).
    If the translator is disabled or fails, rich_spec is None.
    """
    original = user_text or ""
    if not _enabled():
        return None, TranslatorV2Result(ok=False, error="disabled")
    result = translate_rich_spec(original)
    if result.ok and result.rich_spec is not None:
        return result.rich_spec, result
    return None, result
