"""
SpecTranslator — AI translates user speech → formal specification JSON ONLY.

ALLOWED:
  - Rewrite natural language into structured JSON (commands/entities/buttons/rules/flows)
  - Mark needs_clarification when text is too thin

FORBIDDEN:
  - Generating Python / any code
  - Domain packs (shop/delivery/ticket skeletons)
  - Inventing commands the user did not imply
  - Touching formal_engine

Pipeline:
  user text → SpecTranslator → ground against original → sectioned text → Formal Engine
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
    "gemini-1.5-flash",
    "gpt-4o-mini",
    "claude-3-haiku",
    "claude-3.5-sonnet",
    "gpt-4o",
)

_SYSTEM = """أنت مترجم مواصفات فقط (Spec Translator) لبوتات تليجرام.
مهمتك الوحيدة: حوّل كلام المستخدم إلى JSON منظم.
ممنوع منعاً باتاً: كتابة كود، اختراع أوامر من قوالب متجر/توصيل/تذاكر، إضافة ميزات «منطقية» لم تُذكر.

أرجع JSON فقط بهذا الشكل:
{
  "bot_name": "string",
  "commands": [{"name": "register", "description": "تسجيل", "admin_only": false}],
  "buttons": ["تسجيل", "تتبع"],
  "entities": [{"name": "Customer", "fields": ["name", "phone"]}],
  "rules": ["لو تم الطلب يحفظ العنوان"],
  "flows": [{"command": "register", "steps": ["name", "phone"]}],
  "needs_clarification": false,
  "clarification_questions": [],
  "notes": ""
}

قواعد صارمة:
1) name للأمر بدون / (register وليس /register) — أحرف إنجليزية صغيرة وأرقام و _.
2) لا تضف أوامر لم يذكرها أو لم يُشر إليها المستخدم. start/help فقط إن لزم الهيكل لاحقاً (لا تضعها أنت).
3) admin_only=true فقط إذا ذكر أدمن/admin/مشرف.
4) الحقول والكيانات من النص أو الإشارة المباشرة فقط.
5) لو النص غامض جداً (اسم فقط أو «عايز بوت»): needs_clarification=true وأضف 1–3 أسئلة قصيرة في clarification_questions.
6) لا Markdown ولا شرح خارج JSON.
7) description و button labels يمكن أن تبقى بالعربية كما قال المستخدم.
"""


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
        }


def _enabled() -> bool:
    # Default ON — translator is the intended path; set SPEC_TRANSLATOR=0 to disable
    v = (os.environ.get("SPEC_TRANSLATOR") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def _norm(s: str) -> str:
    s = (s or "").lower()
    s = s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    s = s.replace("ة", "ه").replace("ى", "ي")
    s = re.sub(r"\s+", " ", s)
    return s


# Linguistic synonym stems (NOT domain packs) — for grounding only
_SYN: list[tuple[str, tuple[str, ...]]] = [
    ("register", ("تسجيل", "يسجل", "signup", "sign up", "register")),
    ("order", ("طلب", "اوردر", "order", "طلبات")),
    ("track", ("تتبع", "يتابع", "track", "tracking")),
    ("my_orders", ("طلباتي", "اوردراتي", "my orders")),
    ("book", ("حجز", "يحجز", "book", "booking", "موعد", "مواعيد")),
    ("menu", ("منيو", "قائمة", "menu")),
    ("admin", ("ادمن", "أدمن", "admin", "مشرف")),
    ("stats", ("احصائ", "إحصائ", "stats")),
    ("search", ("بحث", "يبحث", "search")),
    ("pay", ("دفع", "يدفع", "pay", "payment")),
    ("support", ("دعم", "support", "تذكرة")),
    ("delivery", ("توصيل", "delivery")),
    ("profile", ("ملف", "profile")),
    ("cancel", ("الغاء", "إلغاء", "cancel")),
    ("confirm", ("تاكيد", "تأكيد", "confirm")),
    ("customer", ("عميل", "عملاء", "customer", "client")),
    ("driver", ("سائق", "سائقين", "driver")),
    ("product", ("منتج", "صنف", "product", "item")),
    ("name", ("اسم", "name")),
    ("phone", ("هاتف", "موبايل", "تليفون", "phone", "mobile")),
    ("address", ("عنوان", "address")),
    ("email", ("ايميل", "بريد", "email")),
    ("status", ("حالة", "status")),
    ("date", ("تاريخ", "date")),
    ("time", ("وقت", "time")),
]


def _grounded_token(token: str, original: str, original_n: str) -> bool:
    tok = (token or "").strip()
    if not tok:
        return False
    t = tok.lower()
    if t in original_n or tok in original:
        return True
    if re.search(rf"/{re.escape(t)}\b", original, re.I):
        return True
    # synonym groups
    for key, phrases in _SYN:
        if t == key or t.replace("_", "") == key.replace("_", ""):
            if any(_norm(p) in original_n or p in original for p in phrases):
                return True
        if any(_norm(p) == t or p == tok for p in phrases):
            if any(_norm(p) in original_n or p in original for p in phrases):
                return True
    # multi-part command: register_customer
    parts = [p for p in t.split("_") if len(p) >= 3]
    if len(parts) >= 2 and all(
        p in original_n or any(_norm(ph) in original_n for k, phrases in _SYN if k == p for ph in phrases)
        for p in parts
    ):
        return True
    # arabic/latin substring length >= 3
    if len(t) >= 3 and t in original_n:
        return True
    return False


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


def ground_spec(data: dict[str, Any], original: str) -> tuple[dict[str, Any], dict[str, list[str]]]:
    """Drop any surface not grounded in original user text."""
    raw = original or ""
    text_n = _norm(raw)
    dropped: dict[str, list[str]] = {
        "commands": [],
        "entities": [],
        "fields": [],
        "buttons": [],
        "rules": [],
        "flows": [],
    }
    out: dict[str, Any] = {
        "bot_name": "",
        "commands": [],
        "buttons": [],
        "entities": [],
        "rules": [],
        "flows": [],
        "needs_clarification": bool(data.get("needs_clarification")),
        "clarification_questions": list(data.get("clarification_questions") or []),
        "notes": str(data.get("notes") or "")[:200],
    }

    name = str(data.get("bot_name") or "").strip()
    if name and (_grounded_token(name, raw, text_n) or len(name) <= 40):
        # bot name is soft: allow if present or short label from user context
        if name in raw or _norm(name) in text_n or True:
            out["bot_name"] = name[:48]

    for c in data.get("commands") or []:
        if not isinstance(c, dict):
            continue
        n = re.sub(r"[^a-z0-9_]", "", str(c.get("name") or "").lower().lstrip("/"))
        desc = str(c.get("description") or "")[:100]
        if not n or n in ("start", "help", "http", "https"):
            continue
        if _grounded_token(n, raw, text_n) or _grounded_token(desc, raw, text_n):
            out["commands"].append({
                "name": n[:32],
                "description": desc or n,
                "admin_only": bool(c.get("admin_only")),
            })
        else:
            dropped["commands"].append(n)

    for b in data.get("buttons") or []:
        label = str(b if not isinstance(b, dict) else b.get("label") or b.get("text") or "").strip()
        if not label or len(label) > 48:
            continue
        if _grounded_token(label, raw, text_n) or any(
            _grounded_token(str(x.get("description") or ""), raw, text_n)
            or _grounded_token(str(x.get("name") or ""), raw, text_n)
            for x in out["commands"]
        ):
            # button ok if label in text OR matches a kept command description/name
            cmd_match = any(
                label == str(x.get("description") or "")
                or str(x.get("name") or "") in _norm(label)
                or _norm(label) in _norm(str(x.get("description") or ""))
                for x in out["commands"]
            )
            if label in raw or _norm(label) in text_n or cmd_match:
                out["buttons"].append(label)
            else:
                dropped["buttons"].append(label)
        else:
            dropped["buttons"].append(label)

    for e in data.get("entities") or []:
        if not isinstance(e, dict):
            continue
        en = re.sub(r"[^A-Za-z0-9_]", "", str(e.get("name") or ""))
        if not en or len(en) < 2:
            continue
        if not (
            _grounded_token(en, raw, text_n)
            or _grounded_token(en.lower(), raw, text_n)
        ):
            # allow entity if any field grounded and command implies data
            fields_try = e.get("fields") or []
            if not any(_grounded_token(str(f), raw, text_n) for f in fields_try):
                dropped["entities"].append(en)
                continue
        fields_out = []
        for f in e.get("fields") or []:
            fs = re.sub(r"[^a-z0-9_]", "", str(f).lower())
            if not fs or fs in ("id",):
                if fs == "id":
                    fields_out.append("id")
                continue
            if _grounded_token(fs, raw, text_n) or fs in ("name", "phone", "status", "user_id"):
                # name/phone/status soft-allowed when entity itself grounded (structural minima for records)
                if _grounded_token(fs, raw, text_n) or (
                    en and fs in ("name", "phone", "status", "user_id", "id")
                ):
                    fields_out.append(fs)
                else:
                    dropped["fields"].append(f"{en}.{fs}")
            else:
                dropped["fields"].append(f"{en}.{fs}")
        if "id" not in fields_out:
            fields_out.insert(0, "id")
        out["entities"].append({"name": en[:1].upper() + en[1:], "fields": fields_out[:8]})

    for r in data.get("rules") or []:
        rs = str(r).strip()
        if not rs or len(rs) > 200:
            continue
        # rule must share tokens with original
        toks = [t for t in re.split(r"\s+", rs) if len(t) >= 3][:6]
        if toks and sum(1 for t in toks if _norm(t) in text_n or t in raw) >= max(1, len(toks) // 2):
            out["rules"].append(rs)
        else:
            dropped["rules"].append(rs[:40])

    kept_cmds = {c["name"] for c in out["commands"]}
    for fl in data.get("flows") or []:
        if not isinstance(fl, dict):
            continue
        cmd = re.sub(r"[^a-z0-9_]", "", str(fl.get("command") or "").lower())
        if cmd not in kept_cmds:
            dropped["flows"].append(cmd or "?")
            continue
        steps = []
        for s in fl.get("steps") or []:
            ss = re.sub(r"[^a-z0-9_]", "", str(s).lower())
            if ss:
                steps.append(ss)
        if steps:
            out["flows"].append({"command": cmd, "steps": steps[:6]})

    # If almost nothing left and original was thin → clarification
    if len(out["commands"]) == 0 and not out["needs_clarification"]:
        if len(raw.strip()) < 80:
            out["needs_clarification"] = True
            if not out["clarification_questions"]:
                out["clarification_questions"] = [
                    "البوت بيعمل إيه؟ اكتب الوظائف بجمل قصيرة",
                    "في بيانات تتسجل (اسم، هاتف، عنوان…)؟",
                ]

    return out, dropped


def spec_to_text(data: dict[str, Any], original: str) -> str:
    """Canonical sectioned text for extract_dsl / formal engine."""
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
            lines.append(f"/{n} — {d}{admin}")

    ents = data.get("entities") or []
    if ents:
        lines.append("الكيانات:")
        for e in ents:
            en = e.get("name") or ""
            fields = e.get("fields") or []
            if fields:
                lines.append(f"{en} ({', '.join(str(f) for f in fields)})")
            else:
                lines.append(en)

    buttons = data.get("buttons") or []
    if buttons:
        lines.append("الأزرار:")
        for b in buttons:
            lines.append(str(b))

    rules = data.get("rules") or []
    if rules:
        lines.append("القواعد:")
        for r in rules:
            lines.append(str(r))

    flows = data.get("flows") or []
    if flows:
        lines.append("التدفقات:")
        for fl in flows:
            cmd = fl.get("command") or ""
            steps = fl.get("steps") or []
            lines.append(f"{cmd}: {', '.join(str(s) for s in steps)}")

    # Append original for grounding_gate inside formal path
    lines.append("")
    lines.append("--- المصدر ---")
    lines.append((original or "")[:3000])
    return "\n".join(lines)


def translate_spec(user_text: str, *, timeout: int | None = None) -> TranslatorResult:
    """Call g4f → JSON → ground → sectioned text. Never generates code."""
    text = (user_text or "").strip()
    if not text:
        return TranslatorResult(ok=False, error="empty")

    if not _enabled():
        return TranslatorResult(ok=False, error="disabled")

    timeout = timeout if timeout is not None else int(os.environ.get("SPEC_TRANSLATOR_TIMEOUT", "12"))
    forced = (os.environ.get("SPEC_TRANSLATOR_MODEL") or "").strip()
    candidates = (forced,) if forced else _MODEL_CANDIDATES

    t0 = time.perf_counter()
    last_err = ""
    try:
        from g4f.client import Client
        client = Client()
    except Exception as e:
        return TranslatorResult(ok=False, error=f"g4f_import:{e}")

    messages = [
        {"role": "system", "content": _SYSTEM},
        {
            "role": "user",
            "content": (
                "ترجم الوصف التالي إلى JSON المواصفة المطلوب فقط. "
                "ممنوع الاختراع خارج النص.\n\n"
                f"{text[:6000]}"
            ),
        },
    ]

    for model in candidates:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                web_search=False,
            )
            content = ""
            if response and response.choices:
                content = (response.choices[0].message.content or "").strip()
            data = _parse_json(content)
            if not data:
                last_err = f"bad_json:{model}"
                continue

            grounded, dropped = ground_spec(data, text)
            structured = spec_to_text(grounded, text)
            elapsed = (time.perf_counter() - t0) * 1000
            logger.info(
                "spec_translator ok model=%s cmds=%s dropped_cmds=%s ms=%.0f",
                model,
                len(grounded.get("commands") or []),
                dropped.get("commands"),
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
            )
        except Exception as e:
            last_err = f"{model}:{type(e).__name__}:{e}"
            logger.warning("spec_translator model failed %s", last_err)
            # soft timeout budget
            if (time.perf_counter() - t0) > timeout:
                break
            continue

    elapsed = (time.perf_counter() - t0) * 1000
    return TranslatorResult(
        ok=False,
        error=last_err or "all_models_failed",
        elapsed_ms=round(elapsed, 1),
    )


def prepare_formal_text(user_text: str) -> tuple[str, TranslatorResult]:
    """
    Returns (text_for_formal_engine, translator_result).
    On failure/disabled: original text + ok=False.
    """
    original = user_text or ""
    if not _enabled():
        return original, TranslatorResult(ok=False, error="disabled")
    result = translate_spec(original)
    if result.ok and result.structured_text.strip() and not result.needs_clarification:
        return result.structured_text, result
    if result.ok and result.structured_text.strip() and result.needs_clarification:
        # still return structured for assess, caller may clarify
        return result.structured_text, result
    return original, result
