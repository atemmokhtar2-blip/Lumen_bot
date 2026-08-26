"""Compare generated bot vs user description; produce repair directives for the engine."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Mismatch:
    code: str
    severity: str
    ar: str
    evidence: str = ""


@dataclass
class FidelityReport:
    ok: bool
    score: float
    mismatches: list[Mismatch] = field(default_factory=list)
    repair_directive: dict[str, Any] = field(default_factory=dict)
    summary_ar: str = ""
    source: str = "local"

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "score": self.score,
            "mismatches": [asdict(m) for m in self.mismatches],
            "repair_directive": dict(self.repair_directive),
            "summary_ar": self.summary_ar,
            "source": self.source,
        }

    def to_user_ar(self) -> str:
        if self.ok:
            return f"✅ المطابقة جيدة (درجة {self.score:.0%}) — {self.source}"
        lines = [f"⚠️ فجوات مقابل وصفك (درجة {self.score:.0%}) — {self.source}:"]
        for m in self.mismatches[:12]:
            lines.append(f"• [{m.severity}] {m.ar}")
        acts = (self.repair_directive or {}).get("required_actions") or []
        if acts:
            lines.append("\nإصلاحات مطلوبة من المحرك:")
            for a in acts[:10]:
                lines.append(f"→ {a}")
        return "\n".join(lines)


def summarize_project(project_dir: str | Path) -> dict[str, Any]:
    root = Path(project_dir)

    def rd(rel: str, n: int = 14000) -> str:
        try:
            return (root / rel).read_text(encoding="utf-8", errors="replace")[:n]
        except Exception:
            return ""

    handlers, keyboards, main = rd("app/handlers.py"), rd("app/keyboards.py", 6000), rd("main.py", 8000)
    cmds = sorted(set(re.findall(r"CommandHandler\(\s*['\"]([^'\"]+)['\"]", main + handlers)))
    labels = [m[1] for m in re.findall(r"InlineKeyboardButton\(\s*(['\"])(.+?)\1", keyboards)]
    wm = re.search(r"async def start_handler.*?text\s*=\s*(['\"])(.+?)\1", handlers, re.S)
    welcome = wm.group(2) if wm else ""
    phones = re.findall(r"\b01[0-9]{9}\b", handlers + keyboards + welcome)
    statuses = re.findall(r"(قيد المراجعة|جاري التجهيز|تم الشحن|تم التسليم)", handlers + welcome)
    return {
        "commands": cmds[:40],
        "button_labels": labels[:20],
        "welcome_excerpt": welcome[:500],
        "phones": list(dict.fromkeys(phones))[:5],
        "status_mentions": list(dict.fromkeys(statuses))[:10],
    }


def _local_compare(user_request: str, summary: dict[str, Any]) -> FidelityReport:
    req = user_request or ""
    blob = " ".join(summary.get("button_labels") or []) + " " + (summary.get("welcome_excerpt") or "")
    phones_found = summary.get("phones") or []
    status_blob = blob + " " + " ".join(summary.get("status_mentions") or [])
    mismatches: list[Mismatch] = []
    for word in ("المنتجات", "العروض", "متابعة الطلب", "التواصل", "معلومات المتجر", "طلب منتج"):
        if word in req and word not in blob:
            mismatches.append(Mismatch("missing_menu_label", "error", f"«{word}» مطلوب وغير ظاهر", word))
    for m in re.findall(r"01[0-9]{9}", req):
        if m not in phones_found and m not in blob:
            mismatches.append(Mismatch("missing_contact_phone", "error", f"رقم {m} غير ظاهر في البوت", m))
    for st in ("قيد المراجعة", "جاري التجهيز", "تم الشحن", "تم التسليم"):
        if st in req and st not in status_blob:
            mismatches.append(Mismatch("missing_order_status", "warning", f"حالة «{st}» غير واضحة", st))
    n_err = sum(1 for x in mismatches if x.severity == "error")
    n_warn = sum(1 for x in mismatches if x.severity == "warning")
    score = max(0.0, 1.0 - 0.15 * n_err - 0.05 * n_warn)
    ok = n_err == 0 and score >= 0.75
    WORD_FEAT = {
        "المنتجات": ("🛍️ المنتجات", "shop_catalog"),
        "العروض": ("🔥 العروض", "flash_sale_list"),
        "متابعة الطلب": ("📦 متابعة الطلب", "order_track"),
        "طلب منتج": ("🛒 طلب منتج", "shop_order"),
        "التواصل": ("📞 التواصل معنا", "about"),
        "معلومات المتجر": ("ℹ️ معلومات المتجر", "about"),
    }
    actions, inject, menu, statuses = [], [], [], []
    phone = ""
    for m in mismatches:
        if m.code == "missing_menu_label" and m.evidence in WORD_FEAT:
            lab, feat = WORD_FEAT[m.evidence]
            actions.append(f"أضف زر: {lab}")
            inject.append(feat)
            menu.append({"label": lab, "feature": feat})
        if m.code == "missing_contact_phone":
            actions.append(f"أظهر الرقم {m.evidence}")
            phone = m.evidence
        if m.code == "missing_order_status":
            actions.append(f"أضف حالة: {m.evidence}")
            statuses.append(m.evidence)
    welcome = f"مرحبًا بك في متجرنا 🛍️\nاختر من القائمة.\n\n📞 {phone}" if phone else ""
    repair = {
        "required_actions": actions,
        "inject_features": list(dict.fromkeys(inject)),
        "ux_patch": {
            "menu_buttons": menu,
            "contact_phone": phone,
            "order_statuses": statuses,
            "welcome": welcome,
            "contact_text": (f"للتواصل:\n📞 {phone}" if phone else ""),
        },
    }
    return FidelityReport(
        ok=ok,
        score=score,
        mismatches=mismatches,
        repair_directive=repair,
        summary_ar=("مطابق" if ok else f"{n_err} أخطاء / {n_warn} تحذيرات"),
        source="local",
    )


def gemini_compare(user_request: str, summary: dict[str, Any]) -> FidelityReport | None:
    import os
    import requests

    key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
    if not key:
        return None
    prompt = (
        "أنت مراجع جودة لبوت تيليجرام. قارن وصف المستخدم مع ملخص البوت.\n"
        "أرجع JSON فقط: "
        '{"ok":bool,"score":0.0-1.0,"mismatches":[{"code":"str","severity":"error|warning","ar":"str","evidence":"str"}],'
        '"required_actions":["str"],"inject_features":["shop_catalog","flash_sale_list","shop_order","order_track","about"],'
        '"ux_patch":{"welcome":"","menu_buttons":[{"label":"","feature":""}],"contact_phone":"","contact_text":"","order_statuses":[]},'
        '"summary_ar":"جملة"}\n'
        "لا تخترع شيئاً خارج الوصف.\n\n"
        f"USER_DESCRIPTION:\n{user_request[:10000]}\n\n"
        f"GENERATED_SUMMARY:\n{json.dumps(summary, ensure_ascii=False)[:7000]}\n"
    )
    models = [
        os.getenv("GEMINI_MODEL") or "gemini-3.5-flash",
        "gemini-3.6-flash",
        "gemini-flash-latest",
        "gemini-2.5-flash",
    ]
    for model in models:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            r = requests.post(
                url,
                params={"key": key},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"},
                },
                timeout=60,
            )
            if r.status_code != 200:
                continue
            text = ""
            for c in r.json().get("candidates") or []:
                for part in ((c.get("content") or {}).get("parts") or []):
                    text += str(part.get("text") or "")
            parsed = None
            if text.strip().startswith("{"):
                parsed = json.loads(text)
            else:
                m = re.search(r"\{[\s\S]*\}", text)
                parsed = json.loads(m.group(0)) if m else None
            if not isinstance(parsed, dict):
                continue
            mismatches = [
                Mismatch(
                    str(i.get("code") or "gap"),
                    str(i.get("severity") or "warning"),
                    str(i.get("ar") or "")[:300],
                    str(i.get("evidence") or "")[:200],
                )
                for i in (parsed.get("mismatches") or [])
                if isinstance(i, dict)
            ]
            score = max(0.0, min(1.0, float(parsed.get("score") or 0.5)))
            ok = bool(parsed.get("ok")) if "ok" in parsed else score >= 0.75
            repair = {
                "required_actions": [str(x) for x in (parsed.get("required_actions") or [])][:15],
                "inject_features": [str(x) for x in (parsed.get("inject_features") or [])][:20],
                "ux_patch": parsed.get("ux_patch") if isinstance(parsed.get("ux_patch"), dict) else {},
            }
            return FidelityReport(
                ok=ok,
                score=score,
                mismatches=mismatches,
                repair_directive=repair,
                summary_ar=str(parsed.get("summary_ar") or "")[:500],
                source="gemini",
            )
        except Exception as exc:
            logger.warning("gemini_compare %s: %s", model, exc)
    return None


def compare_generated_to_request(
    user_request: str, project_dir: str | Path, *, use_gemini: bool = True
) -> FidelityReport:
    summary = summarize_project(project_dir)
    local = _local_compare(user_request, summary)
    if not use_gemini:
        return local
    gem = gemini_compare(user_request, summary)
    if gem is None:
        local.source = "local_only"
        return local
    codes = {m.code + m.ar for m in local.mismatches}
    merged = list(local.mismatches)
    for m in gem.mismatches:
        k = m.code + m.ar
        if k not in codes:
            merged.append(m)
            codes.add(k)
    repair = dict(local.repair_directive)
    gr = gem.repair_directive or {}
    repair["required_actions"] = list(
        dict.fromkeys(list(repair.get("required_actions") or []) + list(gr.get("required_actions") or []))
    )[:15]
    repair["inject_features"] = list(
        dict.fromkeys(list(repair.get("inject_features") or []) + list(gr.get("inject_features") or []))
    )[:20]
    ux = dict(repair.get("ux_patch") or {})
    ux.update({k: v for k, v in (gr.get("ux_patch") or {}).items() if v})
    repair["ux_patch"] = ux
    n_err = sum(1 for m in merged if m.severity == "error")
    score = min(local.score, gem.score)
    ok = n_err == 0 and score >= 0.75
    return FidelityReport(
        ok=ok,
        score=score,
        mismatches=merged,
        repair_directive=repair,
        summary_ar=gem.summary_ar or local.summary_ar,
        source="hybrid",
    )


def apply_repairs_to_spec(spec: Any, repair_directive: dict[str, Any]) -> Any:
    try:
        from lumen.engine.spec_core.schema import BotSpec, Feature, Trigger, UxCopy
    except Exception:
        # spec_core removed — pass through unchanged
        return spec

    if isinstance(spec, dict):
        spec = BotSpec.from_dict(spec)
    inject = [str(x).strip() for x in (repair_directive.get("inject_features") or []) if str(x).strip()]
    existing = {f.feature for f in (spec.features or [])}
    try:
        from lumen.engine.services.capability_detection.catalog import CAPABILITIES
    except Exception:
        CAPABILITIES = {}
    for feat in inject:
        if feat in existing or feat not in CAPABILITIES:
            continue
        spec.features.append(Feature(id=feat, feature=feat, trigger=Trigger(type="command", id=feat)))
        existing.add(feat)
    ux = getattr(spec, "ux", None) or UxCopy()
    patch = repair_directive.get("ux_patch") if isinstance(repair_directive.get("ux_patch"), dict) else {}
    if patch.get("welcome"):
        ux.welcome = str(patch["welcome"])[:2000]
    if patch.get("contact_phone"):
        ux.contact_phone = str(patch["contact_phone"])[:40]
        if ux.contact_phone and ux.contact_phone not in (ux.welcome or ""):
            ux.welcome = (ux.welcome or "مرحبًا بك 👋\nاختر من القائمة.").rstrip() + "\n\n📞 " + ux.contact_phone
    if patch.get("contact_text"):
        ux.contact_text = str(patch["contact_text"])[:500]
    if patch.get("order_statuses"):
        ux.order_statuses = list(
            dict.fromkeys(list(ux.order_statuses or []) + [str(x)[:80] for x in patch["order_statuses"]])
        )[:12]
    have = {str(b.get("label")) for b in (ux.menu_buttons or []) if isinstance(b, dict)}
    for b in patch.get("menu_buttons") or []:
        if isinstance(b, dict) and str(b.get("label") or "") not in have:
            ux.menu_buttons.append(
                {"label": str(b.get("label"))[:60], "feature": str(b.get("feature") or "")[:64]}
            )
            have.add(str(b.get("label")))
    LABEL = {
        "shop_catalog": "🛍️ المنتجات",
        "flash_sale_list": "🔥 العروض",
        "shop_order": "🛒 طلب منتج",
        "order_track": "📦 متابعة الطلب",
        "about": "ℹ️ معلومات المتجر",
    }
    have_f = {str(b.get("feature")) for b in ux.menu_buttons if isinstance(b, dict)}
    for feat in inject:
        if feat not in have_f and feat in LABEL:
            ux.menu_buttons.append({"label": LABEL[feat], "feature": feat})
            have_f.add(feat)
    spec.ux = ux
    return spec


def build_verify_repair(
    spec: Any,
    out_dir: str | Path,
    user_request: str,
    *,
    use_gemini: bool = True,
    max_rounds: int = 2,
):
    """Removed with the deterministic engine. Always returns a failed report."""
    last = FidelityReport(
        ok=False,
        score=0.0,
        summary_ar="مسار التحقق الحتمي أُزيل — استخدم Cline فقط",
    )
    return spec, last
