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

_EXTRACT_SYSTEM = """You are a STRICT Spec Translator for Telegram bots. You output ONLY valid JSON.

═══════════════════════════════════════════════════════════════
ABSOLUTE CONSTRAINTS (NEVER VIOLATE):
═══════════════════════════════════════════════════════════════
1. You ONLY understand and translate. You NEVER write any code (no Python, no
   JavaScript, no SQL, no shell). You output a JSON SPEC only.
2. The user's text is the ONLY source of truth.
3. You MUST NOT invent, translate, rename, or "improve" any name the user wrote.
   - If the user wrote Arabic words like "اسم الكتاب", the field name MUST be
     a snake_case transliteration of EXACTLY those Arabic words
     (e.g. "اسم_الكتاب"), NEVER an English translation like "title".
   - If the user wrote "اسم المؤلف", the field name is "اسم_المؤلف",
     NEVER "author".
   - NEVER substitute English translations for the user's own words.
4. evidence.quote MUST be a VERBATIM (exact character-for-character) substring
   copied directly from the user's original text. Do NOT paraphrase, do NOT
   translate, do NOT summarize the quote. Copy the exact span of words.
5. Do NOT invent features, commands, fields, entities, or buttons the user did
   not mention or clearly imply.
6. Extract ALL functions the user mentioned (lists, "and", "فيه X و Y",
   "زرار X و زرار Y").
7. Create a button in buttons[] for EVERY command the user mentions as a
   button ("زرار", "button", "زر"). Each button's target_command must match
   a command name. If the user says "زرار X", create BOTH a command AND a button.

═══════════════════════════════════════════════════════════════
OUTPUT RULES:
═══════════════════════════════════════════════════════════════
- Reply with a single JSON object. Nothing else.
- No markdown. No code fences. No ```json. No explanations. No greetings.
- First character must be { and last character must be }.
- Use double quotes for all keys and string values (strict JSON).

═══════════════════════════════════════════════════════════════
SCHEMA (output exactly this shape):
═══════════════════════════════════════════════════════════════
{
  "bot_name": "",
  "bot_kind": "custom",
  "description": "",
  "language": "ar",
  "commands": [
    {
      "name": "add_book",
      "description": "اضافة كتاب",
      "admin_only": false,
      "evidence": {"quote": "اضافة كتاب", "confidence": 0.9}
    }
  ],
  "buttons": [
    {"label": "اضافة كتاب", "callback_id": "add_book", "target_command": "add_book", "evidence": {"quote": "اضافة كتاب"}}
  ],
  "entities": [
    {"name": "Book", "fields": [{"name": "اسم_الكتاب", "field_type": "str"}, {"name": "اسم_المؤلف", "field_type": "str"}, {"name": "isbn", "field_type": "str"}], "evidence": {"quote": "اسم الكتاب واسم المؤلف ورقم ISBN"}}
  ],
  "rules": [
    {"condition": "if registered then save", "effect": "save record", "evidence": {"quote": "يحفظ"}}
  ],
  "tech": {"database": "sqlite", "payments": false, "admin_panel": false, "notifications": false},
  "needs_clarification": false,
  "clarification_questions": []
}

═══════════════════════════════════════════════════════════════
FIELD RULES:
═══════════════════════════════════════════════════════════════
- commands[].name: a SHORT Latin slug [a-z0-9_] transliterated from the user's
  words (e.g. "اضافة كتاب" → "add_book"). Never start/help.
- commands[].description: the user's OWN words (Arabic), verbatim or
  near-verbatim.
- entities[].name: a SHORT PascalCase Latin slug (e.g. "Book", "Patient",
  "Product"). This is a class label, NOT a translation of field content.
- entities[].fields[].name: ⚠️ CRITICAL. Use a snake_case transliteration of
  the EXACT Arabic words the user wrote. The user wrote "اسم الكتاب" → field
  name is "اسم_الكتاب". The user wrote "رقم ISBN" → field name is "isbn"
  (already Latin). The user wrote "السعر" → field name is "السعر". NEVER
  translate to English. NEVER invent fields the user did not mention.
- entities[].fields[].field_type: one of str, int, bool, float, list.
- evidence.quote: a VERBATIM phrase copied character-for-character from the
  user text. This is how the system verifies you didn't hallucinate.
- If the user message is too vague: needs_clarification=true with 1-3
  questions in the user's language.
"""

_AUDIT_SYSTEM = """You are a STRICT fidelity auditor for bot specs.

Given the original user text and a JSON spec, output ONLY a corrected JSON
object (same schema as input).

═══════════════════════════════════════════════════════════════
ABSOLUTE RULES:
═══════════════════════════════════════════════════════════════
1. You ONLY audit and correct the JSON. You NEVER write any code.
2. Add commands/entities/fields that are clearly present in the user text but
   missing in the JSON.
3. Ensure every "زرار" / "button" / "زر" the user mentioned has BOTH a command
   AND a button in buttons[] with target_command matching the command name.
4. Remove items with NO support in the user text.
5. ⚠️ FIELD NAMES: Verify every entities[].fields[].name is a snake_case
   transliteration of the EXACT Arabic words the user wrote. If you find an
   English translation (e.g. "title" instead of "اسم_الكتاب"), FIX IT back to
   the Arabic transliteration. The user's own words are sacred.
6. ⚠️ EVIDENCE: Improve every evidence.quote to be a VERBATIM substring copied
   character-for-character from the user text. No paraphrasing, no translation.
7. No markdown, no prose, no code fences. First char { last char }.
"""

_INFER_SYSTEM = """You are a STRICT deep inference engine for Telegram bot specs.

You ONLY enrich the JSON with behavioral semantics. You NEVER write any code.
Given a JSON spec, enrich EVERY command with its behavioral semantics. Output
ONLY JSON (same overall shape, but commands are deeper).

═══════════════════════════════════════════════════════════════════════════════
ABSOLUTE RULES:
═══════════════════════════════════════════════════════════════════════════════
1. You NEVER write code. You ONLY add semantic labels to existing JSON.
2. Do NOT invent new commands — only enrich existing ones. You MAY add entities
   (database tables) the user clearly described if they are missing.
3. ⚠️ FIELD NAMES: When building collects_fields and flow_steps[].key, you MUST
   reuse the EXACT field names already present in entities[].fields[].name.
   Do NOT translate them to English. If the entity has a field "اسم_الكتاب",
   then flow_steps[].key MUST be "اسم_الكتاب", NOT "title".
4. ⚠️ flow_steps[].prompt: write the prompt in the USER's language (Arabic),
   asking for the field using the user's own words. E.g. for field "اسم_الكتاب"
   the prompt is "أدخل اسم الكتاب:".

For EACH command add/complete these fields:
- "kind": one of: start, help, collect, lookup, list, stats, broadcast, action,
  info, navigate, custom
    * collect  = gathers several fields from the user (a wizard / form). If the
      user said a button "يدخل" (enters) several pieces of data → kind=collect.
    * lookup   = queries one record by id/key/name
    * list     = lists / browses multiple records ("كل الكتب", "عرض المنتجات")
    * stats    = aggregate numbers / dashboard ("إحصائيات", "مبيعاتي", "stats")
    * broadcast= admin sends to many users ("broadcast", "إذاعة")
    * action   = performs a side-effect (send, notify, toggle, delete, cancel,
                 ban, mute, kick, warn, pin, lock, unlock, set rules/welcome)
    * info     = static informational reply (rules, admins, staff, id, info)
    * navigate = opens a menu / keyboard (panel, settings menu)
    * custom   = ONLY use this if the command truly fits none of the above

- "action_type": CRITICAL for action/info/stats commands. Set a semantic
  identifier that tells the engine WHAT Telegram API operation to perform.
  Use these exact values when applicable:
    * Member moderation: ban_user, unban_user, mute_user, unmute_user,
      kick_user, warn_user, unwarn_user, show_warnings, clear_warnings
    * Message operations: pin_message, unpin_message, purge_messages,
      clean_messages, delete_message
    * Group settings: toggle_setting (for lock/unlock/antilink/antispam/
      antiflood/antibot/captcha/maintenance), show_locks, set_slowmode,
      set_welcome, set_goodbye, set_rules, show_welcome, show_goodbye,
      show_rules
    * Filters/Lists: add_filter, remove_filter, show_filters,
      add_blacklist, remove_blacklist, show_blacklist,
      add_whitelist, remove_whitelist, show_whitelist
    * Admin/Info: show_panel, show_admins, show_staff, show_id, show_info,
      report_user, set_language, show_settings
    * Owner/System: broadcast_message, show_stats, show_groups, show_users,
      backup_data, restore_data, show_logs, restart_bot
  If the command does not match any of these, leave action_type empty.

- "target_args": describe what arguments the command takes, in natural language.
  Examples: "user_id or reply to a message", "duration + reason",
  "on/off toggle", "the text to broadcast", "none".

- "entity": the entity name this command operates on (empty if none)
- "collects_fields": list of field keys the command gathers from the user
  (MUST match entity field names exactly). Empty if none.
- "post_action": one of: store, confirm, notify, compute, none
    * store   = persist collected data into the entity store
    * confirm = echo back the collected data
    * notify  = send a notification
    * compute = run a calculation and reply
- "reply_text": a short reply message in the USER's language (for
  info/start/help/action commands)
- "flow_steps": for collect commands, an ordered list of
  {"key": <exact field name>, "prompt": <Arabic prompt>, "action": "ask"}.
  One step per field in collects_fields.

⚠️ CLASSIFICATION IS CRITICAL. Defaulting everything to "custom" is a FAILURE.
  - If a command's description says the user "enters/inputs/fills" multiple
    fields, it is "collect" — NOT "custom".
  - If the description says "show all / list / كل", it is "list".
  - If it says "stats / إحصائيات", it is "stats".
  - If it is a moderation verb (ban, mute, kick, warn, pin, delete, lock,
    unlock, purge), it is "action" with the matching action_type.
  - If it shows static info (rules, admins, staff, id, info), it is "info"
    with the matching action_type (show_rules, show_admins, etc.).
  - If it collects text to save (setrules, setwelcome, setgoodbye), it is
    "collect" with flow_steps and action_type set_rules/set_welcome/set_goodbye.

⚠️ ENTITIES: If the user's text describes database tables or data structures
  (e.g. "users, groups, admins, warnings, bans, mutes, filters, rules, logs"),
  make sure entities[] contains one entry per table with appropriate fields.
  If entities are missing, ADD them based on what the user described. Each
  entity name should be PascalCase (User, Group, Admin, Warning, Ban, Mute,
  Filter, Rule, Log, GroupSetting, Statistic). Include sensible fields:
    * User: user_id(int), username(str), first_name(str), joined_at(str)
    * Group: group_id(int), title(str), members_count(int)
    * Admin: user_id(int), group_id(int), role(str)
    * GroupSetting: group_id(int), setting_key(str), setting_value(str)
    * Warning: user_id(int), group_id(int), reason(str), count(int)
    * Ban: user_id(int), group_id(int), reason(str)
    * Mute: user_id(int), group_id(int), until(str), reason(str)
    * Filter: group_id(int), keyword(str), response(str)
    * Rule: group_id(int), rules_text(str)
    * Log: group_id(int), action(str), admin_id(int), target_id(int), at(str)
    * Statistic: group_id(int), metric(str), value(int)
  Only add entities the user actually mentioned or clearly implied.

No markdown, no prose. First char { last char }.
"""

_RETRY_SYSTEM = """You previously returned invalid JSON. Output ONLY one corrected JSON object.
No markdown, no fences, no prose. First char { last char }. Same schema. Fix the errors listed.
Remember: NEVER translate Arabic field names to English. NEVER write code. evidence.quote must be verbatim from the user text."""


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


# ── Arabic-aware token matching for field/entity name grounding ──

# Common Arabic-Latin transliteration pairs for when the user wrote Latin words
# but we need to check if a Latin slug maps back to Arabic words.
_LATIN_AR_HINTS = {
    # (latin slug token) : set of arabic words that justify it
    "isbn": {"isbn", "رقم"},
    "id": {"id", "معرف", "رقم"},
    "phone": {"phone", "هاتف", "تليفون", "رقم"},
    "tel": {"tel", "هاتف", "تليفون"},
    "email": {"email", "بريد", "ايميل"},
    "name": {"name", "اسم", "الاسم"},
    "title": {"title", "اسم", "عنوان"},
    "author": {"author", "مؤلف", "اسم"},
    "book": {"book", "كتاب"},
    "product": {"product", "منتج"},
    "price": {"price", "سعر", "السعر"},
    "qty": {"qty", "quantity", "كمية"},
    "quantity": {"quantity", "qty", "كمية"},
    "order": {"order", "طلب", "اوردر"},
    "patient": {"patient", "مريض"},
    "date": {"date", "تاريخ"},
    "time": {"time", "وقت", "ساعة"},
    "customer": {"customer", "عميل", "زبون"},
    "client": {"client", "عميل", "زبون"},
    "count": {"count", "عدد"},
    "total": {"total", "اجمالي", "مجموع"},
    "city": {"city", "مدينة"},
    "address": {"address", "عنوان", "العنوان"},
    # ── Group management terms ──
    "user": {"user", "مستخدم", "الاعضاء", "اعضاء", "عضو", "المستخدمين", "المستخدم"},
    "users": {"users", "مستخدم", "الاعضاء", "اعضاء", "عضو", "المستخدمين"},
    "group": {"group", "مجموعة", "مجموعات", "المجموعة", "جروب", "الجروبات", "الجروب"},
    "groups": {"groups", "مجموعة", "مجموعات", "المجموعة", "جروب", "الجروبات"},
    "admin": {"admin", "مشرف", "المشرفين", "المشرف", "ادمن", "الادمن", "الادمنية"},
    "admins": {"admins", "مشرف", "المشرفين", "المشرف", "ادمن", "الادمنية"},
    "staff": {"staff", "طاقم", "المشرفين", "الادمنية", "الطاقم"},
    "warning": {"warning", "تحذير", "التحذيرات", "تحذيرات", "انذار"},
    "warnings": {"warnings", "تحذير", "التحذيرات", "تحذيرات", "انذار"},
    "ban": {"ban", "حظر", "بان", "طرد", "منع", "الحظر"},
    "bans": {"bans", "حظر", "الباند", "المحظورين", "الحظر"},
    "mute": {"mute", "كتم", "ميوت", "اكتم", "كتمة"},
    "mutes": {"mutes", "كتم", "المكتومين", "ميوت"},
    "kick": {"kick", "طرد", "كيك", "اطرد"},
    "filter": {"filter", "فلتر", "فلاتر", "الفلتر", "ردود", "رد", "ردود_تلقائية"},
    "filters": {"filters", "فلتر", "فلاتر", "الفلاتر", "ردود", "رد"},
    "rule": {"rule", "قواعد", "قاعدة", "القواعد", "القوانين", "قانون"},
    "rules": {"rules", "قواعد", "قاعدة", "القواعد", "القوانين", "قانون"},
    "log": {"log", "سجل", "سجلات", "السجل", "السجلات", "log", "logs"},
    "logs": {"logs", "سجل", "سجلات", "السجل", "السجلات"},
    "statistic": {"statistic", "احصائيات", "احصائية", "الاحصائيات", "احصاء"},
    "statistics": {"statistics", "احصائيات", "الاحصائيات", "احصاء"},
    "setting": {"setting", "اعداد", "اعدادات", "الاعدادات", "ضبط"},
    "settings": {"settings", "اعداد", "اعدادات", "الاعدادات", "ضبط"},
    "welcome": {"welcome", "ترحيب", "الترحيب", "ترحيبية"},
    "goodbye": {"goodbye", "وداع", "توديع", "الوداع"},
    "captcha": {"captcha", "كابتشا", "تحقق"},
    "antilink": {"antilink", "روابط", "منع_الروابط", "الروابط"},
    "antispam": {"antispam", "سبام", "spam", "منع_السبام"},
    "antiflood": {"antiflood", "فلوود", "flood", "سبام"},
    "antibot": {"antibot", "بوتات", "ال بوتات", "منع_البوتات"},
    "blacklist": {"blacklist", "قائمة_سوداء", "القائمة_السوداء", "حظر"},
    "whitelist": {"whitelist", "قائمة_بيضاء", "القائمة_البيضاء", "استثناء"},
    "broadcast": {"broadcast", "اذاعة", "إذاعة", "بث"},
    "panel": {"panel", "لوحة", "اللوحة", "التحكم"},
    "report": {"report", "تبليغ", "بلاغ", "شكوى", "تبليغات"},
    "language": {"language", "لغة", "اللغة"},
}

# Arabic field name -> set of arabic words that justify it (for arabic slugs)
def _arabic_slug_to_words(slug: str) -> set[str]:
    """Split an arabic snake_case slug into its component words."""
    if not slug:
        return set()
    parts = re.split(r"[_\s]+", slug)
    out = set()
    for p in parts:
        p = p.strip()
        if p:
            out.add(p)
    return out


def _name_grounded(
    name: str,
    original_norm: str,
    original_tokens: set[str],
    *,
    is_field: bool = False,
) -> bool:
    """
    Decide whether a field name or entity name is traceable to the original
    user text. This is STRICTER than evidence grounding: it checks the actual
    data name, not just the evidence quote.

    A name is grounded if:
      1. It (normalized) appears as a substring of the original — covers Arabic
         slugs like 'اسم_الكتاب' (after stripping underscores 'اسم الكتاب').
      2. Its component tokens all appear in the original tokens — covers
         multi-word Arabic slugs.
      3. It's a Latin slug and each token maps (via _LATIN_AR_HINTS) to an
         Arabic word that IS in the original — covers 'isbn', 'phone', etc.
      4. It's a short Latin slug (≤8 chars) and at least one hint word is in
         the original.
      5. It's a pure-Latin entity class label (Book, Patient, Product) and the
         corresponding Arabic word appears in the original (كتاب, مريض, منتج).
    """
    name = (name or "").strip()
    if not name:
        return False
    # Normalize: lowercase, strip arabic diacritics, remove underscores for
    # substring matching
    nn = _normalize_text(name).replace("_", " ").strip()
    nn_compact = nn.replace(" ", "")
    on_compact = original_norm.replace(" ", "")

    # 1. substring (compact, ignores spaces) — strong evidence
    if nn and nn in original_norm:
        return True
    if nn_compact and len(nn_compact) >= 3 and nn_compact in on_compact:
        return True

    # 2. all component tokens in original
    tokens = set(nn.split()) if nn else set()
    if tokens:
        # For arabic slugs, require a meaningful overlap
        overlap = tokens & original_tokens
        # If every token is in the original → grounded
        if overlap and len(overlap) >= max(1, (len(tokens) * 3) // 4):
            return True
        # If at least half the tokens match → grounded
        if len(overlap) >= max(1, len(tokens) // 2):
            return True

    # 3. Latin slug → check hint map
    is_latin = bool(re.match(r"^[a-z0-9_]+$", name))
    if is_latin:
        lat_tokens = [t for t in name.split("_") if t]
        matched_any = False
        for lt in lat_tokens:
            hints = _LATIN_AR_HINTS.get(lt.lower())
            if hints:
                if hints & original_tokens:
                    matched_any = True
                    break
        if matched_any:
            return True
        # 4. short slug, single hint word present
        if len(name) <= 12 and lat_tokens:
            for lt in lat_tokens:
                hints = _LATIN_AR_HINTS.get(lt.lower())
                if hints and (hints & original_tokens):
                    return True

    # 5. entity class label: Book → كتاب, Patient → مريض, Product → منتج
    if not is_field and is_latin:
        label_low = name.lower()
        hints = _LATIN_AR_HINTS.get(label_low)
        if hints and (hints & original_tokens):
            return True

    return False


def _ground_spec(data: dict[str, Any], original: str) -> tuple[dict[str, Any], dict[str, list[str]]]:
    """
    Drop commands/buttons/entities/rules whose evidence is not traceable to the
    original user text. Returns (grounded_data, dropped_report).
    Never drops /start or /help (structural minima).

    ENHANCED (v2.1): Also validates field names, entity names, and flow_step
    keys against the original text using _name_grounded(). Hallucinated
    English-translated field names are dropped. Flow_step keys that don't
    match any grounded entity field are dropped/reset.
    """
    original_norm = _normalize_text(original)
    original_tokens = _token_set(original)
    dropped: dict[str, list[str]] = {
        "commands": [], "buttons": [], "entities": [], "rules": [],
        "fields": [], "flow_steps": [],
    }

    def _ev_quote(ev: Any) -> str:
        if isinstance(ev, dict):
            return ev.get("quote", "") or ev.get("text", "") or ""
        if isinstance(ev, str):
            return ev
        return ""

    # commands: evidence grounding (OR description grounding)
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
        desc = c.get("description") or ""
        if (_evidence_grounded(ev, original_norm, original_tokens)
                or _evidence_grounded(desc, original_norm, original_tokens)):
            kept_cmds.append(c)
        else:
            dropped["commands"].append(name or "?")
    data["commands"] = kept_cmds

    # buttons: evidence grounding (OR label grounding)
    btns = data.get("buttons") or []
    kept_btns = []
    for b in btns:
        if not isinstance(b, dict):
            continue
        ev = _ev_quote(b.get("evidence"))
        label = b.get("label") or ""
        if (_evidence_grounded(ev, original_norm, original_tokens)
                or _evidence_grounded(label, original_norm, original_tokens)):
            kept_btns.append(b)
        else:
            dropped["buttons"].append(b.get("label") or b.get("callback_id") or "?")
    data["buttons"] = kept_btns

    # Button-completeness safety net
    has_buttons_in_text = any(
        kw in original_norm for kw in ("زرار", "زر ", "زر.", "زرار", "button", "buttons", "زرّار", "زر")
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
            label = c.get("description") or cname
            kept_btns.append({
                "label": label,
                "callback_id": cname,
                "target_command": cname,
                "evidence": c.get("evidence") or {"quote": label},
            })
        data["buttons"] = kept_btns

    # entities: evidence grounding + FIELD NAME grounding
    ents = data.get("entities") or []
    kept_ents = []
    for e in ents:
        if not isinstance(e, dict):
            continue
        ev = _ev_quote(e.get("evidence"))
        ent_name = e.get("name") or ""
        if not (_evidence_grounded(ev, original_norm, original_tokens)
                or _name_grounded(ent_name, original_norm, original_tokens)):
            dropped["entities"].append(ent_name or "?")
            continue
        # Validate each field name against the original text
        fields = e.get("fields") or []
        kept_fields = []
        for fld in fields:
            if not isinstance(fld, dict):
                continue
            fname = fld.get("name") or ""
            if not fname:
                continue
            if _name_grounded(fname, original_norm, original_tokens, is_field=True):
                kept_fields.append(fld)
            else:
                fev = _ev_quote(fld.get("evidence"))
                if fev and _evidence_grounded(fev, original_norm, original_tokens):
                    kept_fields.append(fld)
                else:
                    dropped["fields"].append(f"{ent_name}.{fname}")
        e["fields"] = kept_fields
        kept_ents.append(e)
    data["entities"] = kept_ents

    # Build a set of all grounded field names (for flow_step validation)
    grounded_field_names: set[str] = set()
    for e in kept_ents:
        for fld in (e.get("fields") or []):
            if isinstance(fld, dict):
                fn = (fld.get("name") or "").strip()
                if fn:
                    grounded_field_names.add(fn)
                    grounded_field_names.add(fn.lower())

    # commands (again): validate flow_steps + collects_fields
    for c in kept_cmds:
        if not isinstance(c, dict):
            continue
        cfields = c.get("collects_fields") or []
        if cfields:
            kept_cf = []
            for cf in cfields:
                cfn = (cf or "").strip()
                if not cfn:
                    continue
                if (cfn in grounded_field_names
                        or cfn.lower() in grounded_field_names
                        or _name_grounded(cfn, original_norm, original_tokens, is_field=True)):
                    kept_cf.append(cfn)
                else:
                    dropped["fields"].append(f"{c.get('name','')}.collects:{cfn}")
            c["collects_fields"] = kept_cf

        fsteps = c.get("flow_steps") or []
        if fsteps:
            kept_fs = []
            for fs in fsteps:
                if not isinstance(fs, dict):
                    continue
                fkey = (fs.get("key") or "").strip()
                if not fkey:
                    continue
                if (fkey in grounded_field_names
                        or fkey.lower() in grounded_field_names
                        or _name_grounded(fkey, original_norm, original_tokens, is_field=True)):
                    kept_fs.append(fs)
                else:
                    dropped["flow_steps"].append(f"{c.get('name','')}.flow:{fkey}")
            c["flow_steps"] = kept_fs

            # If we dropped all flow_steps but the command is collect, rebuild
            # them from collects_fields (which are already validated)
            if not kept_fs and (c.get("kind") == "collect"):
                cf = c.get("collects_fields") or []
                rebuilt = []
                for fk in cf:
                    rebuilt.append({
                        "key": fk,
                        "prompt": f"أدخل {fk}:",
                        "action": "ask",
                    })
                c["flow_steps"] = rebuilt

    data["commands"] = kept_cmds

    # rules: evidence grounding (OR condition grounding)
    rules = data.get("rules") or []
    kept_rules = []
    for r in rules:
        if not isinstance(r, dict):
            continue
        ev = _ev_quote(r.get("evidence"))
        cond = r.get("condition") or ""
        if (_evidence_grounded(ev, original_norm, original_tokens)
                or _evidence_grounded(cond, original_norm, original_tokens)):
            kept_rules.append(r)
        else:
            dropped["rules"].append(r.get("condition") or r.get("name") or "?")
    data["rules"] = kept_rules

    return data, dropped
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
                        (f"Enrich this spec JSON. For each command add kind, entity, "
                         f"collects_fields, post_action, reply_text, flow_steps. "
                         f"Ensure entity fields are typed. "
                         f"CRITICAL: kind must NOT be 'custom' for commands that collect "
                         f"data (use 'collect'), list records (use 'list'), or show "
                         f"stats (use 'stats'). flow_steps[].key MUST reuse the exact "
                         f"field names from entities[].fields[].name.\n\n"
                         f"Original user text for reference:\n{text[:3000]}\n\n"
                         f"Spec to enrich:\n{payload}"),
                    )
                    if inferred and inferred.get("commands"):
                        data = inferred
                        passes_done = 3
                except Exception as inf_e:
                    logger.warning("deep inference skipped: %s", inf_e)

            # ── PASS 3b: CUSTOM re-inference safety net ──
            # If after inference, commands that clearly collect data are still
            # 'custom' with no collects_fields, do a targeted re-inference.
            if _infer_enabled() and (time.perf_counter() - t0) < timeout - 4:
                cmds_check = data.get("commands") or []
                needs_reinfer = False
                for c in cmds_check:
                    if not isinstance(c, dict):
                        continue
                    kind = (c.get("kind") or "").lower()
                    cf = c.get("collects_fields") or []
                    desc = (c.get("description") or "").lower()
                    # Detect collect-like commands mis-classified as custom
                    collect_hints = any(
                        kw in desc for kw in (
                            "بيدخل", "يدخل", "ادخال",
                            "تسجيل", "اضافة", "جديد",
                            "enter", "input", "add", "register", "collect",
                        )
                    )
                    if kind == "custom" and not cf and collect_hints:
                        needs_reinfer = True
                        break
                if needs_reinfer:
                    try:
                        payload = json.dumps(data, ensure_ascii=False)[:8000]
                        reinferred = _call_for_json(
                            client, model, _INFER_SYSTEM,
                            (f"Some commands were mis-classified as 'custom' but they "
                             f"clearly collect data from the user (their description "
                             f"mentions entering/adding/registering). Re-classify them "
                             f"as 'collect' with proper collects_fields and flow_steps. "
                             f"Also classify list-like commands as 'list' and stats-like "
                             f"as 'stats'. flow_steps[].key MUST reuse exact field names "
                             f"from entities[].fields[].name. NEVER translate Arabic "
                             f"field names to English.\n\n"
                             f"Original user text:\n{text[:3000]}\n\n"
                             f"Spec to fix:\n{payload}"),
                        )
                        if reinferred and reinferred.get("commands"):
                            # Only accept if it improved classification
                            old_custom = sum(
                                1 for c in (data.get("commands") or [])
                                if isinstance(c, dict) and (c.get("kind") or "").lower() == "custom"
                            )
                            new_custom = sum(
                                1 for c in (reinferred.get("commands") or [])
                                if isinstance(c, dict) and (c.get("kind") or "").lower() == "custom"
                            )
                            if new_custom < old_custom:
                                data = reinferred
                                passes_done = 3
                    except Exception as ri_e:
                        logger.warning("custom re-inference skipped: %s", ri_e)

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
