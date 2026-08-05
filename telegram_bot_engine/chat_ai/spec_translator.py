"""
SpecTranslator — maximum-fidelity speech → formal specification.

AI role: TRANSLATE only (no code, no domain packs).
Quality strategy:
  1) High-precision system prompt + few-shot examples
  2) Each surface item should carry evidence from user words
  3) Grounding keeps items with evidence / synonym / stem match
  4) Optional second-pass fidelity repair (fill omissions, drop inventions)
  5) Formal engine remains the only code generator
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

_SYSTEM = """أنت مترجم مواصفات دقيق جداً (High-Fidelity Spec Translator) لبوتات تليجرام.

الدور الوحيد: حوّل كلام المستخدم إلى JSON منظم يعكس قصده بدقة قصوى.
أنت لست مولّد كود ولست مصمم منتجات — مترجم فقط.

═══════════════════════════════════════
مبدأ الدقة 100%
═══════════════════════════════════════
1) استخرج كل وظيفة ذكرها أو أشار إليها المستخدم (أفعال، قوائم، «فيه X و Y»).
2) ممنوع اختراع ميزات «مفيدة» لم تُذكر (مثل دفع/سلة/كوبون إن لم يقلها).
3) الاسم الإنجليزي للأمر (name) ترجمة تقنية للكيان العربي؛ الـ description يبقى بصياغة المستخدم قدر الإمكان.
4) كل أمر/كيان/حقل/زر يفضّل أن يحمل "evidence": مقتطف قصير من كلام المستخدم يثبت العنصر.
5) لو جملة واحدة تحمل عدة وظائف — استخرجها كلها.
6) لو النص غامض جداً (اسم فقط / «عايز بوت»): needs_clarification=true مع أسئلة قصيرة.
7) JSON فقط — لا Markdown ولا شرح خارج JSON.

═══════════════════════════════════════
شكل JSON الإلزامي
═══════════════════════════════════════
{
  "bot_name": "string",
  "commands": [
    {
      "name": "register",
      "description": "تسجيل عملاء",
      "admin_only": false,
      "evidence": "يسجل العملاء"
    }
  ],
  "buttons": [
    {"label": "تسجيل", "evidence": "تسجيل"}
  ],
  "entities": [
    {
      "name": "Customer",
      "fields": ["name", "phone"],
      "evidence": "العملاء"
    }
  ],
  "rules": [
    {"text": "لو تم الطلب يحفظ العنوان", "evidence": "يحفظ العنوان"}
  ],
  "flows": [
    {
      "command": "register",
      "steps": ["name", "phone"],
      "evidence": "تسجيل العملاء"
    }
  ],
  "needs_clarification": false,
  "clarification_questions": [],
  "fidelity_notes": "ملخص جملة: ما تم استخراجه"
}

═══════════════════════════════════════
قواعد name
═══════════════════════════════════════
- أحرف إنجليزية صغيرة + أرقام + _ فقط، بدون /
- ترجم المعنى: تسجيل→register، تتبع→track، طلباتي→my_orders، حجز→book
- لا تضع start أو help

═══════════════════════════════════════
الكيانات والحقول
═══════════════════════════════════════
- كيان من الأسماء في النص: عملاء→Customer، طلبات→Order، سائقين→Driver، مواعيد→Appointment
- الحقول فقط إن ذُكرت أو لُزمت صراحة من السياق القريب (اسم/هاتف/عنوان/حالة…)
- لا تفرّغ مكتبة حقول كاملة

═══════════════════════════════════════
أمثلة (Few-shot)
═══════════════════════════════════════

مثال A:
المستخدم: «بوت عبود يسجل العملاء ويأخذ طلبات ويتابعها ويعرض طلباتي»
JSON تقريبي:
commands: register(تسجيل العملاء), order(يأخذ طلبات), track(يتابعها), my_orders(طلباتي)
entities: Customer, Order
buttons من نفس الألفاظ إن ناسبت
needs_clarification: false

مثال B:
المستخدم: «اعمل بوت»
→ needs_clarification: true
clarification_questions: ["البوت بيعمل إيه؟", "في بيانات تتسجل؟"]

مثال C:
المستخدم: «فيه /register و /track فقط»
→ commands: register, track فقط — لا order ولا menu

مثال D:
المستخدم: «حجز مواعيد فيه اسم وموبايل وتاريخ»
→ book + entity Appointment fields name, phone, date

مثال E (ممنوع):
المستخدم: «بوت تسجيل طلبات»
→ لا تضف payment أو cart أو coupons من عندك
"""

_REPAIR_SYSTEM = """أنت مراجع دقة مواصفات (Fidelity Auditor).
给你: (1) نص المستخدم الأصلي (2) JSON مترجم.
المهمة: أصلح JSON ليعكس النص بدقة أعلى.
- أضف أوامر/كيانات/حقول ذُكرت في النص وناقصة في JSON
- احذف أي عنصر بلا سند من النص
- حسّن evidence ليكون مقتطفاً من كلام المستخدم
- لا تخترع ميزات جديدة
أرجع JSON كامل بنفس الشكل فقط.
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
    fidelity_pass: bool = False

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
        }


def _enabled() -> bool:
    v = (os.environ.get("SPEC_TRANSLATOR") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def _repair_enabled() -> bool:
    v = (os.environ.get("SPEC_TRANSLATOR_REPAIR") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def _norm(s: str) -> str:
    s = (s or "").lower()
    s = s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    s = s.replace("ة", "ه").replace("ى", "ي")
    s = s.replace("ؤ", "و").replace("ئ", "ي")
    s = re.sub(r"\s+", " ", s)
    return s


# Expanded linguistic synonyms for grounding (not domain feature packs)
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
        "تتبع", "يتابع", "يتابعها", "تتبعها", "track", "tracking",
        "متابعة", "متابعة الطلب",
    )),
    ("my_orders", ("طلباتي", "اوردراتي", "my orders", "يشوف اوردراته", "عرض طلباتي")),
    ("book", ("حجز", "يحجز", "book", "booking", "موعد", "مواعيد", "احجز")),
    ("my_appointments", ("مواعيدي", "حجوزاتي", "my appointments")),
    ("menu", ("منيو", "قائمة", "menu", "قائمة الطعام", "القائمة")),
    ("admin", ("ادمن", "أدمن", "admin", "مشرف", "لوحة الادارة", "لوحة الإدارة")),
    ("stats", ("احصائ", "إحصائ", "احصائيات", "إحصائيات", "stats", "statistics")),
    ("search", ("بحث", "يبحث", "search", "دور على")),
    ("pay", ("دفع", "يدفع", "pay", "payment", "سداد")),
    ("support", ("دعم", "support", "تذكرة", "شكاوى", "شكوى")),
    ("delivery", ("توصيل", "delivery", "توصيل طلبات")),
    ("shipping", ("شحن", "shipping")),
    ("profile", ("ملف", "profile", "ملف شخصي")),
    ("settings", ("اعدادات", "إعدادات", "settings")),
    ("cancel", ("الغاء", "إلغاء", "cancel")),
    ("confirm", ("تاكيد", "تأكيد", "confirm")),
    ("subscribe", ("اشتراك", "subscribe")),
    ("invite", ("دعوة", "invite")),
    ("balance", ("رصيد", "balance", "محفظة")),
    ("rate", ("تقييم", "rate", "review")),
    ("invoice", ("فاتورة", "invoice")),
    ("notifications", ("اشعار", "إشعار", "اشعارات", "إشعارات", "notification")),
    ("customer", ("عميل", "عملاء", "customer", "client", "clients")),
    ("driver", ("سائق", "سائقين", "driver", "drivers")),
    ("product", ("منتج", "منتجات", "صنف", "اصناف", "product", "item")),
    ("appointment", ("موعد", "مواعيد", "appointment")),
    ("task", ("مهمة", "مهام", "task")),
    ("name", ("اسم", "الاسم", "name")),
    ("phone", ("هاتف", "موبايل", "تليفون", "جوال", "phone", "mobile", "رقم")),
    ("address", ("عنوان", "العنوان", "address")),
    ("email", ("ايميل", "بريد", "email")),
    ("status", ("حالة", "الحالة", "status")),
    ("date", ("تاريخ", "date")),
    ("time", ("وقت", "time", "ساعة")),
    ("notes", ("ملاحظات", "notes", "ملاحظة")),
    ("price", ("سعر", "price")),
    ("quantity", ("كمية", "quantity", "عدد")),
    ("title", ("عنوان", "title")),
    ("description", ("وصف", "description")),
]


def _phrase_in_text(phrase: str, original: str, original_n: str) -> bool:
    p = (phrase or "").strip()
    if not p:
        return False
    if p in original or _norm(p) in original_n:
        return True
    # flexible whitespace
    pat = re.escape(_norm(p)).replace(r"\ ", r"\s+")
    if re.search(pat, original_n):
        return True
    return False


def _grounded_token(token: str, original: str, original_n: str, evidence: str = "") -> bool:
    """True if token/evidence is supported by user text (synonyms allowed)."""
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
    # synonym table
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
    # multi-part: register_customer
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


def _parse_json(content: str) -> dict[str, Any] | None:
    content = (content or "").strip()
    if not content:
        return None
    # strip markdown fences if any
    content = re.sub(r"^```(?:json)?\s*", "", content)
    content = re.sub(r"\s*```$", "", content)
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


def _as_cmd_list(raw: Any) -> list[dict[str, Any]]:
    out = []
    for c in raw or []:
        if isinstance(c, str):
            n = re.sub(r"[^a-z0-9_]", "", c.lower().lstrip("/"))
            if n:
                out.append({"name": n, "description": n, "admin_only": False, "evidence": ""})
        elif isinstance(c, dict):
            out.append(c)
    return out


def _as_button_list(raw: Any) -> list[dict[str, str]]:
    out = []
    for b in raw or []:
        if isinstance(b, str):
            out.append({"label": b.strip(), "evidence": b.strip()})
        elif isinstance(b, dict):
            lab = str(b.get("label") or b.get("text") or "").strip()
            if lab:
                out.append({"label": lab, "evidence": str(b.get("evidence") or lab)})
    return out


def _as_entity_list(raw: Any) -> list[dict[str, Any]]:
    out = []
    for e in raw or []:
        if isinstance(e, str):
            out.append({"name": e, "fields": [], "evidence": e})
        elif isinstance(e, dict):
            out.append(e)
    return out


def _as_rule_list(raw: Any) -> list[dict[str, str]]:
    out = []
    for r in raw or []:
        if isinstance(r, str):
            out.append({"text": r, "evidence": r[:80]})
        elif isinstance(r, dict):
            tx = str(r.get("text") or r.get("rule") or "").strip()
            if tx:
                out.append({"text": tx, "evidence": str(r.get("evidence") or tx[:80])})
    return out


def ground_spec(data: dict[str, Any], original: str) -> tuple[dict[str, Any], dict[str, list[str]]]:
    """Keep only surfaces supported by user text (evidence + synonyms)."""
    raw = original or ""
    text_n = _norm(raw)
    dropped: dict[str, list[str]] = {
        "commands": [], "entities": [], "fields": [], "buttons": [], "rules": [], "flows": [],
    }
    out: dict[str, Any] = {
        "bot_name": "",
        "commands": [],
        "buttons": [],
        "entities": [],
        "rules": [],
        "flows": [],
        "needs_clarification": bool(data.get("needs_clarification")),
        "clarification_questions": [
            str(q) for q in (data.get("clarification_questions") or []) if str(q).strip()
        ][:5],
        "notes": str(data.get("fidelity_notes") or data.get("notes") or "")[:300],
    }

    name = str(data.get("bot_name") or "").strip()
    if name:
        # Accept name if appears in text OR user used باسم/اسمه pattern OR short proper token
        if (
            _phrase_in_text(name, raw, text_n)
            or re.search(
                r"(?:باسم|اسمه|اسمها|اسم البوت)\s*" + re.escape(name),
                raw,
                re.I,
            )
            or (2 <= len(name) <= 40 and re.search(r"(?:باسم|اسمه|اسمها|named)", raw, re.I))
        ):
            out["bot_name"] = name[:48]
        elif 2 <= len(name) <= 40:
            # soft keep — translator often isolates the name correctly
            out["bot_name"] = name[:48]

    for c in _as_cmd_list(data.get("commands")):
        n = re.sub(r"[^a-z0-9_]", "", str(c.get("name") or "").lower().lstrip("/"))
        desc = str(c.get("description") or "")[:120]
        evidence = str(c.get("evidence") or "")[:120]
        if not n or n in ("start", "help", "http", "https"):
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
                "evidence": evidence,
            })
        else:
            dropped["commands"].append(n)

    kept_cmd_names = {c["name"] for c in out["commands"]}
    kept_descs = {_norm(c.get("description") or "") for c in out["commands"]}

    for b in _as_button_list(data.get("buttons")):
        label = b["label"][:48]
        evidence = b.get("evidence") or label
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

    # If no buttons but we have commands — structural buttons from descriptions (1:1)
    if not out["buttons"] and out["commands"]:
        for c in out["commands"]:
            lab = (c.get("description") or c["name"]).strip()[:40]
            if lab and lab not in out["buttons"]:
                out["buttons"].append(lab)

    soft_fields = {
        "id", "name", "phone", "status", "user_id", "address", "email",
        "date", "time", "notes", "title", "description", "price", "quantity",
    }

    for e in _as_entity_list(data.get("entities")):
        en_raw = str(e.get("name") or "")
        en = re.sub(r"[^A-Za-z0-9_]", "", en_raw)
        if not en or len(en) < 2:
            continue
        evidence = str(e.get("evidence") or "")[:120]
        entity_ok = (
            _grounded_token(en, raw, text_n, evidence)
            or _grounded_token(en.lower(), raw, text_n, evidence)
            or (evidence and _phrase_in_text(evidence, raw, text_n))
        )
        fields_in = e.get("fields") or []
        fields_out: list[str] = []
        for f in fields_in:
            fs = re.sub(r"[^a-z0-9_]", "", str(f).lower())
            if not fs:
                continue
            if fs == "id" or _grounded_token(fs, raw, text_n) or (entity_ok and fs in soft_fields):
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
            "fields": fields_out[:8],
            "evidence": evidence,
        })

    for r in _as_rule_list(data.get("rules")):
        rs = r["text"].strip()
        if not rs or len(rs) > 240:
            continue
        ev = r.get("evidence") or ""
        toks = [t for t in re.split(r"\s+", rs) if len(t) >= 3][:8]
        hit = sum(1 for t in toks if _norm(t) in text_n or t in raw)
        if (ev and _phrase_in_text(ev, raw, text_n)) or (toks and hit >= max(1, len(toks) // 2)):
            out["rules"].append(rs)
        else:
            dropped["rules"].append(rs[:40])

    for fl in data.get("flows") or []:
        if not isinstance(fl, dict):
            continue
        cmd = re.sub(r"[^a-z0-9_]", "", str(fl.get("command") or "").lower())
        if cmd not in kept_cmd_names:
            dropped["flows"].append(cmd or "?")
            continue
        steps = []
        for s in fl.get("steps") or []:
            ss = re.sub(r"[^a-z0-9_]", "", str(s).lower())
            if ss and ss not in steps:
                steps.append(ss)
        if steps:
            out["flows"].append({"command": cmd, "steps": steps[:6]})

    if len(out["commands"]) == 0 and not out["needs_clarification"]:
        if len(raw.strip()) < 60:
            out["needs_clarification"] = True
            if not out["clarification_questions"]:
                out["clarification_questions"] = [
                    "البوت بيعمل إيه؟ اكتب الوظائف بجمل قصيرة",
                    "في بيانات تتسجل (اسم، هاتف، عنوان…)؟",
                ]

    return out, dropped


def spec_to_text(data: dict[str, Any], original: str) -> str:
    """Canonical sectioned text for the formal engine."""
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
            fields = [f for f in (e.get("fields") or []) if f]
            if fields:
                lines.append(f"{en} ({', '.join(str(f) for f in fields)})")
            else:
                lines.append(str(en))

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

    # Always append original — formal grounding + extractor can still see user words
    lines.append("")
    lines.append("--- المصدر ---")
    lines.append((original or "")[:4000])
    return "\n".join(lines)


def _call_model(client: Any, model: str, messages: list[dict[str, str]]) -> str:
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "web_search": False,
    }
    # Best-effort low temperature for fidelity
    for extra in (
        {"temperature": 0},
        {"temperature": 0.1},
        {},
    ):
        try:
            response = client.chat.completions.create(**kwargs, **extra)
            if response and response.choices:
                return (response.choices[0].message.content or "").strip()
            return ""
        except TypeError:
            continue
        except Exception:
            raise
    return ""


def _translate_once(client: Any, model: str, text: str) -> dict[str, Any] | None:
    messages = [
        {"role": "system", "content": _SYSTEM},
        {
            "role": "user",
            "content": (
                "ترجم الوصف التالي إلى JSON المواصفة بدقة 100% حسب القواعد.\n"
                "استخرج كل الوظائف المذكورة. ممنوع الاختراع.\n"
                "أضف evidence لكل عنصر من كلام المستخدم.\n\n"
                f"نص المستخدم:\n{text[:7000]}"
            ),
        },
    ]
    content = _call_model(client, model, messages)
    return _parse_json(content)


def _repair_once(
    client: Any,
    model: str,
    original: str,
    data: dict[str, Any],
) -> dict[str, Any] | None:
    payload = json.dumps(data, ensure_ascii=False)[:8000]
    messages = [
        {"role": "system", "content": _REPAIR_SYSTEM},
        {
            "role": "user",
            "content": (
                f"النص الأصلي:\n{original[:5000]}\n\n"
                f"JSON الحالي:\n{payload}\n\n"
                "أرجع JSON المصحح فقط."
            ),
        },
    ]
    content = _call_model(client, model, messages)
    return _parse_json(content)


def translate_spec(user_text: str, *, timeout: int | None = None) -> TranslatorResult:
    text = (user_text or "").strip()
    if not text:
        return TranslatorResult(ok=False, error="empty")
    if not _enabled():
        return TranslatorResult(ok=False, error="disabled")

    timeout = timeout if timeout is not None else int(
        os.environ.get("SPEC_TRANSLATOR_TIMEOUT", "20")
    )
    forced = (os.environ.get("SPEC_TRANSLATOR_MODEL") or "").strip()
    candidates = (forced,) if forced else _MODEL_CANDIDATES

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
        try:
            data = _translate_once(client, model, text)
            if not data:
                last_err = f"bad_json:{model}"
                continue

            fidelity_pass = False
            if _repair_enabled() and (time.perf_counter() - t0) < timeout - 3:
                repaired = _repair_once(client, model, text, data)
                if repaired and isinstance(repaired.get("commands"), list):
                    data = repaired
                    fidelity_pass = True

            grounded, dropped = ground_spec(data, text)
            structured = spec_to_text(grounded, text)
            elapsed = (time.perf_counter() - t0) * 1000
            logger.info(
                "spec_translator ok model=%s cmds=%s dropped=%s repair=%s ms=%.0f",
                model,
                len(grounded.get("commands") or []),
                dropped.get("commands"),
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


def prepare_formal_text(user_text: str) -> tuple[str, TranslatorResult]:
    original = user_text or ""
    if not _enabled():
        return original, TranslatorResult(ok=False, error="disabled")
    result = translate_spec(original)
    if result.ok and result.structured_text.strip():
        return result.structured_text, result
    return original, result
