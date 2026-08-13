"""Answers derived from live account and project registries.

No plan quota, project component, or capability facts are embedded here. Values are
read from the current checkout and the current tenant/plan registry.
"""
from __future__ import annotations

from pathlib import Path

from typing import Any

from b2b_platform.plans import PLANS, get_plan, normalize_plan_id, public_plan_dict
from b2b_platform.tenants import get_tenant_store

from .project_context import project_manifest


def _tenant_for(sender_id: str):
    try:
        return get_tenant_store().get_by_telegram(int(sender_id))
    except (TypeError, ValueError, OSError):
        return None


def resolve_plan(sender_id: str, fallback_plan_id: str | None = None) -> tuple[str, dict[str, Any] | None]:
    """Resolve the plan from the account store; fallback is offline compatibility only."""
    tenant = _tenant_for(sender_id)
    plan_id = getattr(tenant, "plan_id", None) if tenant else None
    if not plan_id:
        plan_id = fallback_plan_id
    if not plan_id:
        return "", None
    canonical = normalize_plan_id(plan_id)
    return canonical, public_plan_dict(get_plan(canonical))


def _limit(value: Any, unlimited_text: str = "غير محدود") -> str:
    return unlimited_text if value in (0, None) else str(value)


def _plan_text(plan: dict[str, Any]) -> str:
    return (
        f"الخطة الحالية: {plan['name_ar']} ({plan['name']})\n"
        f"التوليد الشهري: {_limit(plan['generations_per_month'])}\n"
        f"البوتات المستضافة: {_limit(plan['hosted_bots'])}\n"
        f"الرسائل الشهرية: {_limit(plan['messages_per_month'])}\n"
        f"المعاينة الحية: {plan['live_preview_minutes']} دقيقة\n"
        f"حد API: {plan['api_rpm']} طلب/دقيقة\n"
        f"مستوى المحرك: {plan['engine_tier']}"
    )


def _compare_text() -> str:
    rows = []
    for plan_obj in PLANS.values():
        plan = public_plan_dict(plan_obj)
        rows.append(
            f"{plan['name_ar']} ({plan['name']}): "
            f"توليد {_limit(plan['generations_per_month'])}، "
            f"استضافة {_limit(plan['hosted_bots'])}، "
            f"API {plan['api_rpm']} طلب/دقيقة"
        )
    return "مقارنة الخطط الحالية من سجل المشروع:\n" + "\n".join(rows)


def _package_lines(manifest: dict[str, Any]) -> str:
    lines = []
    for package, modules in manifest.get("packages", {}).items():
        names = [item.get("module", "") for item in modules if item.get("module")]
        lines.append(f"{package}: {', '.join(names) if names else 'لا توجد وحدات مكتشفة'}")
    return "\n".join(lines)


def _project_text(intent: str) -> str:
    manifest = project_manifest()
    packages = manifest.get("packages", {})
    models = manifest.get("models", [])
    plans = manifest.get("plan_ids", [])
    if intent == "project_identity":
        return f"المشروع الحالي هو {manifest['root']}. المكونات المكتشفة:\n{_package_lines(manifest)}\nمعرف الحالة: {manifest['fingerprint'][:12]}"
    if intent == "project_capabilities":
        return f"القدرات المكتشفة من مكونات المشروع الحالية:\n{_package_lines(manifest)}\nعدد خطط الحساب المتاحة في السجل: {len(plans)}\nموديلات الحوار المتاحة: {len(models)}"
    if intent == "project_workflow":
        return f"مسار المشروع مبني من الوحدات الحالية المكتشفة:\n{_package_lines(manifest)}\nمصدر الخطط: سجل الخطط وقت التشغيل، وليس بيانات ثابتة داخل الموديل."
    if intent == "ask_project_component":
        return f"مكونات المشروع الحالية حسب القراءة المباشرة للبيئة:\n{_package_lines(manifest)}"
    return ""


def answer_for_intent(
    intent: str,
    *,
    sender_id: str,
    fallback_plan_id: str | None,
    requested_plan_id: str | None = None,
) -> str | None:
    if intent in {"project_identity", "project_capabilities", "project_workflow", "ask_project_component"}:
        return _project_text(intent)
    if intent == "ask_plan_comparison":
        return _compare_text()
    if intent in {"ask_current_plan", "ask_plan_details", "ask_plan_limits"}:
        _plan_id, current = resolve_plan(sender_id, fallback_plan_id)
        if intent == "ask_plan_details" and requested_plan_id:
            try:
                selected = normalize_plan_id(requested_plan_id)
                current = public_plan_dict(get_plan(selected))
            except Exception:
                pass
        if not current:
            return "لم أتمكن من قراءة خطة حسابك من مصدر الحساب حالياً. أعد المحاولة بعد لحظات."
        return _plan_text(current)

    # Domain responses for greet/help/capabilities/... — never silent on known intents
    uttered = _utter_for_intent(intent)
    if uttered:
        return uttered
    return None


# ── Domain utterance fallback (so greet/help/etc. never go silent) ─────────
_DOMAIN_UTTER_CACHE: dict[str, str] | None = None
_INTENT_TO_UTTER = {
    "greet": "utter_greet",
    "goodbye": "utter_goodbye",
    "bot_challenge": "utter_iamabot",
    "affirm": "utter_affirm",
    "deny": "utter_deny",
    "ask_help": "utter_help",
    "ask_capabilities": "utter_capabilities",
    "ask_plan": "utter_plan_info",
    "ask_pricing": "utter_pricing",
    "ask_how_to_generate": "utter_how_to_generate",
    "describe_bot_idea": "utter_ask_clarify_idea",
    "ask_limitations": "utter_limitations",
    "ask_support": "utter_support",
    "how_platform_works": "utter_how_platform_works",
    "how_to_upgrade": "utter_how_to_upgrade",
    "ask_about_hosting": "utter_hosting",
    "ask_about_preview": "utter_preview",
    "ask_about_watermark": "utter_watermark",
    "ask_about_free": "utter_ask_about_free",
    "ask_about_starter": "utter_ask_about_starter",
    "ask_about_growth": "utter_ask_about_growth",
    "out_of_scope": "utter_out_of_scope",
    "nlu_fallback": "utter_default",
    "ask_hosting": "utter_hosting",
    "ask_preview": "utter_preview",
    "ask_generation": "utter_how_to_generate",
    "ask_billing_support": "utter_support",
}


def _load_domain_utters() -> dict[str, str]:
    global _DOMAIN_UTTER_CACHE
    if _DOMAIN_UTTER_CACHE is not None:
        return _DOMAIN_UTTER_CACHE
    out: dict[str, str] = {}
    try:
        import yaml
        path = Path(__file__).resolve().parents[1] / "domain.yml"
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        responses = data.get("responses") or {}
        for key, variants in responses.items():
            if not isinstance(variants, list) or not variants:
                continue
            text = ""
            for item in variants:
                if isinstance(item, dict) and item.get("text"):
                    text = str(item["text"]).strip()
                    break
                if isinstance(item, str):
                    text = item.strip()
                    break
            if text:
                out[str(key)] = text
    except Exception:
        out = {}
    # Minimal hard fallbacks if domain missing/unreadable
    out.setdefault(
        "utter_greet",
        "مرحباً بك في Maestro 👋\nاسألني عن الخطط أو اكتب وصف بوت للتوليد.",
    )
    out.setdefault("utter_goodbye", "إلى اللقاء! اكتب /start لما ترجع.")
    out.setdefault("utter_help", "اكتب وصف بوت، أو اسأل عن الخطط/الاستضافة. أوامر: /start /help /plan")
    out.setdefault("utter_default", "ما فهمتش قصدك تمامًا. جرّب /help أو اكتب وصف البوت اللي تحتاجه.")
    out.setdefault("utter_out_of_scope", "السؤال ده خارج نطاق المنصة. اسأل عن التوليد أو الخطط أو الاستضافة.")
    _DOMAIN_UTTER_CACHE = out
    return out


def _utter_for_intent(intent: str) -> str | None:
    if not intent:
        return None
    utters = _load_domain_utters()
    key = _INTENT_TO_UTTER.get(intent)
    if key and key in utters:
        return utters[key]
    # Conventional mapping intent X → utter_X
    guess = f"utter_{intent}"
    if guess in utters:
        return utters[guess]
    return None

