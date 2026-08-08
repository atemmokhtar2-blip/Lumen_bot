"""
SpecTranslator — speech → structured specification (translate only, never code).

Paths:
  1) Optional HuggingFace JSON translation when HF_TOKEN is set
  2) Deterministic structural translation (always available)

Supports multi-step flows, entities/relations, catalog→order conversation.
Formal engine remains the only code generator.
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


@dataclass
class TranslatorResult:
    ok: bool = False
    structured_text: str = ""
    grounded_json: dict[str, Any] = field(default_factory=dict)
    model_used: str = ""
    error: str = ""
    elapsed_ms: float = 0.0
    needs_clarification: bool = False
    clarification_questions: list[str] = field(default_factory=list)
    dropped: dict[str, Any] = field(default_factory=dict)
    path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "structured_text": self.structured_text[:2000],
            "grounded_json": self.grounded_json,
            "model_used": self.model_used,
            "error": self.error,
            "elapsed_ms": self.elapsed_ms,
            "needs_clarification": self.needs_clarification,
            "clarification_questions": list(self.clarification_questions or []),
            "dropped": self.dropped,
            "path": self.path,
        }


def chunk_long_text(text: str, max_chunk_size: int = 2000) -> list[str]:
    if len(text) <= max_chunk_size:
        return [text]
    paragraphs = text.split("\n")
    chunks: list[str] = []
    current = ""
    for p in paragraphs:
        if len(current) + len(p) + 1 > max_chunk_size:
            if current:
                chunks.append(current.strip())
            current = p
        else:
            current = current + "\n" + p if current else p
    if current:
        chunks.append(current.strip())
    return chunks


def merge_spec_json(specs: list[dict[str, Any]]) -> dict[str, Any]:
    if not specs:
        return {}
    if len(specs) == 1:
        return specs[0]
    master = dict(specs[0])
    seen_c = {c.get("name") for c in master.get("commands", []) if isinstance(c, dict)}
    seen_e = {e.get("name") for e in master.get("entities", []) if isinstance(e, dict)}
    seen_b = {(b.get("label") if isinstance(b, dict) else str(b)) for b in master.get("buttons", [])}
    for s in specs[1:]:
        if not isinstance(s, dict):
            continue
        for cmd in s.get("commands") or []:
            if isinstance(cmd, dict) and cmd.get("name") not in seen_c:
                master.setdefault("commands", []).append(cmd)
                seen_c.add(cmd.get("name"))
        for ent in s.get("entities") or []:
            if isinstance(ent, dict) and ent.get("name") not in seen_e:
                master.setdefault("entities", []).append(ent)
                seen_e.add(ent.get("name"))
        for btn in s.get("buttons") or []:
            lab = btn.get("label") if isinstance(btn, dict) else str(btn)
            if lab and lab not in seen_b:
                master.setdefault("buttons", []).append(btn if isinstance(btn, dict) else {"label": lab})
                seen_b.add(lab)
        for fl in s.get("flows") or []:
            master.setdefault("flows", []).append(fl)
    return master


_ITEM_HINTS = (
    "يظهر له", "يظهرلها", "يظهر", "الاصناف", "الأصناف", "اصناف", "أصناف",
    "المنتجات", "منتجات", "القائمة", "menu", "items", "categories",
)
_BTN_PATTERNS = (
    r"يدوس على زر\s*(?P<label>[^\n]{2,48})",
    r"الضغط على زر\s*(?P<label>[^\n]{2,48})",
    r"زر\s*[«\"']?(?P<label>[^\n«\"']{2,40})[»\"']?",
)


def _norm(s: str) -> str:
    s = (s or "").strip()
    s = s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ة", "ه").replace("ى", "ي")
    return re.sub(r"\s+", " ", s).lower()


def _slug(label: str) -> str:
    n = _norm(label)
    mapping = [
        (("عرض جميع الاصناف", "عرض الاصناف", "كل الاصناف", "جميع الاصناف"), "show_categories"),
        (("عرض المنتجات", "كل المنتجات"), "show_products"),
        (("القائمه", "قائمه الطعام", "المنيو", "menu"), "menu"),
        (("حظر",), "ban"), (("طرد",), "kick"), (("كتم",), "mute"),
        (("تسجيل",), "register"), (("تتبع",), "track"),
    ]
    for keys, cmd in mapping:
        if any(k in n for k in keys):
            return cmd
    try:
        from telegram_bot_engine.formal_engine.ontology.telegram_capabilities import (
            commands_from_capability_evidence,
        )
        ev = commands_from_capability_evidence(label)
        if ev:
            return ev[0][0]
    except Exception:
        pass
    return "action"


def _extract_button_labels(text: str) -> list[str]:
    found, seen = [], set()
    for pat in _BTN_PATTERNS:
        for m in re.finditer(pat, text, re.I):
            lab = re.sub(r"\s+", " ", m.group("label").strip().rstrip(":.،,"))
            lab = re.split(r"\s+(?:يظهر|يفتح|يعرض)\b", lab, maxsplit=1)[0].strip()
            if 2 <= len(lab) <= 48 and lab not in seen:
                seen.add(lab)
                found.append(lab)
    return found


def _extract_item_list(text: str) -> list[str]:
    lines = [ln.strip() for ln in (text or "").splitlines()]
    items, capture = [], False
    for ln in lines:
        if not ln:
            if capture and items:
                break
            continue
        n = _norm(ln)
        if any(h in n for h in _ITEM_HINTS) or "يظهر له" in n:
            capture = True
            continue
        if capture:
            if ln.endswith(":") or ln.startswith("/") or re.match(r"^(الأوامر|الازرار|الأزرار|الكيانات)", ln):
                break
            body = re.sub(r"^[\-•*\d\)\.\s]+", "", ln).strip()
            if 1 < len(body) <= 32 and not re.search(r"(اعمل|بوت|يدوس|زر)", body):
                items.append(body)
            elif items and len(body) > 40:
                break
    return items[:30]


def structural_translate(user_text: str) -> dict[str, Any]:
    text = (user_text or "").strip()
    spec: dict[str, Any] = {
        "bot_name": "", "commands": [], "buttons": [], "entities": [], "rules": [], "flows": [],
    }
    m = re.search(
        r"(?:باسم|اسمه|اسم البوت)\s*[«\"']?([A-Za-z0-9\u0600-\u06FF][A-Za-z0-9\u0600-\u06FF \-_]{1,40})",
        text, re.I,
    )
    if m:
        spec["bot_name"] = m.group(1).strip()[:48]

    seen: set[str] = set()
    for m in re.finditer(
        r"/(?P<cmd>[a-zA-Z][a-zA-Z0-9_]{1,32})\b\s*[-–—:：]?\s*(?P<desc>[^\n/]{0,80})", text
    ):
        name = m.group("cmd").lower()
        if name in seen:
            continue
        seen.add(name)
        spec["commands"].append({"name": name, "description": (m.group("desc") or name).strip()[:100]})

    for lab in _extract_button_labels(text):
        spec["buttons"].append({"label": lab})
        cmd = _slug(lab)
        if cmd not in seen and cmd != "action":
            seen.add(cmd)
            spec["commands"].append({"name": cmd, "description": lab[:100]})

    items = _extract_item_list(text)
    if items:
        spec["entities"].append({"name": "Item", "fields": ["name"]})
        spec["entities"].append({"name": "Order", "fields": ["item_name", "quantity", "status"]})
        for it in items:
            spec["buttons"].append({"label": it})
        if "show_categories" not in seen and "menu" not in seen:
            desc = next(
                (b["label"] for b in spec["buttons"]
                 if "اصناف" in _norm(b.get("label", "")) or "منتجات" in _norm(b.get("label", ""))),
                "عرض الأصناف",
            )
            seen.add("show_categories")
            spec["commands"].append({"name": "show_categories", "description": desc[:100]})
            if not any("اصناف" in _norm(b.get("label", "")) for b in spec["buttons"]):
                spec["buttons"].insert(0, {"label": desc})
        if "order" not in seen:
            seen.add("order")
            spec["commands"].append({"name": "order", "description": "طلب صنف بالكمية"})
        spec["flows"].append({
            "id": "order",
            "command": "order",
            "entity": "Order",
            "kind": "collect",
            "steps": [
                {"key": "quantity", "prompt": "أرسل الكمية المطلوبة (رقم)"},
                {"key": "confirm", "prompt": "للتأكيد اكتب: نعم — للإلغاء اكتب: لا"},
            ],
            "prefill_from_button": "item_name",
        })
        spec["rules"].append("عند اختيار صنف من الأزرار يبدأ تدفق الطلب: كمية ثم تأكيد")

    try:
        from telegram_bot_engine.formal_engine.ontology.telegram_capabilities import (
            commands_from_capability_evidence,
        )
        for cmd, _caps, desc in commands_from_capability_evidence(text):
            if cmd not in seen:
                seen.add(cmd)
                spec["commands"].append({"name": cmd, "description": desc, "admin_only": True})
    except Exception:
        pass

    if "start" not in seen:
        spec["commands"].insert(0, {"name": "start", "description": "تشغيل البوت"})
        seen.add("start")
    if "help" not in seen:
        spec["commands"].append({"name": "help", "description": "المساعدة"})
    return spec


def _spec_to_sectioned_text(data: dict[str, Any], original: str) -> str:
    lines: list[str] = []
    name = str(data.get("bot_name") or "").strip()
    if name:
        lines.append(f"اعمل بوت تليجرام باسم {name}")
    else:
        first = (original or "").strip().splitlines()[0][:200] if original else "اعمل بوت تليجرام"
        lines.append(first)

    cmds = data.get("commands") or []
    if isinstance(cmds, list) and cmds:
        lines.append("")
        lines.append("الأوامر:")
        for c in cmds:
            if not isinstance(c, dict):
                continue
            nme = str(c.get("name") or "").strip().lstrip("/").replace(" ", "_")
            if not nme:
                continue
            desc = str(c.get("description") or nme).strip()
            if c.get("admin_only") and "أدمن" not in desc:
                desc = f"{desc} (أدمن)"
            lines.append(f"/{nme} - {desc}")

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

    flows = data.get("flows") or []
    if isinstance(flows, list) and flows:
        lines.append("")
        lines.append("التدفقات:")
        for fl in flows:
            if not isinstance(fl, dict):
                continue
            fid = str(fl.get("id") or fl.get("command") or "flow").strip()
            steps = fl.get("steps") or []
            keys = [str(st.get("key")) for st in steps if isinstance(st, dict) and st.get("key")]
            ent = str(fl.get("entity") or "").strip()
            line = f"- {fid}"
            if ent:
                line += f" @{ent}"
            if keys:
                line += " : " + ", ".join(keys)
            lines.append(line)
            for st in steps:
                if isinstance(st, dict) and st.get("key") and st.get("prompt"):
                    lines.append(f"  • {st['key']}: {st['prompt']}")

    rules = data.get("rules") or []
    if isinstance(rules, list) and rules:
        lines.append("")
        lines.append("القواعد:")
        for r in rules:
            if isinstance(r, str) and r.strip():
                lines.append(f"- {r.strip()}")

    return "\n".join(lines).strip() + "\n"


_HF_SYSTEM = (
    "Convert bot descriptions to JSON only (no code). "
    "Schema: bot_name, commands[{name,description,admin_only}], buttons[{label}], "
    "entities[{name,fields}], flows[{id,command,entity,steps[{key,prompt}]}], rules[]. "
    "Use only evidenced features. Menu items become buttons. Multi-step orders use flows."
)


def _hf_translate(text: str, timeout: int) -> TranslatorResult:
    t0 = time.perf_counter()
    try:
        from .hf_provider import chat, enabled
        if not enabled():
            return TranslatorResult(ok=False, error="HF_TOKEN not configured", path="hf")
        content, model = chat(
            [{"role": "system", "content": _HF_SYSTEM}, {"role": "user", "content": text[:6000]}],
            timeout=timeout, max_tokens=2000, temperature=0.0, json_mode=True,
        )
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            m = re.search(r"\{[\s\S]*\}", content or "")
            data = json.loads(m.group(0)) if m else None
        if not isinstance(data, dict) or not isinstance(data.get("commands"), list) or not data.get("commands"):
            raise ValueError("invalid_or_empty_spec")
        return TranslatorResult(
            ok=True,
            structured_text=_spec_to_sectioned_text(data, text),
            grounded_json=data,
            model_used=f"huggingface:{model}",
            elapsed_ms=round((time.perf_counter() - t0) * 1000, 1),
            path="hf",
        )
    except Exception as exc:
        return TranslatorResult(
            ok=False, error=f"{type(exc).__name__}:{exc}"[:800],
            elapsed_ms=round((time.perf_counter() - t0) * 1000, 1), path="hf",
        )


def translate_spec(user_text: str, *, timeout: int | None = None) -> TranslatorResult:
    text = (user_text or "").strip()
    t0 = time.perf_counter()
    if not text:
        return TranslatorResult(
            ok=False, error="empty_text", needs_clarification=True,
            clarification_questions=["اكتب وصف البوت والأوامر أو الأزرار المطلوبة."],
            path="passthrough",
        )
    timeout = timeout if timeout is not None else int(os.environ.get("SPEC_TRANSLATOR_TIMEOUT", "25"))
    use_hf = os.environ.get("SPEC_TRANSLATOR", "1").strip() not in ("0", "false", "off")
    hf_result = None
    if use_hf and os.environ.get("HF_TOKEN", "").strip():
        hf_result = _hf_translate(text, timeout=timeout)
        if hf_result.ok and hf_result.structured_text.strip():
            return hf_result

    spec = structural_translate(text)
    structured = _spec_to_sectioned_text(spec, text)
    meaningful = [c for c in (spec.get("commands") or []) if isinstance(c, dict) and c.get("name") not in ("start", "help")]
    ok = bool(meaningful or (spec.get("buttons") or []))
    return TranslatorResult(
        ok=ok,
        structured_text=structured if ok else text,
        grounded_json=spec,
        model_used="structural",
        elapsed_ms=round((time.perf_counter() - t0) * 1000, 1),
        path="structural",
        error=(hf_result.error if hf_result and not hf_result.ok else ""),
        needs_clarification=not ok,
        clarification_questions=(
            [] if ok else ["المستخدم هيقدر يعمل إيه؟ اكتب أوامر أو أزرار أو قائمة أصناف بشكل واضح."]
        ),
    )


def prepare_formal_text(user_text: str) -> tuple[str, TranslatorResult]:
    tr = translate_spec(user_text)
    if tr.ok and tr.structured_text.strip():
        return tr.structured_text, tr
    return (user_text or "").strip(), tr
