"""Catalog of tools Groq may request. Implementations live in executor only."""
from __future__ import annotations

from typing import Any

# Machine contract for the chat model (never executed by the model itself).
TOOL_SPECS: dict[str, dict[str, Any]] = {
    "clone_repo": {
        "description": "سحب مستودع Git (GitHub/GitLab/Bitbucket) إلى مساحة المستخدم",
        "params": {
            "url": "رابط المستودع https",
            "token": "اختياري — PAT للمستودعات الخاصة",
            "branch": "اختياري — فرع محدد",
            "depth": "اختياري — عمق الـ shallow clone (افتراضي 1)",
        },
        "requires_confirmation": False,
    },
    "repo_inspect": {
        "description": "فحص مستودع مسحوب أو بوت مولَّد: ملفات، أوامر، نقاط ضعف",
        "params": {
            "path": "اختياري — مسار المشروع؛ وإلا آخر مشروع/مستودع نشط",
        },
        "requires_confirmation": False,
    },
    "repo_understand": {
        "description": "تحليل بنية المستودع النشط (ملفات رئيسية + ملخص)",
        "params": {
            "path": "اختياري — مسار المستودع",
        },
        "requires_confirmation": False,
    },
    "generate_bot": {
        "description": "توليد بوت تيليجرام من مواصفات المستخدم عبر محرك spec_core",
        "params": {
            "spec_request": "وصف البوت بالعربية أو الإنجليزية",
        },
        "requires_confirmation": False,
    },
    "refine_bot": {
        "description": "تعديل بوت المستخدم الحالي عبر المحرك مع دمج الميزات السابقة",
        "params": {
            "spec_request": "وصف التعديل المطلوب",
        },
        "requires_confirmation": False,
    },
    "repo_modify": {
        "description": "طلب تعديل على المستودع/البوت النشط — التنفيذ عبر المحرك فقط",
        "params": {
            "path": "اختياري — مسار المشروع",
            "change": "وصف التعديل بالعربية أو الإنجليزية",
        },
        "requires_confirmation": False,
    },
    "host_status": {
        "description": "حالة الاستضافة للبوتات المستضافة",
        "params": {},
        "requires_confirmation": False,
    },
    "host_start": {
        "description": "تشغيل استضافة بوت",
        "params": {"project_path": "مسار المشروع"},
        "requires_confirmation": True,
    },
    "host_stop": {
        "description": "إيقاف استضافة بوت",
        "params": {"project_path": "مسار المشروع"},
        "requires_confirmation": True,
    },
}


def list_tool_names() -> list[str]:
    return sorted(TOOL_SPECS.keys())


def tool_catalog_for_prompt() -> str:
    lines = []
    for name, spec in TOOL_SPECS.items():
        params = ", ".join(f"{k}" for k in (spec.get("params") or {}))
        conf = " (يحتاج تأكيد)" if spec.get("requires_confirmation") else ""
        lines.append(f"- {name}{conf}: {spec.get('description')} | params: {params or '—'}")
    return "\n".join(lines)
