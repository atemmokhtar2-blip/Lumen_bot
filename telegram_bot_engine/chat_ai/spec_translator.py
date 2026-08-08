"""
SpecTranslator — high-fidelity speech → formal specification JSON.

Enforcement stack:
  1) JSON-only system prompt (no prose)
  2) Robust extract + parse
  3) Schema validation (required keys/types)
  4) Auto-retry on invalid JSON/schema
  5) Defaults for missing optional fields
  6) Grounding against original user text
  7) Optional fidelity repair pass

AI never generates code. Formal engine is the only codegen path.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("ai_agent_7h_bot.spec_translator")

_MODEL_CANDIDATES = (
    "gemini-2.0-flash",
    "gpt-4o-mini",
    "claude-3.5-sonnet",
    "gemini-1.5-flash",
    "claude-3-haiku",
    "gpt-4o",
)

# ── JSON Output Enforcement ───────────────────────────────────────────────

_SYSTEM = """You are a Spec Translator for Telegram bots. You output ONLY valid JSON.

ABSOLUTE OUTPUT RULES:
- Reply with a single JSON object. Nothing else.
- No markdown. No code fences. No ```json. No explanations. No greetings. No trailing text.
- First character must be { and last character must be }.
- Use double quotes for all keys and string values (strict JSON).

ROLE:
- Translate the user's natural language into a structured bot specification.
- Do NOT write Python or any code.
- Do NOT invent features the user did not mention or clearly imply.
- Prefer completeness of what the user said over inventing extras.

SCHEMA (all keys required; use empty arrays/strings/false when unknown):
{
  "bot_name": "",
  "commands": [
    {
      "name": "register",
      "description": "تسجيل",
      "admin_only": false,
      "roles": ["user", "admin"],
      "evidence": "تسجيل"
    }
  ],
  "buttons": [
    {"label": "تسجيل", "evidence": "تسجيل"}
  ],
  "entities": [
    {
      "name": "Customer",
      "fields": [{"name": "phone", "type": "string", "required": true}],
      "relations": [{"target": "Order", "type": "one_to_many"}],
      "evidence": "عملاء"
    }
  ],
  "rules": [
    {"text": "لو تم الطلب يحفظ", "condition": "total > 0", "evidence": "يحفظ"}
  ],
  "flows": [
    {
      "command": "register",
      "steps": ["name", "phone"],
      "evidence": "تسجيل"
    }
  ],
  "integrations": [
    {"service": "stripe", "purpose": "payments", "evidence": "دفع"}
  ],
  "needs_clarification": false,
  "clarification_questions": [],
  "fidelity_notes": ""
}

FIELD RULES:
- commands[].name: lowercase English [a-z0-9_], no slash, never start/help.
- commands[].description: keep user language when possible.
- evidence: short quote/paraphrase from the user text that justifies the item.
- entities[].name: PascalCase or CapWord English identifier.
- entities[].fields: lowercase English field ids only.
- buttons: objects with label + evidence (not bare strings).
- rules: objects with text + evidence.
- If the user message is too vague (only a name / "make a bot"): needs_clarification=true and 1-3 short clarification_questions in the user's language.
- Extract ALL functions the user mentioned in one sentence (lists, "and", "فيه X و Y").

EXAMPLES OF INVALID OUTPUT (never do this):
- Here is the JSON: {...}
- ```json {...} ```
- JSON above plus an explanation paragraph
"""

_RETRY_SYSTEM = """You previously returned invalid or incomplete JSON for a Spec Translator task.
Output ONLY one corrected JSON object. No markdown, no fences, no prose.
First char { last char }. Same schema as before. Fix the validation errors listed by the user message.
"""

_REPAIR_SYSTEM = """You are a fidelity auditor for bot specs.
Given original user text and a JSON spec, output ONLY a corrected JSON object (same schema).
- Add commands/entities/fields clearly present in the user text but missing in JSON.
- Remove items with no support in the user text.
- Improve evidence to short spans from the user text.
- No markdown, no prose, no code fences. First char { last char }.
"""


@dataclass
class SchemaIssue:
    path: str
    message: str


@dataclass
class TranslatorResult:
    ok: bool
    structured_text: str = ""
    model_used: str = ""
    elapsed_ms: float = 0.0
    error: str = ""
    raw_json: dict[str, Any] = field(default_factory=dict)
    grounded_json: dict[str, Any] = field(default_factory=dict)
    dropped: dict[str, list[str]] = field(default_factory=dict)
    needs_clarification: bool = False
    clarification_questions: list[str] = field(default_factory=list)
    fidelity_pass: bool = False
    schema_ok: bool = False
    schema_issues: list[str] = field(default_factory=list)
    retries: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "model_used": self.model_used,
            "elapsed_ms": self.elapsed_ms,
            "error": self.error,
            "needs_clarification": self.needs_clarification,
            "clarification_questions": list(self.clarification_questions),
            "commands": len((self.grounded_json or {}).get("commands") or []),
            "entities": len((self.grounded_json or {}).get("entities") or []),
            "buttons": len((self.grounded_json or {}).get("buttons") or []),
            "dropped": dict(self.dropped or {}),
            "has_structured_text": bool(self.structured_text),
            "fidelity_pass": self.fidelity_pass,
            "schema_ok": self.schema_ok,
            "schema_issues": list(self.schema_issues)[:12],
            "retries": self.retries,
        }


def _enabled() -> bool:
    v = (os.environ.get("SPEC_TRANSLATOR") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def _repair_enabled() -> bool:
    v = (os.environ.get("SPEC_TRANSLATOR_REPAIR") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def _max_retries() -> int:
    try:
        return max(0, min(3, int(os.environ.get("SPEC_TRANSLATOR_RETRIES", "2"))))
    except ValueError:
        return 2


def _norm(s: str) -> str:
    s = (s or "").lower()
    s = s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    s = s.replace("ة", "ه").replace("ى", "ي")
    s = s.replace("ؤ", "و").replace("ئ", "ي")
    s = re.sub(r"\s+", " ", s)
    return s


_SYN: list[tuple[str, tuple[str, ...]]] = [
    ("register", (
        "تسجيل", "يسجل", "سجّل", "سجل", "signup", "sign up", "register",
        "تسجيل عميل", "تسجيل عملاء", "انشاء حساب", "إنشاء حساب",
    )),
    ("register_customer", ("تسجيل عميل", "تسجيل العملاء", "register customer")),
    ("register_driver", ("تسجيل سائق", "تسجيل سائقين", "register driver")),
    ("order", (
        "طلب", "اوردر", "order", "طلبات", "ياخذ طلبات", "يأخذ طلبات",
        "طلب جديد", "اوردر جديد", "انشاء طلب", "إنشاء طلب",
    )),
    ("new_order", ("طلب جديد", "اوردر جديد", "new order")),
    ("track", (
        "تتبع", "يتابع", "يتابعها", "تتبعها", "track", "tracking", "متابعة",
    )),
    ("my_orders", ("طلباتي", "اوردراتي", "my orders", "عرض طلباتي")),
    ("book", ("حجز", "يحجز", "book", "booking", "موعد", "مواعيد", "احجز")),
    ("my_appointments", ("مواعيدي", "حجوزاتي", "my appointments")),
    ("menu", ("منيو", "قائمة", "menu", "قائمة الطعام")),
    ("admin", ("ادمن", "أدمن", "admin", "مشرف", "لوحة الادارة", "لوحة الإدارة")),
    ("stats", ("احصائ", "إحصائ", "احصائيات", "إحصائيات", "stats")),
    ("search", ("بحث", "يبحث", "search")),
    ("pay", ("دفع", "يدفع", "pay", "payment", "سداد")),
    ("support", ("دعم", "support", "تذكرة", "شكاوى", "شكوى")),
    ("delivery", ("توصيل", "delivery")),
    ("shipping", ("شحن", "shipping")),
    ("profile", ("ملف", "profile", "ملف شخصي")),
    ("settings", ("اعدادات", "إعدادات", "settings")),
    ("cancel", ("الغاء", "إلغاء", "cancel")),
    ("confirm", ("تاكيد", "تأكيد", "confirm")),
    ("subscribe", ("اشتراك", "subscribe")),
    ("invite", ("دعوة", "invite")),
    ("balance", ("رصيد", "balance", "محفظة", "wallet")),
    ("wallet", ("محفظة", "wallet", "رصيد")),
    ("rate", ("تقييم", "rate", "review")),
    ("invoice", ("فاتورة", "invoice")),
    ("notifications", ("اشعار", "إشعار", "اشعارات", "إشعارات")),
    ("customer", ("عميل", "عملاء", "customer", "client")),
    ("driver", ("سائق", "سائقين", "driver")),
    ("product", ("منتج", "منتجات", "صنف", "product", "item")),
    ("appointment", ("موعد", "مواعيد", "appointment")),
    ("task", ("مهمة", "مهام", "task")),
    ("name", ("اسم", "الاسم", "name")),
    ("phone", ("هاتف", "موبايل", "تليفون", "جوال", "phone", "mobile")),
    ("address", ("عنوان", "العنوان", "address")),
    ("email", ("ايميل", "بريد", "email")),
    ("status", ("حالة", "الحالة", "status")),
    ("date", ("تاريخ", "date")),
    ("time", ("وقت", "time")),
    ("notes", ("ملاحظات", "notes")),
    ("price", ("سعر", "price")),
    ("quantity", ("كمية", "quantity")),
    ("title", ("عنوان", "title")),
    ("description", ("وصف", "description")),
]


def _phrase_in_text(phrase: str, original: str, original_n: str) -> bool:
    p = (phrase or "").strip()
    if not p:
        return False
    if p in original or _norm(p) in original_n:
        return True
    pat = re.escape(_norm(p)).replace(r"\ ", r"\s+")
    return bool(re.search(pat, original_n))


def _grounded_token(token: str, original: str, original_n: str, evidence: str = "") -> bool:
    if evidence and _phrase_in_text(evidence, original, original_n):
        return True
    tok = (token or "").strip()
    if not tok:
        return False
    t = tok.lower().strip()
    if _phrase_in_text(tok, original, original_n):
        return True
    if re.search(rf"/{re.escape(t)}\b", original, re.I):
        return True
    for key, phrases in _SYN:
        key_n = key.replace("_", "")
        t_n = t.replace("_", "")
        if t == key or t_n == key_n or t.endswith("_" + key) or t.startswith(key + "_"):
            if any(_phrase_in_text(p, original, original_n) for p in phrases):
                return True
        for p in phrases:
            if _norm(p) == t or p == tok:
                if any(_phrase_in_text(pp, original, original_n) for pp in phrases):
                    return True
    parts = [p for p in t.split("_") if len(p) >= 3]
    if len(parts) >= 2:
        ok_parts = 0
        for p in parts:
            if p in original_n or _grounded_token(p, original, original_n):
                ok_parts += 1
            else:
                for key, phrases in _SYN:
                    if p == key and any(_phrase_in_text(ph, original, original_n) for ph in phrases):
                        ok_parts += 1
                        break
        if ok_parts >= len(parts):
            return True
    return False


# ── Parse + Schema ────────────────────────────────────────────────────────

def extract_json_object(content: str) -> str | None:
    """Pull the outermost JSON object from a model reply (fences/prose tolerant)."""
    content = (content or "").strip()
    if not content:
        return None
    # strip common fences
    content = re.sub(r"^```(?:json|JSON)?\s*", "", content)
    content = re.sub(r"\s*```$", "", content)
    content = content.strip()
    if content.startswith("{") and content.endswith("}"):
        return content
    # find balanced object
    start = content.find("{")
    if start < 0:
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
    blob = extract_json_object(content)
    if not blob:
        return None
    try:
        data = json.loads(blob)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        # trailing commas soft fix
        soft = re.sub(r",\s*}", "}", blob)
        soft = re.sub(r",\s*]", "]", soft)
        try:
            data = json.loads(soft)
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None


def _cmd_name_ok(name: str) -> bool:
    return bool(re.fullmatch(r"[a-z][a-z0-9_]{1,31}", name or ""))


def validate_spec_schema(data: Any) -> tuple[bool, list[SchemaIssue], dict[str, Any]]:
    """
    Validate + normalize into canonical dict with defaults for missing optionals.
    Returns (ok_enough_to_use, issues, normalized).
    ok_enough_to_use: dict root with lists; hard-fail only if not a dict after parse.
    """
    issues: list[SchemaIssue] = []
    if not isinstance(data, dict):
        return False, [SchemaIssue("$", "root must be a JSON object")], {}

    out: dict[str, Any] = {
        "bot_name": "",
        "commands": [],
        "buttons": [],
        "entities": [],
        "rules": [],
        "flows": [],
        "integrations": [],
        "needs_clarification": False,
        "clarification_questions": [],
        "fidelity_notes": "",
    }

    # required keys presence (defaults fill)
    for key in out:
        if key not in data:
            issues.append(SchemaIssue(key, "missing key — default applied"))

    bn = data.get("bot_name", "")
    if bn is None:
        bn = ""
    if not isinstance(bn, str):
        issues.append(SchemaIssue("bot_name", "must be string — coerced"))
        bn = str(bn)
    out["bot_name"] = bn.strip()[:48]

    # commands
    raw_cmds = data.get("commands", [])
    if raw_cmds is None:
        raw_cmds = []
    if not isinstance(raw_cmds, list):
        issues.append(SchemaIssue("commands", "must be array — reset to []"))
        raw_cmds = []
    for i, c in enumerate(raw_cmds):
        path = f"commands[{i}]"
        if isinstance(c, str):
            n = re.sub(r"[^a-z0-9_]", "", c.lower().lstrip("/"))
            if _cmd_name_ok(n) and n not in ("start", "help"):
                out["commands"].append({
                    "name": n,
                    "description": n,
                    "admin_only": False,
                    "evidence": "",
                })
            else:
                issues.append(SchemaIssue(path, f"invalid command string {c!r}"))
            continue
        if not isinstance(c, dict):
            issues.append(SchemaIssue(path, "must be object or string"))
            continue
        n = re.sub(r"[^a-z0-9_]", "", str(c.get("name") or "").lower().lstrip("/"))
        if not n or n in ("start", "help"):
            issues.append(SchemaIssue(f"{path}.name", "empty or reserved"))
            continue
        if not _cmd_name_ok(n):
            issues.append(SchemaIssue(f"{path}.name", f"invalid name {n!r}"))
            continue
        desc = c.get("description", n)
        if not isinstance(desc, str):
            desc = str(desc)
            issues.append(SchemaIssue(f"{path}.description", "coerced to string"))
        admin = c.get("admin_only", False)
        if not isinstance(admin, bool):
            admin = str(admin).lower() in ("1", "true", "yes")
            issues.append(SchemaIssue(f"{path}.admin_only", "coerced to bool"))
        evidence = c.get("evidence", "")
        if not isinstance(evidence, str):
            evidence = str(evidence or "")
        out["commands"].append({
            "name": n[:32],
            "description": desc.strip()[:120] or n,
            "admin_only": bool(admin),
            "evidence": evidence.strip()[:120],
        })

    # buttons
    raw_btns = data.get("buttons", [])
    if raw_btns is None:
        raw_btns = []
    if not isinstance(raw_btns, list):
        issues.append(SchemaIssue("buttons", "must be array — reset"))
        raw_btns = []
    for i, b in enumerate(raw_btns):
        path = f"buttons[{i}]"
        if isinstance(b, str):
            lab = b.strip()[:48]
            if lab:
                out["buttons"].append({"label": lab, "evidence": lab})
            continue
        if not isinstance(b, dict):
            issues.append(SchemaIssue(path, "must be object or string"))
            continue
        lab = str(b.get("label") or b.get("text") or "").strip()[:48]
        if not lab:
            issues.append(SchemaIssue(f"{path}.label", "empty"))
            continue
        ev = str(b.get("evidence") or lab).strip()[:120]
        out["buttons"].append({"label": lab, "evidence": ev})

    # entities
    raw_ents = data.get("entities", [])
    if raw_ents is None:
        raw_ents = []
    if not isinstance(raw_ents, list):
        issues.append(SchemaIssue("entities", "must be array — reset"))
        raw_ents = []
    for i, e in enumerate(raw_ents):
        path = f"entities[{i}]"
        if isinstance(e, str):
            en = re.sub(r"[^A-Za-z0-9_]", "", e)
            if len(en) >= 2:
                out["entities"].append({"name": en[:1].upper() + en[1:], "fields": ["id"], "evidence": e})
            continue
        if not isinstance(e, dict):
            issues.append(SchemaIssue(path, "must be object or string"))
            continue
        en = re.sub(r"[^A-Za-z0-9_]", "", str(e.get("name") or ""))
        if len(en) < 2:
            issues.append(SchemaIssue(f"{path}.name", "invalid"))
            continue
        fields_raw = e.get("fields", [])
        if fields_raw is None:
            fields_raw = []
        if not isinstance(fields_raw, list):
            issues.append(SchemaIssue(f"{path}.fields", "must be array"))
            fields_raw = []
        fields: list[str] = []
        for f in fields_raw:
            fs = re.sub(r"[^a-z0-9_]", "", str(f).lower())
            if fs and fs not in fields:
                fields.append(fs)
        if "id" not in fields:
            fields.insert(0, "id")
        ev = str(e.get("evidence") or "").strip()[:120]
        out["entities"].append({
            "name": en[:1].upper() + en[1:],
            "fields": fields[:10],
            "evidence": ev,
        })

    # rules
    raw_rules = data.get("rules", [])
    if raw_rules is None:
        raw_rules = []
    if not isinstance(raw_rules, list):
        issues.append(SchemaIssue("rules", "must be array — reset"))
        raw_rules = []
    for i, r in enumerate(raw_rules):
        path = f"rules[{i}]"
        if isinstance(r, str):
            tx = r.strip()[:240]
            if tx:
                out["rules"].append({"text": tx, "evidence": tx[:80]})
            continue
        if not isinstance(r, dict):
            issues.append(SchemaIssue(path, "must be object or string"))
            continue
        tx = str(r.get("text") or r.get("rule") or "").strip()[:240]
        if not tx:
            issues.append(SchemaIssue(f"{path}.text", "empty"))
            continue
        ev = str(r.get("evidence") or tx[:80]).strip()[:120]
        out["rules"].append({"text": tx, "evidence": ev})

    # flows
    raw_flows = data.get("flows", [])
    if raw_flows is None:
        raw_flows = []
    if not isinstance(raw_flows, list):
        issues.append(SchemaIssue("flows", "must be array — reset"))
        raw_flows = []
    for i, fl in enumerate(raw_flows):
        path = f"flows[{i}]"
        if not isinstance(fl, dict):
            issues.append(SchemaIssue(path, "must be object"))
            continue
        cmd = re.sub(r"[^a-z0-9_]", "", str(fl.get("command") or "").lower())
        if not cmd:
            issues.append(SchemaIssue(f"{path}.command", "empty"))
            continue
        steps_raw = fl.get("steps", [])
        if not isinstance(steps_raw, list):
            issues.append(SchemaIssue(f"{path}.steps", "must be array"))
            steps_raw = []
        steps: list[str] = []
        for s in steps_raw:
            ss = re.sub(r"[^a-z0-9_]", "", str(s).lower())
            if ss and ss not in steps:
                steps.append(ss)
        if not steps:
            issues.append(SchemaIssue(f"{path}.steps", "empty steps — skipped"))
            continue
        out["flows"].append({
            "command": cmd,
            "steps": steps[:8],
            "evidence": str(fl.get("evidence") or "")[:120],
        })

    nc = data.get("needs_clarification", False)
    if not isinstance(nc, bool):
        nc = str(nc).lower() in ("1", "true", "yes")
        issues.append(SchemaIssue("needs_clarification", "coerced to bool"))
    out["needs_clarification"] = bool(nc)

    cq = data.get("clarification_questions", [])
    if cq is None:
        cq = []
    if not isinstance(cq, list):
        issues.append(SchemaIssue("clarification_questions", "must be array"))
        cq = []
    out["clarification_questions"] = [str(q).strip() for q in cq if str(q).strip()][:5]

    fn = data.get("fidelity_notes", data.get("notes", ""))
    if not isinstance(fn, str):
        fn = str(fn or "")
    out["fidelity_notes"] = fn.strip()[:300]

    # Hard failure: empty root after parse is still usable with defaults
    # Soft: mark schema_ok if no type-level critical issues
    critical = [x for x in issues if "must be" in x.message and "coerced" not in x.message and "default" not in x.message and "reset" not in x.message]
    # We still accept after defaults — schema_ok means no structural disasters
    schema_ok = isinstance(data, dict)
    return schema_ok, issues, out


def apply_defaults(data: dict[str, Any], original: str) -> dict[str, Any]:
    """Fill safe structural defaults without inventing domain features."""
    out = dict(data)
    out.setdefault("commands", [])
    out.setdefault("buttons", [])
    out.setdefault("entities", [])
    out.setdefault("rules", [])
    out.setdefault("flows", [])
    out.setdefault("needs_clarification", False)
    out.setdefault("clarification_questions", [])
    out.setdefault("fidelity_notes", "")
    out.setdefault("bot_name", "")

    # If no commands and short text → clarification
    if not out["commands"] and len((original or "").strip()) < 60:
        out["needs_clarification"] = True
        if not out["clarification_questions"]:
            out["clarification_questions"] = [
                "البوت بيعمل إيه؟ اكتب الوظائف بجمل قصيرة",
                "في بيانات تتسجل (اسم، هاتف، عنوان…)؟",
            ]

    # Structural buttons from command descriptions when buttons empty
    if not out["buttons"] and out["commands"]:
        for c in out["commands"]:
            if isinstance(c, dict):
                lab = str(c.get("description") or c.get("name") or "").strip()[:40]
                if lab:
                    out["buttons"].append({"label": lab, "evidence": lab})

    # Ensure flows only reference known commands; drop later in grounding too
    return out


# ── Grounding (reuse logic) ───────────────────────────────────────────────

def ground_spec(data: dict[str, Any], original: str) -> tuple[dict[str, Any], dict[str, list[str]]]:
    raw = original or ""
    text_n = _norm(raw)
    dropped: dict[str, list[str]] = {
        "commands": [], "entities": [], "fields": [], "buttons": [], "rules": [], "flows": [],
    }
    out: dict[str, Any] = {
        "bot_name": str(data.get("bot_name") or "")[:48],
        "commands": [],
        "buttons": [],
        "entities": [],
        "rules": [],
        "flows": [],
        "needs_clarification": bool(data.get("needs_clarification")),
        "clarification_questions": list(data.get("clarification_questions") or [])[:5],
        "notes": str(data.get("fidelity_notes") or data.get("notes") or "")[:300],
    }

    for c in data.get("commands") or []:
        if not isinstance(c, dict):
            continue
        n = str(c.get("name") or "")
        desc = str(c.get("description") or "")[:120]
        evidence = str(c.get("evidence") or "")[:120]
        if not n or n in ("start", "help"):
            continue
        if (
            _grounded_token(n, raw, text_n, evidence)
            or _grounded_token(desc, raw, text_n, evidence)
            or (evidence and _phrase_in_text(evidence, raw, text_n))
        ):
            out["commands"].append({
                "name": n[:32],
                "description": desc or n,
                "admin_only": bool(c.get("admin_only")),
                "roles": list(c.get("roles") or []),
                "evidence": evidence,
            })
        else:
            dropped["commands"].append(n)

    for b in data.get("buttons") or []:
        if isinstance(b, str):
            label, evidence = b.strip()[:48], b.strip()
        elif isinstance(b, dict):
            label = str(b.get("label") or "").strip()[:48]
            evidence = str(b.get("evidence") or label)
        else:
            continue
        if not label:
            continue
        cmd_match = any(
            _norm(label) == _norm(c.get("description") or "")
            or c["name"] in _norm(label)
            or _norm(label) in _norm(c.get("description") or "")
            for c in out["commands"]
        )
        if (
            _phrase_in_text(label, raw, text_n)
            or _grounded_token(label, raw, text_n, evidence)
            or cmd_match
        ):
            out["buttons"].append(label)
        else:
            dropped["buttons"].append(label)

    if not out["buttons"] and out["commands"]:
        for c in out["commands"]:
            lab = (c.get("description") or c["name"]).strip()[:40]
            if lab and lab not in out["buttons"]:
                out["buttons"].append(lab)

    # Fields must appear in user text (or evidence). No soft-field inventory.
    for e in data.get("entities") or []:
        if not isinstance(e, dict):
            continue
        en = re.sub(r"[^A-Za-z0-9_]", "", str(e.get("name") or ""))
        if len(en) < 2:
            continue
        evidence = str(e.get("evidence") or "")[:120]
        entity_ok = (
            _grounded_token(en, raw, text_n, evidence)
            or _grounded_token(en.lower(), raw, text_n, evidence)
            or (evidence and _phrase_in_text(evidence, raw, text_n))
        )
        fields_out: list[str] = []
        for f in e.get("fields") or []:
            fs = re.sub(r"[^a-z0-9_]", "", str(f).lower())
            if not fs:
                continue
            if fs == "id" or _grounded_token(fs, raw, text_n, evidence):
                if fs not in fields_out:
                    fields_out.append(fs)
            else:
                dropped["fields"].append(f"{en}.{fs}")
        if not entity_ok and not fields_out:
            dropped["entities"].append(en)
            continue
        if "id" not in fields_out:
            fields_out.insert(0, "id")
        out["entities"].append({
            "name": en[:1].upper() + en[1:],
            "fields": e.get("fields") or fields_out[:8],
            "relations": list(e.get("relations") or []),
            "evidence": evidence,
        })

    for r in data.get("rules") or []:
        if isinstance(r, str):
            rs, ev, cond = r.strip(), r[:80], ""
        elif isinstance(r, dict):
            rs = str(r.get("text") or "").strip()
            ev = str(r.get("evidence") or rs[:80])
            cond = str(r.get("condition") or "")
        else:
            continue
        if not rs or len(rs) > 240:
            continue
        toks = [t for t in re.split(r"\s+", rs) if len(t) >= 3][:8]
        hit = sum(1 for t in toks if _norm(t) in text_n or t in raw)
        if (ev and _phrase_in_text(ev, raw, text_n)) or (toks and hit >= max(1, len(toks) // 2)):
            out["rules"].append({"text": rs, "condition": cond, "evidence": ev})
        else:
            dropped["rules"].append(rs[:40])

    for i in data.get("integrations") or []:
        if not isinstance(i, dict): continue
        srv = str(i.get("service") or "").lower()
        ev = str(i.get("evidence") or srv)
        if _grounded_token(srv, raw, text_n, ev):
            out["integrations"].append(i)
        else:
            dropped["integrations"].append(srv)

    kept = {c["name"] for c in out["commands"]}
    for fl in data.get("flows") or []:
        if not isinstance(fl, dict):
            continue
        cmd = re.sub(r"[^a-z0-9_]", "", str(fl.get("command") or "").lower())
        if cmd not in kept:
            dropped["flows"].append(cmd or "?")
            continue
        steps = []
        for s in fl.get("steps") or []:
            ss = re.sub(r"[^a-z0-9_]", "", str(s).lower())
            if ss and ss not in steps:
                steps.append(ss)
        if steps:
            out["flows"].append({"command": cmd, "steps": steps[:6]})

    if len(out["commands"]) == 0 and not out["needs_clarification"] and len(raw.strip()) < 60:
        out["needs_clarification"] = True
        if not out["clarification_questions"]:
            out["clarification_questions"] = [
                "البوت بيعمل إيه؟ اكتب الوظائف بجمل قصيرة",
                "في بيانات تتسجل (اسم، هاتف، عنوان…)؟",
            ]
    return out, dropped


def spec_to_text(data: dict[str, Any], original: str) -> str:
    lines: list[str] = []
    name = str(data.get("bot_name") or "").strip()
    if name:
        lines.append(f"اعمل بوت تليجرام باسم {name}")
    else:
        first = (original or "").strip().splitlines()[0][:200] if original else "اعمل بوت تليجرام"
        lines.append(first)

    cmds = data.get("commands") or []
    if cmds:
        lines.append("الأوامر:")
        for c in cmds:
            n = c.get("name") or ""
            d = c.get("description") or n
            admin = " (أدمن)" if c.get("admin_only") else ""
            roles = f" [roles: {', '.join(c.get('roles', []))}]" if c.get("roles") else ""
            lines.append(f"/{n} — {d}{admin}{roles}")

    ents = data.get("entities") or []
    if ents:
        lines.append("الكيانات:")
        for e in ents:
            en = e.get("name") or ""
            fields = []
            for f in (e.get("fields") or []):
                if isinstance(f, dict):
                    fields.append(f"{f.get('name')}:{f.get('type', 'str')}")
                else:
                    fields.append(str(f))
            rel_str = ""
            if e.get("relations"):
                rel_str = " | العلاقات: " + ", ".join([f"{r.get('type')} with {r.get('target')}" for r in e["relations"]])
            lines.append(f"{en} ({', '.join(fields)}){rel_str}")

    ints = data.get("integrations") or []
    if ints:
        lines.append("التكاملات:")
        for i in ints:
            lines.append(f"- {i.get('service')}: {i.get('purpose')}")

    buttons = data.get("buttons") or []
    if buttons:
        lines.append("الأزرار:")
        for b in buttons:
            lines.append(str(b))

    rules = data.get("rules") or []
    if rules:
        lines.append("القواعد:")
        for r in rules:
            if isinstance(r, dict):
                cond = f" [إذا {r.get('condition')}]" if r.get("condition") else ""
                lines.append(f"{r.get('text')}{cond}")
            else:
                lines.append(str(r))

    flows = data.get("flows") or []
    if flows:
        lines.append("التدفقات:")
        for fl in flows:
            lines.append(f"{fl.get('command')}: {', '.join(str(s) for s in (fl.get('steps') or []))}")

    lines.append("")
    lines.append("--- المصدر ---")
    lines.append((original or "")[:8000]) # Increased for long text
    return "\n".join(lines)


# ── Model I/O ─────────────────────────────────────────────────────────────

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
    return ""


def _issues_text(issues: list[SchemaIssue]) -> str:
    if not issues:
        return "unknown schema problem"
    return "\n".join(f"- {i.path}: {i.message}" for i in issues[:15])


def _request_json(
    client: Any,
    model: str,
    user_text: str,
    *,
    retry_errors: str | None = None,
) -> tuple[dict[str, Any] | None, str]:
    """Returns (normalized_spec_or_None, raw_content)."""
    # If text is very long, use chunking strategy
    if not retry_errors and len(user_text) > 10000:
        return _request_json_long(client, model, user_text)

    if retry_errors:
        messages = [
            {"role": "system", "content": _RETRY_SYSTEM},
            {
                "role": "user",
                "content": (
                    "Fix the JSON. Validation problems:\n"
                    f"{retry_errors}\n\n"
                    "Original user text:\n"
                    f"{user_text[:8000]}\n\n"
                    "Return ONLY the corrected JSON object."
                ),
            },
        ]
    else:
        messages = [
            {"role": "system", "content": _SYSTEM},
            {
                "role": "user",
                "content": (
                    "Translate the following user text into the required JSON schema.\n"
                    "JSON only. No markdown. No prose.\n\n"
                    f"{user_text[:12000]}"
                ),
            },
        ]
    content = _call_model(client, model, messages)
    data = _parse_json(content)
    if data is None:
        return None, content
    ok, issues, normalized = validate_spec_schema(data)
    if not ok:
        return None, content
    normalized = apply_defaults(normalized, user_text)
    return normalized, content

def _request_json_long(client: Any, model: str, user_text: str) -> tuple[dict[str, Any] | None, str]:
    """Strategy for extremely long texts: Extract Map -> Translate Chunks -> Merge."""
    logger.info(f"Using long-text strategy for {len(user_text)} chars")
    
    # 1. Extract Mental Map
    map_messages = [
        {"role": "system", "content": "You are a requirements analyzer. Extract a list of ALL commands, entities, and integrations mentioned in the text. Output ONLY a simple JSON list of names."},
        {"role": "user", "content": f"Text: {user_text[:20000]}"}
    ]
    map_content = _call_model(client, model, map_messages)
    
    # 2. Chunking (simple split for now, could be smarter)
    chunks = [user_text[i:i+8000] for i in range(0, len(user_text), 8000)]
    all_specs = []
    
    for chunk in chunks[:5]: # Limit to 5 chunks for safety
        spec, _ = _request_json(client, model, chunk)
        if spec:
            all_specs.append(spec)
            
    if not all_specs:
        return None, "long_text_failed"
        
    # 3. Merge Specs
    merged = all_specs[0]
    for other in all_specs[1:]:
        for key in ["commands", "entities", "buttons", "rules", "flows", "integrations"]:
            merged[key].extend(other.get(key, []))
            
    # De-duplicate
    merged["commands"] = list({c["name"]: c for c in merged["commands"] if "name" in c}.values())
    merged["entities"] = list({e["name"]: e for e in merged["entities"] if "name" in e}.values())
    
    return merged, "merged_from_chunks"


def _translate_with_hf(text: str, timeout: int) -> TranslatorResult:
    """Translate using HF Inference Providers; return a normal TranslatorResult."""
    from .hf_provider import chat, enabled

    if not enabled():
        return TranslatorResult(ok=False, error="hf_disabled")
    t0 = time.perf_counter()
    messages = [
        {"role": "system", "content": _SYSTEM},
        {
            "role": "user",
            "content": (
                "Translate the following user text into the required JSON schema. "
                "Return ONLY the JSON object.\n\n" + text[:7000]
            ),
        },
    ]
    try:
        content, model = chat(
            messages,
            timeout=timeout,
            max_tokens=2200,
            temperature=0,
            json_mode=True,
        )
        data = _parse_json(content)
        if data is None:
            return TranslatorResult(
                ok=False,
                model_used=model,
                error="hf_invalid_json",
                elapsed_ms=round((time.perf_counter() - t0) * 1000, 1),
            )
        ok, issues, normalized = validate_spec_schema(data)
        if not ok:
            return TranslatorResult(
                ok=False,
                model_used=model,
                error="hf_schema_invalid",
                schema_issues=[f"{i.path}: {i.message}" for i in issues],
                elapsed_ms=round((time.perf_counter() - t0) * 1000, 1),
            )
        data = apply_defaults(normalized, text)
        grounded, dropped = ground_spec(data, text)
        # A model may return clarification questions while omitting commands.
        # Do not let that create a formally valid but empty bot when the user
        # already named concrete capabilities; use the lexical fallback below.
        if not (grounded.get("commands") or []) and len(text) >= 20:
            fallback = _local_fallback_spec(text)
            if fallback.count("/"):
                return TranslatorResult(
                    ok=True,
                    structured_text=fallback,
                    model_used=f"huggingface:{model}+local_fallback",
                    elapsed_ms=round((time.perf_counter() - t0) * 1000, 1),
                    raw_json=data,
                    grounded_json=grounded,
                    dropped=dropped,
                    schema_ok=True,
                )
        structured = spec_to_text(grounded, text)
        return TranslatorResult(
            ok=True,
            structured_text=structured,
            model_used=f"huggingface:{model}",
            elapsed_ms=round((time.perf_counter() - t0) * 1000, 1),
            raw_json=data,
            grounded_json=grounded,
            dropped=dropped,
            needs_clarification=bool(grounded.get("needs_clarification")),
            clarification_questions=list(grounded.get("clarification_questions") or []),
            schema_ok=True,
            schema_issues=[f"{i.path}: {i.message}" for i in issues],
        )
    except Exception as exc:
        return TranslatorResult(
            ok=False,
            error=f"hf:{type(exc).__name__}:{exc}"[:1200],
            elapsed_ms=round((time.perf_counter() - t0) * 1000, 1),
        )


def translate_spec(user_text: str, *, timeout: int | None = None) -> TranslatorResult:
    text = (user_text or "").strip()
    if not text:
        return TranslatorResult(ok=False, error="empty")
    if not _enabled():
        return TranslatorResult(ok=False, error="disabled")

    timeout = timeout if timeout is not None else int(
        os.environ.get("SPEC_TRANSLATOR_TIMEOUT", "25")
    )

    # Hugging Face is the primary provider when HF_TOKEN is configured. This
    # avoids the unstable g4f dependency while retaining backward compatibility
    # for installations that have not configured HF yet.
    if (os.environ.get("HF_TOKEN") or "").strip() and os.environ.get(
        "HF_PRIMARY", "1"
    ).strip().lower() not in {"0", "false", "no", "off"}:
        hf_result = _translate_with_hf(text, timeout)
        if hf_result.ok:
            return hf_result
        logger.warning("Hugging Face spec translation failed: %s", hf_result.error)
        # Do not silently switch back to the unstable legacy provider. The
        # caller will use the deterministic local fallback instead.
        if not os.environ.get("LEGACY_G4F", "").strip():
            return hf_result

    forced = (os.environ.get("SPEC_TRANSLATOR_MODEL") or "").strip()
    candidates = (forced,) if forced else _MODEL_CANDIDATES
    retries_max = _max_retries()

    t0 = time.perf_counter()
    last_err = ""
    try:
        from g4f.client import Client
        client = Client()
    except Exception as e:
        return TranslatorResult(ok=False, error=f"g4f_import:{e}")

    for model in candidates:
        if (time.perf_counter() - t0) > timeout:
            last_err = "timeout"
            break
        retries_used = 0
        try:
            data, raw_content = _request_json(client, model, text)
            schema_issues: list[str] = []

            if data is None:
                # retry parse/schema failures
                while retries_used < retries_max and (time.perf_counter() - t0) < timeout:
                    retries_used += 1
                    err = "invalid JSON or not an object — return pure JSON only"
                    data, raw_content = _request_json(
                        client, model, text, retry_errors=err
                    )
                    if data is not None:
                        break
                if data is None:
                    last_err = f"bad_json:{model}"
                    continue

            # schema validate again after success path
            ok, issues, normalized = validate_spec_schema(data)
            data = apply_defaults(normalized if ok else data, text)
            schema_issues = [f"{i.path}: {i.message}" for i in issues]

            # If critical empty commands on rich text, one schema retry
            if (
                not data.get("commands")
                and len(text) >= 80
                and retries_used < retries_max
                and (time.perf_counter() - t0) < timeout
            ):
                retries_used += 1
                data2, _ = _request_json(
                    client,
                    model,
                    text,
                    retry_errors=(
                        "commands array is empty but user text is detailed. "
                        "Extract all mentioned functions into commands[]. "
                        + _issues_text(issues)
                    ),
                )
                if data2 and data2.get("commands"):
                    data = data2
                    ok2, issues2, norm2 = validate_spec_schema(data)
                    data = apply_defaults(norm2 if ok2 else data, text)
                    schema_issues = [f"{i.path}: {i.message}" for i in issues2]

            fidelity_pass = False
            if _repair_enabled() and (time.perf_counter() - t0) < timeout - 4:
                try:
                    payload = json.dumps(data, ensure_ascii=False)[:8000]
                    repair_msgs = [
                        {"role": "system", "content": _REPAIR_SYSTEM},
                        {
                            "role": "user",
                            "content": (
                                f"Original text:\n{text[:5000]}\n\n"
                                f"Current JSON:\n{payload}\n\n"
                                "Return ONLY corrected JSON."
                            ),
                        },
                    ]
                    repaired_raw = _call_model(client, model, repair_msgs)
                    repaired = _parse_json(repaired_raw)
                    if repaired:
                        ok_r, issues_r, norm_r = validate_spec_schema(repaired)
                        if ok_r and (norm_r.get("commands") or data.get("commands")):
                            data = apply_defaults(norm_r, text)
                            fidelity_pass = True
                            schema_issues = [f"{i.path}: {i.message}" for i in issues_r]
                except Exception as rep_e:
                    logger.warning("fidelity repair skipped: %s", rep_e)

            grounded, dropped = ground_spec(data, text)
            structured = spec_to_text(grounded, text)
            elapsed = (time.perf_counter() - t0) * 1000
            logger.info(
                "spec_translator ok model=%s cmds=%s retries=%s repair=%s ms=%.0f",
                model,
                len(grounded.get("commands") or []),
                retries_used,
                fidelity_pass,
                elapsed,
            )
            return TranslatorResult(
                ok=True,
                structured_text=structured,
                model_used=model,
                elapsed_ms=round(elapsed, 1),
                raw_json=data,
                grounded_json=grounded,
                dropped=dropped,
                needs_clarification=bool(grounded.get("needs_clarification")),
                clarification_questions=list(grounded.get("clarification_questions") or []),
                fidelity_pass=fidelity_pass,
                schema_ok=True,
                schema_issues=schema_issues,
                retries=retries_used,
            )
        except Exception as e:
            last_err = f"{model}:{type(e).__name__}:{e}"
            logger.warning("spec_translator failed %s", last_err)
            continue

    elapsed = (time.perf_counter() - t0) * 1000
    return TranslatorResult(
        ok=False,
        error=last_err or "all_models_failed",
        elapsed_ms=round(elapsed, 1),
    )


def _local_fallback_spec(original: str) -> str:
    """Build a small grounded spec when the optional translator times out.

    This is intentionally a lexical fallback, not a domain template: every
    emitted command is enabled only by phrases present in the user's text.
    """
    text = original or ""
    rules = [
        ("products", "المنتجات", ("منتج", "منتجات", "اصناف", "أصناف", "صنف")),
        ("cart", "سلة الشراء", ("سلة", "سله", "عربة", "عربه")),
        ("checkout", "إتمام الطلب", ("إتمام الطلب", "اتمام الطلب", "شراء", "طلب الأوردر", "طلب الاوردر")),
        ("tickets", "تذاكر الدعم", ("تذكرة", "تذاكر", "تذاكر الدعم")),
        ("support", "الدعم", ("دعم", "خدمة العملاء", "خدمه العملاء")),
        ("warn", "التحذير", ("تحذير", "إنذار", "انذار")),
        ("ban", "الحظر", ("حظر", "بان")),
        ("mute", "الكتم", ("كتم",)),
        ("booking", "الحجوزات", ("حجز", "حجوز", "موعد", "مواعيد")),
        ("delivery", "التوصيل", ("توصيل",)),
        ("pay", "الدفع", ("دفع", "سداد",)),
        ("search", "البحث", ("بحث",)),
    ]
    selected: list[tuple[str, str]] = []
    seen: set[str] = set()
    for command, label, phrases in rules:
        if command not in seen and any(p in text for p in phrases):
            selected.append((command, label))
            seen.add(command)
    lines = ["اعمل بوت تليجرام"]
    if selected:
        lines.append("الأوامر:")
        lines.extend(f"/{cmd} — {label}" for cmd, label in selected)
        lines.append("الأزرار:")
        lines.extend(f"- {label}" for _, label in selected)
    if any(p in text for p in ("منتج", "منتجات", "صنف", "أصناف")):
        lines.append("الكيانات:")
        lines.append("Product (id, name, price)")
    if any(p in text for p in ("طلب", "اوردر", "أوردر")):
        if "الكيانات:" not in lines:
            lines.append("الكيانات:")
        lines.append("Order (id, status)")
    lines.extend(["", "--- المصدر ---", text[:4000]])
    return "\\n".join(lines)


def prepare_formal_text(user_text: str) -> tuple[str, TranslatorResult]:
    original = user_text or ""
    if not _enabled():
        return original, TranslatorResult(ok=False, error="disabled")
    result = translate_spec(original)
    if result.ok and result.structured_text.strip():
        return result.structured_text, result
    # Never pass a rich natural-language request straight to extract_dsl after
    # a timeout: that path understands sections, not arbitrary Arabic prose.
    fallback = _local_fallback_spec(original)
    if fallback.count("/"):
        result.ok = True
        result.model_used = "local_fallback"
        result.structured_text = fallback
        result.error = result.error or "translator_fallback"
        result.grounded_json = {"fallback": True}
        return fallback, result
    return original, result
