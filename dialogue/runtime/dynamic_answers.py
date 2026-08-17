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


def _usage_text(metadata: dict[str, Any] | None) -> str:
    live = dict((metadata or {}).get("live_context") or {})
    usage = dict(live.get("usage") or {})
    plan = dict(live.get("plan") or {})
    if not usage or not plan:
        return "لا أستطيع قراءة استخدام حسابك الآن من المصدر الحي. أعد المحاولة بعد لحظات."
    messages_remaining = usage.get("messages_remaining")
    generations_remaining = usage.get("generations_remaining")
    msg = "غير محدود" if messages_remaining is None else str(messages_remaining)
    gen = "غير محدود" if generations_remaining is None else str(generations_remaining)
    return (
        f"حسب بيانات حسابك الحالية في خطة {plan.get('name_ar', plan.get('name', 'الحالية'))}:\n"
        f"الرسائل المتبقية هذا الشهر: {msg}\n"
        f"التوليدات المتبقية هذا الشهر: {gen}\n"
        f"عدد الحروف التي قرأتها الخدمة في هذه الفترة: {int(usage.get('characters_used') or 0)}."
    )


def answer_for_intent(
    intent: str,
    *,
    sender_id: str,
    fallback_plan_id: str | None,
    requested_plan_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str | None:
    if intent in {"ask_usage", "ask_remaining", "ask_message_limit", "ask_character_usage"}:
        return _usage_text(metadata)
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

    # No static/domain fallback is allowed. Unknown or unsupported intents
    # must be handled by the trained model or rejected safely by the bridge.
    return None

