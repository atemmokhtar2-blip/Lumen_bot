"""
SpecTranslator — human speech → structured specification ONLY.

Hard constraints:
  - TRANSLATE only. Never write code. Never invent features or domains.
  - AI path: Groq primary (GROQ_API_KEY), Hugging Face optional fallback.
  - Structural extraction is NOT used on the generation path.
  - Every field is grounded against the original user text.
  - Formal engine is the ONLY code generator.

No domain templates. No g4f. No command renaming.
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
    r"(?<!\w)زر\s+[«\"']?(?P<label>[^\n«\"']{2,40})[»\"']?",
)


def _norm(s: str) -> str:
    s = (s or "").strip()
    s = s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ة", "ه").replace("ى", "ي")
    return re.sub(r"\s+", " ", s).lower()


def _slug(label: str) -> str:
    """Deterministic slug from label text only — no domain template mapping."""
    lab = (label or "").strip()
    if re.match(r"^[a-zA-Z][a-zA-Z0-9_]{1,32}$", lab):
        return lab.lower()
    parts = re.findall(r"[a-zA-Z0-9]+", lab)
    if parts:
        stem = "_".join(p.lower() for p in parts)[:32]
        if stem and re.match(r"^[a-z][a-z0-9_]{0,32}$", stem):
            return stem
    import hashlib
    h = hashlib.sha1(lab.encode("utf-8")).hexdigest()[:8]
    return f"act_{h}"


def _extract_button_labels(text: str) -> list[str]:
    """Extract button labels from user text only — never invent labels."""
    found, seen = [], set()
    for pat in _BTN_PATTERNS:
        for m in re.finditer(pat, text, re.I):
            lab = re.sub(r"\s+", " ", m.group("label").strip().rstrip(":.،,"))
            lab = re.split(r"\s+(?:يظهر|يفتح|يعرض)\b", lab, maxsplit=1)[0].strip()
            if 2 <= len(lab) <= 48 and lab not in seen:
                seen.add(lab)
                found.append(lab)

    section_headers = ("الازرار", "الأزرار", "buttons", "القائمة الرئيسية")
    lines = (text or "").splitlines()
    in_btn_section = False
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        n = _norm(s).rstrip(":")
        if any(n == _norm(h) or n.startswith(_norm(h)) for h in section_headers):
            in_btn_section = True
            continue
        if in_btn_section and any(
            n.startswith(_norm(h)) for h in (
                "الاوامر", "الأوامر", "commands", "الكيانات", "entities",
                "القواعد", "rules", "التدفقات", "flows",
            )
        ):
            in_btn_section = False
            continue
        if not in_btn_section:
            if re.match(r"^[➕📋✅❌🗑]\s*\S", s) and 2 <= len(s) <= 40:
                lab = re.sub(r"^[➕📋✅❌🗑]\s*", "", s).strip()
                if lab and lab not in seen and not lab.startswith("/"):
                    seen.add(lab)
                    found.append(lab)
            continue
        lab = re.sub(r"^[➕📋✅❌🗑•\-\*]\s*", "", s).strip()
        if re.match(r"^[A-Za-z][A-Za-z0-9_]*\s*\(", lab):
            continue
        if "(" in lab and ")" in lab and re.search(r"\bid\b|,", lab, re.I):
            continue
        if 2 <= len(lab) <= 48 and lab not in seen and not lab.startswith("/"):
            seen.add(lab)
            found.append(lab)
    return found


def _command_stem_from_label(label: str) -> str | None:
    """Derive command id from label words only — no domain packs / fixed stems."""
    lab = (label or "").strip()
    if not lab or len(lab) > 40:
        return None
    if re.match(r"^[a-zA-Z][a-zA-Z0-9_]{1,32}$", lab):
        return lab.lower()
    parts = re.findall(r"[a-zA-Z0-9]+", lab)
    if parts:
        stem = "_".join(p.lower() for p in parts)[:32]
        if stem and re.match(r"^[a-z][a-z0-9_]{0,32}$", stem) and stem not in _BLOCKED_CMD_NAMES:
            return stem
    return None


def _extract_item_list(text: str) -> list[str]:
    lines = [ln.strip() for ln in (text or "").splitlines()]
    items, capture = [], False
    for ln in lines:
        if not ln:
            if capture and items:
                break
            continue
        n = _norm(ln)
        if any(h in n for h in _ITEM_HINTS) or "يظهر له" in n or "الاصناف" in n or "الأصناف" in n or "منيو" in n:
            capture = True
            # inline list after colon on same line: الأصناف: بيتزا، برجر
            if ":" in ln or "：" in ln:
                tail = re.split(r"[:：]", ln, 1)[-1].strip()
                if tail and ("," in tail or "،" in tail):
                    for p in re.split(r"[,،]+", tail):
                        p = p.strip()
                        if 1 < len(p) <= 32:
                            items.append(p)
            continue
        if capture:
            if ln.endswith(":") or ln.startswith("/") or re.match(r"^(الأوامر|الازرار|الأزرار|الكيانات)", ln):
                break
            body = re.sub(r"^[\-•*\d\)\.\s]+", "", ln).strip()
            if 1 < len(body) <= 32 and not re.search(r"(اعمل|بوت|يدوس|زر|المستخدم|يختار|يدخل)", body):
                items.append(body)
            elif items and len(body) > 40:
                break
    # inline patterns anywhere: الأصناف: a، b، c
    if not items:
        for m in re.finditer(
            r"(?:الأصناف|الاصناف|المنتجات|المنيو|menu|items)\s*[:：]\s*([^\n]+)",
            text or "",
            re.I,
        ):
            for p in re.split(r"[,،]+", m.group(1)):
                p = p.strip()
                if 1 < len(p) <= 32 and p not in items:
                    items.append(p)
    return items[:30]


def _detect_ordered_steps(text: str) -> list[dict[str, str]]:
    """Detect multi-step conversation from sequencing phrases in user text."""
    t = text or ""
    n = _norm(t)
    steps: list[dict[str, str]] = []

    # Explicit: الاسم ثم الهاتف ثم العنوان
    m = re.search(
        r"(?:الاسم|name)\s*(?:ثم|بعدين|ثمّ|ثم\s+بعدين|,|،)\s*(?:الهاتف|الجوال|phone|رقم)?"
        r".{0,20}?(?:ثم|بعدين|,|،)\s*(?:العنوان|address)?",
        t,
        re.I,
    )
    # Field sequence with ثم / بعدين
    parts = re.split(r"\s*(?:ثم|بعدين|وبعدين|ثمّ)\s*", t)
    if len(parts) >= 2:
        field_map = [
            (r"اسم|name", "name", "أرسل الاسم"),
            (r"هاتف|جوال|phone|رقم", "phone", "أرسل رقم الهاتف"),
            (r"عنوان|address", "address", "أرسل العنوان"),
            (r"كمي|quantity|عدد", "quantity", "أرسل الكمية المطلوبة (رقم)"),
            (r"تأكيد|confirm|يؤكد", "confirm", "للتأكيد اكتب: نعم — للإلغاء اكتب: لا"),
            (r"بريد|ايميل|email", "email", "أرسل البريد الإلكتروني"),
            (r"ملاحظ|notes", "notes", "أرسل الملاحظات"),
            (r"تاريخ|date", "date", "أرسل التاريخ"),
            (r"وقت|time", "time", "أرسل الوقت"),
        ]
        for part in parts:
            pn = _norm(part)
            for pat, key, prompt in field_map:
                if re.search(pat, pn) and not any(s["key"] == key for s in steps):
                    steps.append({"key": key, "prompt": prompt})
                    break

    # Phrase: يختار صنف ... يدخل الكمية ... يؤكد
    if re.search(r"يختار\s*صنف|اختيار\s*صنف|من\s*المنيو", n):
        if not any(s["key"] == "quantity" for s in steps) and re.search(r"كمي", n):
            steps.append({"key": "quantity", "prompt": "أرسل الكمية المطلوبة (رقم)"})
        if not any(s["key"] == "confirm" for s in steps) and re.search(r"يؤكد|تأكيد|confirm", n):
            steps.append({"key": "confirm", "prompt": "للتأكيد اكتب: نعم — للإلغاء اكتب: لا"})

    # Ensure quantity→confirm order for order-like
    if any(s["key"] == "quantity" for s in steps) and not any(s["key"] == "confirm" for s in steps):
        if re.search(r"تأكيد|يؤكد|confirm", n):
            steps.append({"key": "confirm", "prompt": "للتأكيد اكتب: نعم — للإلغاء اكتب: لا"})

    return steps[:8]





def _extract_dynamic_tools(text: str) -> list[dict[str, Any]]:
    """
    Build tool specs fresh from THIS user text only.
    No saved product catalog — each request recomputes tools from wording.
    """
    tools: list[dict[str, Any]] = []
    seen: set[str] = set()
    blob = text or ""
    n = _norm(blob)

    # Bullet / line items that look like checks or tools
    line_pats = [
        r"(?m)^[\s•\-\*\d\.\)➕📧🌐🔐📊🔍]+\s*(?P<title>[A-Za-z\u0600-\u06FF][^\n]{2,60})$",
        r"(?i)(?:فحص|أداة|اداة|check|scan|tool|module)\s*[:=：\-]?\s*(?P<title>[^\n]{3,60})",
    ]
    candidates: list[str] = []
    for pat in line_pats:
        for m in re.finditer(pat, blob):
            title = re.sub(r"\s+", " ", m.group("title")).strip().rstrip(":.،,")
            if 3 <= len(title) <= 60:
                candidates.append(title)

    # Phrase evidence → tool (keywords must appear in THIS text)
    phrase_tools = [
        (("dns", "سجلات dns", "dns records"), "dns_lookup", "domain", "DNS records"),
        (("mx", "mx records", "سجلات mx"), "mx_lookup", "domain", "MX records"),
        (("spf",), "spf_check", "domain", "SPF"),
        (("dmarc",), "dmarc_check", "domain", "DMARC"),
        (("tls", "ssl", "شهادة", "certificate"), "tls_info", "domain", "TLS/SSL"),
        (("http status", "status code", "حالة http"), "http_status", "url", "HTTP status"),
        (("security headers", "هيدرز", "hsts", "csp", "رؤوس"), "security_headers", "url", "Security headers"),
        (("whois", "ويز", "مالك الدومين"), "whois_lookup", "domain", "WHOIS"),
        (("robots.txt", "robots"), "robots_check", "url", "robots.txt"),
        (("openapi", "swagger"), "openapi_check", "url", "OpenAPI/Swagger"),
        (("sitemap", "خريطة الموقع"), "sitemap_check", "url", "Sitemap"),
        (("security.txt",), "security_txt", "url", "security.txt"),
        (("port", "منافذ"), "port_info", "domain", "Port info"),  # will be limited to common service banners only if implemented
        (("ping", "icmp"), "ping_check", "domain", "Ping"),
        (("pdf", "تقرير"), "report_pdf", "project", "PDF report"),
    ]
    for keys, tid, inp, title in phrase_tools:
        if any(_norm(k) in n or k.lower() in blob.lower() for k in keys):
            if tid not in seen:
                seen.add(tid)
                tools.append({
                    "id": tid,
                    "title": title,
                    "input": inp,
                    "source": "phrase",
                })

    # From dashboard-style titles
    for title in candidates:
        tn = _norm(title)
        tid = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")[:32] or "tool"
        if tid in seen or tid in ("start", "help"):
            continue
        # skip pure product-looking short food words without scan verbs
        inp = "domain"
        if any(k in tn for k in ("web", "site", "http", "url", "موقع", "robots", "sitemap")):
            inp = "url"
        if any(k in tn for k in ("report", "تقرير", "pdf")):
            inp = "project"
        if any(k in tn for k in ("password", "كلمة السر", "hash")):
            inp = "text"
        seen.add(tid)
        tools.append({"id": tid, "title": title[:60], "input": inp, "source": "line"})

    return tools[:24]


def _classify_tool_primitive(tool: dict[str, Any]) -> str:
    """Map one user-derived tool to a safe execution primitive (compositional, not a bot pack)."""
    blob = _norm(
        " ".join(str(tool.get(k) or "") for k in ("id", "title", "description", "input"))
    )
    if any(k in blob for k in ("dmarc",)):
        return "dns_txt_dmarc"
    if any(k in blob for k in ("spf",)):
        return "dns_txt_spf"
    if any(k in blob for k in ("mx",)):
        return "dns_mx"
    if any(k in blob for k in ("dns",)):
        return "dns_a"
    if any(k in blob for k in ("tls", "ssl", "شهاده", "certificate")):
        return "tls_cert"
    if any(k in blob for k in ("security header", "هيدرز", "hsts", "csp", "headers")):
        return "http_headers"
    if any(k in blob for k in ("http status", "status code", "حاله http")):
        return "http_status"
    if any(k in blob for k in ("robots",)):
        return "http_path:/robots.txt"
    if any(k in blob for k in ("sitemap",)):
        return "http_path:/sitemap.xml"
    if any(k in blob for k in ("security.txt",)):
        return "http_path:/.well-known/security.txt"
    if any(k in blob for k in ("whois",)):
        return "whois"
    if any(k in blob for k in ("ping",)):
        return "ping"
    if any(k in blob for k in ("pdf", "report", "تقرير")):
        return "report_text"
    if any(k in blob for k in ("password", "hash")):
        return "password_strength"
    return "echo_target"



def _entities_from_user_text(text: str) -> list[dict[str, Any]]:
    """Extract entities only from explicit user sections — no invented domain entities."""
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    section_headers = (
        "الكيانات", "كيانات", "entities", "النماذج", "نماذج البيانات",
        "data models", "models",
    )
    lines = (text or "").splitlines()
    capture = False
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        n = _norm(s)
        if any(_norm(h) == n.rstrip(":") or n.startswith(_norm(h)) for h in section_headers):
            capture = True
            continue
        if capture and any(
            n.startswith(_norm(h)) for h in (
                "الاوامر", "الأوامر", "commands", "الازرار", "الأزرار", "buttons",
                "القواعد", "rules", "التدفقات", "flows",
            )
        ):
            capture = False
            continue
        if not capture:
            continue
        body = re.sub(r"^[\-•\*]\s*", "", s).strip()
        m = re.match(
            r"^[«\"']?([A-Za-z][A-Za-z0-9_]{1,40})[»\"']?\s*"
            r"(?:[\(:：]\s*([^\)\n]{1,120})[\)]?)?",
            body,
        )
        if not m or (m.group(2) is None and "(" not in body and ":" not in body and "：" not in body):
            continue
        name = m.group(1)
        key = name.lower()
        if key in seen or len(name) < 2:
            continue
        seen.add(key)
        raw_fields = m.group(2) or ""
        fields = [f.strip() for f in re.split(r"[,،]+", raw_fields) if f.strip()]
        fields = [re.sub(r"[^a-zA-Z0-9_]", "", f) for f in fields]
        fields = [f for f in fields if f]
        found.append({"name": name[:1].upper() + name[1:], "fields": fields})
    for m in re.finditer(
        r"\b([A-Z][A-Za-z0-9_]{1,40})\s*\(\s*([a-zA-Z_][a-zA-Z0-9_]*(?:\s*,\s*[a-zA-Z_][a-zA-Z0-9_]*){0,12})\s*\)",
        text or "",
    ):
        name = m.group(1)
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        fields = [f.strip() for f in m.group(2).split(",") if f.strip()]
        found.append({"name": name, "fields": fields})
    return found


def structural_translate(user_text: str) -> dict[str, Any]:
    """Pure extraction from user text — no domain templates, no invented entities/commands."""
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
        r"(?m)(?:^|\s)/(?P<cmd>[a-zA-Z][a-zA-Z0-9_]{1,32})\b\s*[-–—:：]?\s*(?P<desc>[^\n/]{0,80})", text
    ):
        name = m.group("cmd").lower()
        if name in seen:
            continue
        seen.add(name)
        spec["commands"].append({
            "name": name,
            "description": (m.group("desc") or name).strip()[:100],
        })

    for lab in _extract_button_labels(text):
        if not any(b.get("label") == lab for b in spec["buttons"]):
            spec["buttons"].append({"label": lab})
        if not seen:
            stem = _command_stem_from_label(lab)
            if stem and stem not in seen and _valid_cmd_name(stem):
                seen.add(stem)
                spec["commands"].append({"name": stem, "description": lab, "admin_only": False})

    dyn_tools = _extract_dynamic_tools(text)
    if dyn_tools:
        spec["tools"] = dyn_tools

    for ent in _entities_from_user_text(text):
        if not any(e.get("name") == ent["name"] for e in spec["entities"]):
            spec["entities"].append(ent)

    create_cmds = [
        c.get("name") for c in spec["commands"]
        if isinstance(c, dict) and (
            str(c.get("name") or "").startswith(("new_", "add_", "create_"))
            or str(c.get("name") or "") in ("register", "new_client", "new_task", "order")
        )
    ]
    if create_cmds and re.search(
        r"(يطلب|اطلب|اكتب|كتابة|ادخل|أدخل|يجمع).{0,50}(مهم|نص|اسم|title|وصف|بريد|هاتف|كمية)",
        text or "",
        re.I,
    ):
        ordered = _detect_ordered_steps(text)
        steps = ordered if ordered else [{"key": "title", "prompt": "أرسل النص للحفظ:"}]
        for cn in create_cmds:
            if any(f.get("command") == cn for f in spec["flows"]):
                continue
            ent_name = ""
            for e in spec["entities"]:
                en = str(e.get("name") or "").lower()
                if en and (en in cn or cn.endswith(en)):
                    ent_name = e["name"]
                    break
            spec["flows"].append({
                "id": cn,
                "command": cn,
                "entity": ent_name,
                "kind": "collect",
                "steps": steps,
            })

    ordered = _detect_ordered_steps(text)
    if ordered and not spec.get("flows") and spec["commands"]:
        prefer = None
        for c in spec["commands"]:
            n = str(c.get("name") or "")
            if n in ("register",) or n.startswith(("new_", "add_", "create_")):
                prefer = n
                break
        if prefer is None:
            prefer = str(spec["commands"][0].get("name") or "start")
        if prefer not in ("start", "help"):
            ent_name = ""
            for e in spec["entities"]:
                en = str(e.get("name") or "").lower()
                if prefer.endswith(en) or en in prefer:
                    ent_name = e["name"]
                    break
            spec["flows"].append({
                "id": prefer,
                "command": prefer,
                "entity": ent_name,
                "kind": "collect",
                "steps": ordered,
            })

    slash_cmds = re.findall(r"(?m)(?:^|\s)/([A-Za-z][A-Za-z0-9_]{1,32})\b", text or "")
    dense_command_spec = len(slash_cmds) >= 6
    _catalog_evidence = any(
        k in _norm(text) for k in ("اصناف", "الأصناف", "منتجات", "المنتجات", "منيو", "menu items", "كتالوج")
    ) or bool(re.search(r"(يظهر له|الأصناف|الاصناف)\s*[:\n]", text or ""))
    if not dense_command_spec and _catalog_evidence:
        items = _extract_item_list(user_text)
        for it in items:
            if not any(b.get("label") == it for b in spec["buttons"]):
                spec["buttons"].append({"label": it})

    try:
        from telegram_bot_engine.formal_engine.ontology.telegram_capabilities import (
            commands_from_capability_evidence,
        )
        for cmd, _caps, desc in commands_from_capability_evidence(text):
            if cmd not in seen and _valid_cmd_name(cmd):
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



_HF_SYSTEM = """You are a SPEC TRANSLATOR only. You are NOT a coder and NOT a bot builder.

MISSION: Translate the user's natural-language description into a structured JSON specification.
You NEVER write code, never invent features, never complete missing domains.

OUTPUT: JSON object only. No markdown fences. No prose. No Python/JS/code.

Schema (use only keys that have evidence in the user text):
{
  "bot_name": "string from user or empty",
  "commands": [{"name": "exact_token", "description": "from user words", "admin_only": false}],
  "buttons": [{"label": "exact label from user"}],
  "entities": [{"name": "NameFromUser", "fields": ["field_from_user"]}],
  "flows": [{"id": "cmd", "command": "cmd", "entity": "EntityFromUser", "steps": [{"key": "field", "prompt": "short prompt from user intent"}]}],
  "rules": ["rule sentence from user"],
  "relations": [{"from": "A", "to": "B", "via": "field"}],
  "tools": [{"id": "id", "title": "title", "input": "input", "description": "desc"}]
}

ABSOLUTE CONSTRAINTS (violating any = invalid output):
1) TRANSLATE ONLY. Map human speech → structured fields. Do not design, expand, or improve the bot.
2) ZERO CODE. Never output def, class, import, async, handler, Application, or any programming syntax.
3) ZERO INVENTION. Every command name, button label, entity name, field, flow step, rule, and tool MUST be directly evidenced in the user text (literal token or clear paraphrase of the same phrase).
4) COMMAND NAMES: keep the user's exact latin ids when they wrote /new_task, /my_tasks, etc. Never rename (new_task must NOT become add).
5) If the user did not mention a command/entity/button, omit it. Empty lists are correct. Do not fill with start/help/order/catalog defaults.
6) admin_only=true only if the user said admin/أدمن/مشرف for that command.
7) Flows only when the user described a multi-step sequence; steps keys must match fields they mentioned.
8) No domain packs: no shop, delivery, tickets, school, hospital, or generic CRUD scaffolds.
9) If the text is too vague to extract actions, return {"bot_name":"","commands":[],"buttons":[],"entities":[],"flows":[],"rules":[],"relations":[],"tools":[]}.
10) JSON only.
"""



_CODE_MARKERS = (
    "def ", "class ", "import ", "from ", "async def", "await ",
    "Application.", "CommandHandler", "CallbackQueryHandler",
    "```python", "```js", "```javascript", "#!/usr", "module.exports",
)


def _looks_like_code(content: str) -> bool:
    """True if model response looks like source code instead of JSON spec."""
    s = content or ""
    if not s.strip():
        return False
    hits = sum(1 for m in _CODE_MARKERS if m in s)
    if hits >= 2:
        return True
    if re.search(r"^\s*(def|class|async def|import)\s+\w+", s, re.M):
        return True
    return False


def _token_evidenced(token: str, text_n: str, raw: str) -> bool:
    t = (token or "").strip()
    if not t:
        return False
    if re.search(rf"/{re.escape(t)}\b", raw, re.I):
        return True
    if re.search(rf"(?:^|[\s,|/]){re.escape(t)}(?:\s*[-–—:]|\s|$)", raw, re.I | re.M):
        return True
    tl = t.lower()
    if tl in text_n:
        return True
    parts = [p for p in tl.replace("-", "_").split("_") if len(p) >= 3]
    if len(parts) >= 2 and all(p in text_n for p in parts):
        return True
    return False


def _phrase_evidenced(phrase: str, text_n: str, raw: str) -> bool:
    p = (phrase or "").strip()
    if not p or len(p) < 2:
        return False
    if p in raw or _norm(p) in text_n:
        return True
    # allow short token overlap for multi-word labels
    toks = [t for t in re.split(r"\s+", _norm(p)) if len(t) >= 2]
    if len(toks) >= 2 and sum(1 for t in toks if t in text_n) >= max(1, len(toks) - 1):
        return True
    if len(toks) == 1 and toks[0] in text_n:
        return True
    return False


def _ground_spec_to_user_text(data: dict, user_text: str) -> dict:
    """Drop every AI field not evidenced in the original user text. Never invent.

    SpecTranslator may only keep what the human wrote. Formal engine builds code later.
    """
    if not isinstance(data, dict):
        return {
            "bot_name": "", "commands": [], "buttons": [], "entities": [],
            "flows": [], "rules": [], "relations": [], "tools": [],
        }
    raw = user_text or ""
    text_n = _norm(raw)
    out: dict = {
        "bot_name": "",
        "commands": [],
        "buttons": [],
        "entities": [],
        "flows": [],
        "rules": [],
        "relations": [],
        "tools": [],
    }

    bn = str(data.get("bot_name") or "").strip()
    if bn and _phrase_evidenced(bn, text_n, raw):
        out["bot_name"] = bn[:48]

    seen_c: set[str] = set()
    for c in data.get("commands") or []:
        if not isinstance(c, dict):
            continue
        name = _normalize_cmd_name(str(c.get("name") or ""))
        if not name or name in seen_c:
            continue
        desc = str(c.get("description") or "").strip()
        # Must be evidenced by /name, name token, or description phrase in user text
        if not (
            _token_evidenced(name, text_n, raw)
            or (desc and _phrase_evidenced(desc, text_n, raw))
        ):
            continue
        if not _valid_cmd_name(name) and name not in ("start", "help"):
            continue
        admin = bool(c.get("admin_only"))
        if admin and not any(k in text_n or k in raw for k in ("admin", "ادمن", "أدمن", "مشرف", "إدارة")):
            admin = False
        seen_c.add(name)
        out["commands"].append({
            "name": name,
            "description": (desc or name)[:100],
            "admin_only": admin,
        })

    seen_b: set[str] = set()
    for b in data.get("buttons") or []:
        lab = str(b.get("label") if isinstance(b, dict) else b or "").strip()
        if not lab or lab in seen_b:
            continue
        if not _phrase_evidenced(lab, text_n, raw):
            continue
        seen_b.add(lab)
        out["buttons"].append({"label": lab[:48]})

    seen_e: set[str] = set()
    for e in data.get("entities") or []:
        if not isinstance(e, dict):
            continue
        en = str(e.get("name") or "").strip()
        if not en or en.lower() in seen_e:
            continue
        if not _token_evidenced(en, text_n, raw) and not _phrase_evidenced(en, text_n, raw):
            continue
        fields_in = e.get("fields") or e.get("attributes") or []
        fields: list[str] = []
        if isinstance(fields_in, list):
            for f in fields_in:
                fs = str(f).strip()
                if not fs:
                    continue
                # field must appear in text or be structural id
                if fs.lower() in ("id",) or _token_evidenced(fs, text_n, raw) or _phrase_evidenced(fs, text_n, raw):
                    fields.append(re.sub(r"[^a-zA-Z0-9_]", "", fs)[:32])
        seen_e.add(en.lower())
        out["entities"].append({
            "name": en[:1].upper() + en[1:] if en else en,
            "fields": [f for f in fields if f][:16],
        })

    seen_f: set[str] = set()
    cmd_names = {c["name"] for c in out["commands"]}
    for f in data.get("flows") or []:
        if not isinstance(f, dict):
            continue
        cmd = _normalize_cmd_name(str(f.get("command") or f.get("id") or ""))
        if not cmd or cmd in seen_f:
            continue
        # Flow must attach to an evidenced command (or the command name itself in text)
        if cmd not in cmd_names and not _token_evidenced(cmd, text_n, raw):
            continue
        steps_in = f.get("steps") or []
        steps: list[dict] = []
        if isinstance(steps_in, list):
            for st in steps_in:
                if not isinstance(st, dict):
                    continue
                key = re.sub(r"[^a-zA-Z0-9_]", "", str(st.get("key") or "").lower())[:32]
                if not key or key in ("n_x", "x", "field", "value"):
                    continue
                # keep step if key or prompt evidenced, or key is common collect field already in entity fields
                prompt = str(st.get("prompt") or "").strip()[:120]
                if not (
                    _token_evidenced(key, text_n, raw)
                    or (prompt and _phrase_evidenced(prompt, text_n, raw))
                    or any(key in (e.get("fields") or []) for e in out["entities"])
                ):
                    continue
                steps.append({"key": key, "prompt": prompt or f"أرسل {key}"})
        if not steps:
            continue
        ent = str(f.get("entity") or "").strip()
        if ent and not any(e["name"].lower() == ent.lower() for e in out["entities"]):
            if not _token_evidenced(ent, text_n, raw):
                ent = ""
        seen_f.add(cmd)
        out["flows"].append({
            "id": cmd,
            "command": cmd,
            "entity": ent,
            "kind": "collect",
            "steps": steps[:12],
        })

    for r in data.get("rules") or []:
        rs = str(r).strip()
        if rs and _phrase_evidenced(rs, text_n, raw):
            out["rules"].append(rs[:200])

    for rel in data.get("relations") or []:
        if not isinstance(rel, dict):
            continue
        fr = str(rel.get("from") or "").strip()
        to = str(rel.get("to") or "").strip()
        via = str(rel.get("via") or "").strip()
        if fr and to and (
            _token_evidenced(fr, text_n, raw) or any(e["name"].lower() == fr.lower() for e in out["entities"])
        ) and (
            _token_evidenced(to, text_n, raw) or any(e["name"].lower() == to.lower() for e in out["entities"])
        ):
            out["relations"].append({"from": fr, "to": to, "via": via[:40]})

    for t in data.get("tools") or []:
        if not isinstance(t, dict):
            continue
        tid = str(t.get("id") or "").strip()
        title = str(t.get("title") or "").strip()
        blob = f"{tid} {title} {t.get('description') or ''}"
        if tid and (_phrase_evidenced(title or tid, text_n, raw) or _token_evidenced(tid, text_n, raw)):
            out["tools"].append({
                "id": re.sub(r"[^a-z0-9_]", "_", tid.lower())[:40],
                "title": title[:80] or tid,
                "input": str(t.get("input") or "")[:40],
                "description": str(t.get("description") or "")[:120],
            })

    return out


def _parse_spec_json(content: str) -> dict | None:
    if not content:
        return None
    try:
        data = json.loads(content)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", content)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None


def _hf_translate(text: str, timeout: int) -> TranslatorResult:
    """AI translate via Groq (primary) then Hugging Face. Returns grounded JSON only."""
    from . import groq_provider as groq
    from . import hf_provider as hf

    system = (
        "You are a strict specification translator for Telegram bots. "
        "Translate the user description into JSON only. "
        "Never invent domain packs. Only extract what the user described. "
        "Output a single JSON object with keys: "
        "bot_name, commands, buttons, entities, flows, rules, relations, tools. "
        "commands: [{name, description, admin_only}]. "
        "buttons: [{label}]. "
        "entities: [{name, fields}]. "
        "flows: [{command, steps:[{key,prompt}]}]. "
        "tools: [{id, title, input}]. "
        "Command names: lowercase snake_case ASCII. "
        "If the user lists a menu/board of labeled actions, put each as a button "
        "and also as a command (slug from the English/ASCII words in the label). "
        "Do not invent SSL/information commands from prose about certificates."
    )
    user_msg = f"USER DESCRIPTION:\n{text[:12000]}"
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_msg},
    ]
    max_tokens = int(os.environ.get("SPEC_TRANSLATOR_MAX_TOKENS", "3200"))
    errors: list[str] = []

    providers: list[tuple[str, Any]] = []
    if groq.enabled():
        providers.append(("groq", groq))
    if hf.enabled():
        providers.append(("hf", hf))
    if not providers:
        return TranslatorResult(
            ok=False,
            error="No AI provider configured (set GROQ_API_KEY or HF_TOKEN)",
            path="ai_missing",
        )

    content = ""
    model_used = ""
    path_used = ""
    for name, prov in providers:
        try:
            content, model_used = prov.chat(
                messages,
                timeout=timeout,
                max_tokens=max_tokens,
                temperature=0.0,
                json_mode=True,
            )
            path_used = name
            if content:
                break
        except Exception as exc:
            errors.append(f"{name}:{type(exc).__name__}:{exc}"[:300])
            content = ""
    if not content:
        return TranslatorResult(
            ok=False,
            error="; ".join(errors)[:800] or "ai_empty",
            path="ai_failed",
        )

    # Parse JSON from model output
    data: dict[str, Any] | None = None
    try:
        data = json.loads(content)
    except Exception:
        mjson = re.search(r"\{[\s\S]*\}", content)
        if mjson:
            try:
                data = json.loads(mjson.group(0))
            except Exception:
                data = None
    if not isinstance(data, dict):
        return TranslatorResult(
            ok=False,
            error="ai_json_parse_failed",
            model_used=f"{path_used}:{model_used}",
            path=path_used or "ai",
        )

    return TranslatorResult(
        ok=True,
        grounded_json=data,
        model_used=f"{path_used}:{model_used}",
        path=path_used or "ai",
        structured_text="",
        error="",
    )





_BLOCKED_CMD_NAMES = frozenset({
    "ssl", "tls", "example", "information", "com", "http", "https", "www",
    "order", "pin", "records", "status", "certificate", "headers",
    "await", "async", "def", "class", "import", "from", "return", "true", "false", "none",
    "user", "users", "group", "groups", "channel", "history", "fully", "the", "and", "or",
    "get", "set", "view", "open", "show", "list", "new", "old", "all", "with",
    "بالكامل", "command", "commands",
})


def _valid_cmd_name(name: str) -> bool:
    n = (name or "").strip().lstrip("/").lower()
    if not n or n in _BLOCKED_CMD_NAMES:
        return False
    if not re.match(r"^[a-z][a-z0-9_]{0,32}$", n):
        return False
    if n.count("_") > 3:
        return False
    if re.search(r"_id_[a-z]|_name_[a-z]|_email_|_phone_|_status_|_owner_", n):
        return False
    return True


def _normalize_cmd_name(name: str) -> str:
    """Sanitize only — never rename user-provided command names."""
    n = (name or "").strip().lstrip("/").lower().replace(" ", "_").replace("-", "_")
    n = re.sub(r"[^a-z0-9_]", "", n)
    if not n:
        return ""
    if not _valid_cmd_name(n) and n not in ("start", "help"):
        return ""
    return n


def _merge_specs(primary: dict, secondary: dict) -> dict:
    """Union AI + structural specs so HF cannot drop evidenced catalog/items/flows."""
    out: dict = {
        "bot_name": (primary.get("bot_name") or secondary.get("bot_name") or ""),
        "commands": [],
        "buttons": [],
        "entities": [],
        "flows": [],
        "rules": [],
        "relations": list(primary.get("relations") or []) + list(secondary.get("relations") or []),
    }
    # commands
    seen_c: set[str] = set()
    for src in (primary, secondary):
        for c in src.get("commands") or []:
            if not isinstance(c, dict):
                continue
            name = _normalize_cmd_name(str(c.get("name") or ""))
            if not name or name in seen_c:
                continue
            seen_c.add(name)
            cc = dict(c)
            cc["name"] = name
            out["commands"].append(cc)
    # buttons by label
    seen_b: set[str] = set()
    for src in (primary, secondary):
        for b in src.get("buttons") or []:
            lab = (b.get("label") if isinstance(b, dict) else str(b) or "").strip()
            if not lab or lab in seen_b:
                continue
            seen_b.add(lab)
            out["buttons"].append({"label": lab} if not isinstance(b, dict) else {**b, "label": lab})
    # entities by name
    seen_e: set[str] = set()
    for src in (primary, secondary):
        for e in src.get("entities") or []:
            if not isinstance(e, dict):
                continue
            en = str(e.get("name") or "").strip()
            if not en or en.lower() in seen_e:
                continue
            seen_e.add(en.lower())
            out["entities"].append(e)
    # flows by id — prefer richer step lists
    flows_by: dict[str, dict] = {}
    for src in (primary, secondary):
        for f in src.get("flows") or []:
            if not isinstance(f, dict):
                continue
            fid = str(f.get("id") or f.get("command") or "").strip() or "flow"
            fid = _normalize_cmd_name(fid)
            prev = flows_by.get(fid)
            steps = f.get("steps") or []
            if prev is None or len(steps) > len(prev.get("steps") or []):
                ff = dict(f)
                ff["id"] = fid
                ff["command"] = _normalize_cmd_name(str(f.get("command") or fid))
                flows_by[fid] = ff
    out["flows"] = list(flows_by.values())
    # rules
    seen_r: set[str] = set()
    for src in (primary, secondary):
        for r in src.get("rules") or []:
            if isinstance(r, str) and r.strip() and r not in seen_r:
                seen_r.add(r)
                out["rules"].append(r)
    return out




def _label_to_command_name(label: str) -> str:
    """Derive a command slug from a user button label (emoji stripped). No domain packs."""
    raw = (label or "").strip()
    if not raw:
        return ""
    # Drop symbols/emoji; keep letters, digits, spaces, underscores, hyphens
    cleaned = re.sub(r"[^\w\s\-]", " ", raw, flags=re.UNICODE)
    cleaned = cleaned.strip().lower().replace("-", "_").replace(" ", "_")
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    # Prefer ASCII token sequence if mixed script left empty ascii
    ascii_only = re.sub(r"[^a-z0-9_]", "", cleaned)
    if ascii_only and len(ascii_only) >= 2:
        return _normalize_cmd_name(ascii_only)
    return _normalize_cmd_name(cleaned)


def _promote_flows_and_buttons(spec: dict, text: str) -> dict:
    """
    Universal surface promotion (all bots):
      - every grounded button label → command slug
      - every grounded tool id → command (if valid)
      - every flow.command → command
    No domain templates. Only surfaces already present in the grounded spec / user text.
    """
    if not isinstance(spec, dict):
        return spec

    cmds = [c for c in (spec.get("commands") or []) if isinstance(c, dict)]
    have = {str(c.get("name") or "").lower() for c in cmds}

    def _add_cmd(name: str, description: str) -> None:
        nonlocal cmds, have
        name = _normalize_cmd_name(name)
        if not name or name in have:
            return
        if not _valid_cmd_name(name) and name not in ("start", "help"):
            return
        cmds.append({
            "name": name,
            "description": (description or name.replace("_", " "))[:100],
            "admin_only": False,
        })
        have.add(name)

    # 1) flows
    for f in spec.get("flows") or []:
        if not isinstance(f, dict):
            continue
        fname = str(f.get("command") or f.get("id") or "").strip().lower()
        fname = re.sub(r"[^a-z0-9_]", "_", fname).strip("_")
        if fname:
            _add_cmd(fname, fname.replace("_", " "))
            f["command"] = fname
            f["id"] = f.get("id") or fname

    # 2) buttons → commands (label evidenced already by grounding)
    new_buttons: list[dict] = []
    for b in spec.get("buttons") or []:
        lab = str(b.get("label") if isinstance(b, dict) else b or "").strip()
        if not lab:
            continue
        slug = _label_to_command_name(lab)
        if slug:
            _add_cmd(slug, lab)
            entry = {"label": lab[:48], "command": slug}
            if isinstance(b, dict) and b.get("callback"):
                entry["callback"] = str(b.get("callback"))[:64]
            else:
                entry["callback"] = f"cmd:{slug}"
            new_buttons.append(entry)
        else:
            new_buttons.append({"label": lab[:48]} if not isinstance(b, dict) else {**b, "label": lab[:48]})
    if new_buttons:
        spec["buttons"] = new_buttons

    # 3) tools → commands (id must look like a command; title used as description)
    for t in spec.get("tools") or []:
        if not isinstance(t, dict):
            continue
        tid = str(t.get("id") or "").strip().lower()
        tid = re.sub(r"[^a-z0-9_]", "_", tid).strip("_")
        if not tid or tid in {"tool", "logs", "pdf", "sqlite", "ner", "gitignore", "env_example", "python_aiogram"}:
            # skip meta/infra noise ids — not user-facing bot actions
            continue
        title = str(t.get("title") or t.get("description") or tid).strip()
        _add_cmd(tid, title[:100])
        # Ensure a minimal collect flow when tool declares input
        inp = str(t.get("input") or "").strip().lower()
        if inp and inp not in {"none", "n/a", "-"}:
            flows = list(spec.get("flows") or [])
            existing_ids = {
                str(f.get("command") or f.get("id") or "").lower()
                for f in flows if isinstance(f, dict)
            }
            if tid not in existing_ids:
                key = re.sub(r"[^a-z0-9_]", "", inp)[:24] or "value"
                flows.append({
                    "id": tid,
                    "command": tid,
                    "kind": "collect",
                    "steps": [{"key": key, "prompt": f"أرسل {key}:"}],
                })
                spec["flows"] = flows

    # Drop fragment noise only when not explicitly /named in user text
    junk = {
        "ssl", "tls", "example", "information", "com", "http", "https", "www",
        "pin", "records", "certificate", "headers", "status",
    }
    cleaned = []
    for c in cmds:
        name = str(c.get("name") or "").lower()
        if name in junk and not re.search(rf"/{re.escape(name)}\b", text or "", re.I):
            continue
        cleaned.append(c)
    # Always keep start/help if present or add structural minimum later downstream
    spec["commands"] = cleaned

    evid_cmds = {str(c.get("name") or "").lower() for c in cleaned}
    for m in re.finditer(r"(?m)(?:^|\s)/([A-Za-z][A-Za-z0-9_]{1,32})\b", text or ""):
        evid_cmds.add(m.group(1).lower())
    # Keep flows bound to promoted commands
    spec["flows"] = [
        f for f in (spec.get("flows") or [])
        if isinstance(f, dict)
        and str(f.get("command") or f.get("id") or "").lower() in evid_cmds
    ]

    # Tools: keep grounded list; refresh from text without domain packs
    fresh = _extract_dynamic_tools(text)
    existing = [t for t in (spec.get("tools") or []) if isinstance(t, dict)]
    have_t = {str(t.get("id")) for t in existing}
    for t in fresh:
        if str(t.get("id")) not in have_t:
            existing.append(t)
            have_t.add(str(t.get("id")))
    spec["tools"] = existing[:24]
    return spec



def translate_spec(user_text: str, *, timeout: int | None = None) -> TranslatorResult:
    """AI ONLY (Groq primary, HF secondary). No structural fallback."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass
    text = (user_text or "").strip()
    t0 = time.perf_counter()
    if not text:
        return TranslatorResult(
            ok=False,
            error="empty_text",
            needs_clarification=False,
            clarification_questions=[],
            path="passthrough",
            elapsed_ms=0.0,
        )

    timeout = timeout if timeout is not None else int(os.environ.get("SPEC_TRANSLATOR_TIMEOUT", "45"))

    if os.environ.get("SPEC_TRANSLATOR", "1").strip().lower() in {"0", "false", "off"}:
        return TranslatorResult(
            ok=False,
            error="spec_translator_disabled",
            path="disabled",
            elapsed_ms=round((time.perf_counter() - t0) * 1000, 1),
        )

    from . import groq_provider as _groq
    from . import hf_provider as _hf
    if not (_groq.enabled() or _hf.enabled()):
        return TranslatorResult(
            ok=False,
            error="GROQ_API_KEY or HF_TOKEN required — SpecTranslator is AI-only (structural path disabled)",
            path="ai_missing",
            elapsed_ms=round((time.perf_counter() - t0) * 1000, 1),
        )

    ai_result = _hf_translate(text, timeout=timeout)
    if not ai_result.ok:
        return TranslatorResult(
            ok=False,
            error=ai_result.error or "ai_translate_failed",
            model_used=ai_result.model_used,
            path=ai_result.path or "ai",
            elapsed_ms=round((time.perf_counter() - t0) * 1000, 1),
        )

    data = ai_result.grounded_json if isinstance(ai_result.grounded_json, dict) else {}
    # Ground to user text only — never merge structural baseline (source of ssl/information noise)
    grounded = _ground_spec_to_user_text(data, text)

    for c in grounded.get("commands") or []:
        if isinstance(c, dict) and c.get("name"):
            c["name"] = _normalize_cmd_name(str(c["name"]))
    grounded["commands"] = [
        c for c in (grounded.get("commands") or [])
        if isinstance(c, dict) and (
            _valid_cmd_name(str(c.get("name") or ""))
            or str(c.get("name") or "") in ("start", "help")
        )
    ]
    grounded = _promote_flows_and_buttons(grounded, text)

    structured = _spec_to_sectioned_text(grounded, text)
    meaningful = [
        c for c in (grounded.get("commands") or [])
        if isinstance(c, dict) and c.get("name") not in ("start", "help")
    ]
    ok = bool(meaningful or grounded.get("buttons") or grounded.get("flows") or grounded.get("tools"))

    return TranslatorResult(
        ok=ok,
        structured_text=structured if ok else "",
        grounded_json=grounded,
        model_used=ai_result.model_used or "ai",
        elapsed_ms=round((time.perf_counter() - t0) * 1000, 1),
        path=ai_result.path or "ai",
        error="" if ok else "ai_no_grounded_signal",
        needs_clarification=False,
        clarification_questions=[],
    )



def prepare_formal_text(user_text: str) -> tuple[str, TranslatorResult]:
    tr = translate_spec(user_text)
    if tr.ok and tr.structured_text.strip():
        return tr.structured_text, tr
    return (user_text or "").strip(), tr
