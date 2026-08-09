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



_HF_SYSTEM = """You are a Telegram bot SPEC translator (not a coder).
Convert the user description into JSON ONLY.

Schema:
{
  "bot_name": "string",
  "commands": [{"name": "exact_user_name", "description": "string", "admin_only": false}],
  "buttons": [{"label": "string"}],
  "entities": [{"name": "PascalCase", "fields": ["field1", "field2"]}],
  "flows": [{"id": "same_as_command", "command": "exact_user_command", "entity": "EntityFromText", "steps": [{"key": "field", "prompt": "..."}]}],
  "rules": ["string"],
  "relations": [{"from": "EntityA", "to": "EntityB", "via": "field"}]
}

STRICT rules:
1) Extract ONLY what the user wrote. Never invent domains (shop/delivery/tickets/games).
2) Command names MUST stay exactly as the user wrote them (e.g. /new_task stays new_task — never rename to add).
3) Entities and fields ONLY from the user text. Do not invent Order/Customer/Item.
4) Flows attach to the user's command names; steps from the described sequence only.
5) Buttons are labels only; do not invent commands like show_categories unless the user wrote them.
6) tools: only what the user asked for. Rebuild every request from their words.
7) JSON only. No markdown. No code.
"""


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
    t0 = time.perf_counter()
    try:
        from .hf_provider import chat, enabled
        if not enabled():
            return TranslatorResult(ok=False, error="HF_TOKEN not configured", path="hf")
        content, model = chat(
            [
                {"role": "system", "content": _HF_SYSTEM},
                {"role": "user", "content": text[:12000]},
            ],
            timeout=timeout,
            max_tokens=int(os.environ.get("SPEC_TRANSLATOR_MAX_TOKENS", "3200")),
            temperature=0.0,
            json_mode=True,
        )
        data = _parse_spec_json(content)
        if not data:
            raise ValueError("invalid_json")
        if not isinstance(data.get("commands"), list) or not data.get("commands"):
            raise ValueError("no_commands")
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
            ok=False,
            error=f"{type(exc).__name__}:{exc}"[:800],
            elapsed_ms=round((time.perf_counter() - t0) * 1000, 1),
            path="hf",
        )


def _g4f_translate(text: str, timeout: int) -> TranslatorResult:
    """Free multi-provider fallback when HF_TOKEN is missing or HF fails."""
    t0 = time.perf_counter()
    if os.environ.get("G4F_ENABLED", "0").strip().lower() not in {"1", "true", "yes", "on"}:
        return TranslatorResult(ok=False, error="g4f_disabled", path="g4f")
    try:
        from g4f.client import Client  # type: ignore
    except Exception as exc:
        return TranslatorResult(ok=False, error=f"g4f_import:{exc}"[:200], path="g4f")
    models = [
        m.strip()
        for m in (os.environ.get("G4F_MODELS") or "gpt-4o-mini,gemini-2.0-flash,gpt-4o").split(",")
        if m.strip()
    ]
    errors: list[str] = []
    for model in models:
        try:
            client = Client()
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": _HF_SYSTEM},
                    {"role": "user", "content": text[:12000]},
                ],
                temperature=0,
            )
            content = ""
            try:
                content = (resp.choices[0].message.content or "").strip()
            except Exception:
                content = str(resp)[:8000]
            data = _parse_spec_json(content)
            if not data or not isinstance(data.get("commands"), list) or not data.get("commands"):
                errors.append(f"{model}:bad_json")
                continue
            return TranslatorResult(
                ok=True,
                structured_text=_spec_to_sectioned_text(data, text),
                grounded_json=data,
                model_used=f"g4f:{model}",
                elapsed_ms=round((time.perf_counter() - t0) * 1000, 1),
                path="g4f",
            )
        except Exception as exc:
            errors.append(f"{model}:{type(exc).__name__}")
            continue
    return TranslatorResult(
        ok=False,
        error=("; ".join(errors) or "g4f_failed")[:800],
        elapsed_ms=round((time.perf_counter() - t0) * 1000, 1),
        path="g4f",
    )




_BLOCKED_CMD_NAMES = frozenset({
    "await", "async", "def", "class", "import", "from", "return", "true", "false", "none",
    "user", "users", "group", "groups", "channel", "history", "fully", "the", "and", "or",
    "get", "set", "view", "open", "show", "list", "new", "old", "all", "with", "from",
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




def _promote_flows_and_buttons(spec: dict, text: str) -> dict:
    """Ensure every flow.command and dashboard button becomes a real command. Drop junk."""
    if not isinstance(spec, dict):
        return spec
    cmds = list(spec.get("commands") or [])
    have = {str(c.get("name") or "").lower() for c in cmds if isinstance(c, dict)}
    # Promote flow commands
    for f in spec.get("flows") or []:
        if not isinstance(f, dict):
            continue
        fname = str(f.get("command") or f.get("id") or "").strip().lower()
        fname = re.sub(r"[^a-z0-9_]", "_", fname).strip("_")
        if not fname or fname in have:
            continue
        if not _valid_cmd_name(fname) and fname not in ("start", "help"):
            continue
        cmds.append({
            "name": fname,
            "description": fname.replace("_", " "),
            "admin_only": False,
        })
        have.add(fname)
        f["command"] = fname
        f["id"] = f.get("id") or fname
    # Buttons → stems already; also map English dashboard labels
    label_map = (
        (r"domain\s*scan", "domain_scan"),
        (r"email\s*security", "email_security"),
        (r"website\s*security", "website_scan"),
        (r"password\s*security", "password_security"),
        (r"security\s*report", "generate_report"),
        (r"report", "generate_report"),
    )
    for b in spec.get("buttons") or []:
        lab = (b.get("label") if isinstance(b, dict) else str(b)) or ""
        lab_l = lab.lower()
        for pat, cname in label_map:
            if re.search(pat, lab_l) and cname not in have and _valid_cmd_name(cname):
                cmds.append({"name": cname, "description": lab.strip()[:80], "admin_only": False})
                have.add(cname)
                break
    # Drop junk command names (fragments from prose / markdown)
    junk = {"ssl", "tls", "example", "information", "com", "http", "https", "www", "order", "pin", "register", "book", "records", "status", "certificate", "headers"}
    # Keep order only if catalog evidence
    n = _norm(text or "")
    catalog = any(k in n for k in ("اصناف", "الأصناف", "منتجات", "منيو", "catalog", "menu items"))
    cleaned = []
    for c in cmds:
        if not isinstance(c, dict):
            continue
        name = str(c.get("name") or "").lower()
        if name in junk and not (name == "order" and catalog):
            # allow if explicit /name in user text
            if not re.search(rf"/{re.escape(name)}\b", text or "", re.I):
                continue
        if name == "order" and not catalog:
            if not re.search(r"/order\b", text or "", re.I):
                continue
        cleaned.append(c)
    spec["commands"] = cleaned
    # Drop order flows without catalog
    if not catalog:
        spec["flows"] = [
            f for f in (spec.get("flows") or [])
            if not (isinstance(f, dict) and str(f.get("id") or f.get("command") or "").lower() == "order")
        ]
    # Tools always recomputed/merged from text for this request
    fresh = _extract_dynamic_tools(text)
    existing = [t for t in (spec.get("tools") or []) if isinstance(t, dict)]
    have = {str(t.get("id")) for t in existing}
    for t in fresh:
        if str(t.get("id")) not in have:
            existing.append(t)
            have.add(str(t.get("id")))
    spec["tools"] = existing[:24]
    return spec

def translate_spec(user_text: str, *, timeout: int | None = None) -> TranslatorResult:
    text = (user_text or "").strip()
    t0 = time.perf_counter()
    if not text:
        return TranslatorResult(
            ok=False,
            error="empty_text",
            needs_clarification=True,
            clarification_questions=["اكتب وصف البوت والأوامر أو الأزرار المطلوبة."],
            path="passthrough",
        )

    timeout = timeout if timeout is not None else int(os.environ.get("SPEC_TRANSLATOR_TIMEOUT", "45"))
    # Complex / long specs: prefer AI harder
    complex_hint = len(text) >= 80 or any(
        k in text for k in ("ثم", "بعدين", "تدفق", "مراحل", "كيان", "قاعدة", "flow", "steps", "entity")
    )

    ai_result: TranslatorResult | None = None
    # 1) HuggingFace when token present
    from .hf_provider import enabled as hf_enabled
    if os.environ.get("SPEC_TRANSLATOR", "1").strip().lower() not in {"0", "false", "off"}:
        if hf_enabled():
            ai_result = _hf_translate(text, timeout=timeout)
        # 2) g4f fallback when HF failed or unavailable
        g4f_on = os.environ.get("G4F_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}
        if g4f_on and not (ai_result and ai_result.ok):
            if complex_hint or not hf_enabled():
                g4 = _g4f_translate(text, timeout=min(timeout, 50))
                if g4.ok:
                    ai_result = g4
                elif ai_result is None:
                    ai_result = g4
                elif g4.error:
                    ai_result.error = (ai_result.error or "") + "|" + g4.error

    # Always compute structural baseline
    structural = structural_translate(text)

    # If AI succeeded, merge so it cannot drop catalog items / admin caps / flows
    if ai_result and ai_result.ok and isinstance(ai_result.grounded_json, dict) and ai_result.grounded_json:
        merged = _merge_specs(ai_result.grounded_json, structural)
        # ensure capability-friendly command names
        for c in merged.get("commands") or []:
            if isinstance(c, dict) and c.get("name"):
                c["name"] = _normalize_cmd_name(str(c["name"]))
        merged = _promote_flows_and_buttons(merged, text)

        merged["commands"] = [
            c for c in (merged.get("commands") or [])
            if isinstance(c, dict) and _valid_cmd_name(str(c.get("name") or ""))
        ]
        # When user pasted a long explicit /command list, keep only those + start/help
        slash = {m.lower() for m in re.findall(r"(?m)(?:^|\\s)/([A-Za-z][A-Za-z0-9_]{1,32})\\b", text or "")}
        if len(slash) >= 8:
            kept = []
            for c in merged.get("commands") or []:
                if not isinstance(c, dict):
                    continue
                n = str(c.get("name") or "").lower()
                if n in slash or n in ("start", "help"):
                    kept.append(c)
            # restore any slash command missing from kept
            have = {str(c.get("name") or "").lower() for c in kept}
            for name in slash:
                if name not in have:
                    kept.append({"name": name, "description": name, "admin_only": name in {
                        "admin","ban","unban","mute","unmute","kick","warn","unwarn","promote","demote",
                        "broadcast","broadcast_groups","broadcast_users","panel","purge","clear","logs",
                        "backup","restore","maintenance","shutdown","restart","reload","config","database",
                        "blacklist","whitelist","export","import","statistics",
                    }})
            merged["commands"] = kept
            # drop invented catalog buttons when dense command list
            merged["buttons"] = []
            merged["flows"] = [
                f for f in (merged.get("flows") or [])
                if isinstance(f, dict) and (
                    str(f.get("command") or f.get("id") or "").lower() in have
                    or str(f.get("command") or "").lower() in slash
                )
            ]
        structured = _spec_to_sectioned_text(merged, text)
        meaningful = [
            c for c in (merged.get("commands") or [])
            if isinstance(c, dict) and c.get("name") not in ("start", "help")
        ]
        ok = bool(meaningful or merged.get("buttons") or merged.get("flows"))
        return TranslatorResult(
            ok=ok,
            structured_text=structured if ok else text,
            grounded_json=merged,
            model_used=(ai_result.model_used or "ai") + "+structural",
            elapsed_ms=round((time.perf_counter() - t0) * 1000, 1),
            path=(ai_result.path or "ai") + "+structural",
            error=ai_result.error or "",
            needs_clarification=not ok,
            clarification_questions=(
                [] if ok else ["المستخدم هيقدر يعمل إيه؟ اكتب أوامر أو أزرار أو قائمة أصناف بشكل واضح."]
            ),
        )

    structural = _promote_flows_and_buttons(structural, text)
    structured = _spec_to_sectioned_text(structural, text)
    meaningful = [
        c for c in (structural.get("commands") or [])
        if isinstance(c, dict) and c.get("name") not in ("start", "help")
    ]
    ok = bool(meaningful or (structural.get("buttons") or []) or (structural.get("flows") or []))
    return TranslatorResult(
        ok=ok,
        structured_text=structured if ok else text,
        grounded_json=structural,
        model_used="structural",
        elapsed_ms=round((time.perf_counter() - t0) * 1000, 1),
        path="structural",
        error=(ai_result.error if ai_result and not ai_result.ok else ""),
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
