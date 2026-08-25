"""Catalog of tools. ToolContract is source of truth; TOOL_SPECS derived."""
from __future__ import annotations

from typing import Any

try:
    from lumen.engine.tools.contracts import build_default_contracts
    _CONTRACTS = build_default_contracts()
    TOOL_SPECS: dict[str, dict[str, Any]] = {
        name: c.to_spec_dict() for name, c in _CONTRACTS.items()
    }
except Exception:
    TOOL_SPECS = {
    "create_repo": {
        "description": "إنشاء مستودع جديد على GitHub باستخدام توكن المستخدم (PAT)",
        "params": {
            "name": "اسم المستودع",
            "token": "توكن GitHub PAT بصلاحية repo",
            "private": "اختياري — true/false (افتراضي true)",
            "description": "اختياري — وصف المستودع",
        },
        "requires_confirmation": True,
    },
    "git_push": {
        "description": "دفع التغييرات (commit+push) للمستودع النشط أو المسار المحدد",
        "params": {
            "path": "اختياري — مسار المستودع المحلي",
            "token": "اختياري — PAT إن كان المستودع خاصاً",
            "message": "اختياري — رسالة الكوميت",
        },
        "requires_confirmation": True,
    },
    "git_pull": {
        "description": "سحب آخر نسخة من المستودع النشط (git pull)",
        "params": {
            "path": "اختياري — مسار المستودع",
            "token": "اختياري — PAT للمستودعات الخاصة",
        },
        "requires_confirmation": False,
    },
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
        "requires_confirmation": True,
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


# --- Phase D hardened catalog helpers ---

# Risk: low | medium | high | critical — critical/high always HITL
_TOOL_RISK: dict[str, str] = {
    "repo_inspect": "low",
    "repo_understand": "low",
    "host_status": "low",
    "git_pull": "medium",
    "clone_repo": "medium",
    "generate_bot": "medium",
    "refine_bot": "medium",
    "create_repo": "high",
    "git_push": "high",
    "repo_modify": "high",
    "host_start": "critical",
    "host_stop": "critical",
}

_REQUIRED_PARAMS: dict[str, tuple[str, ...]] = {
    "create_repo": ("name", "token"),
    "clone_repo": ("url",),
    "git_push": (),  # path optional if active repo
    "host_start": (),
    "host_stop": (),
    "repo_modify": (),
    "generate_bot": ("spec_request",),
}

# Secrets never stored in pending snapshots
_SECRET_PARAM_KEYS = frozenset({
    "token", "pat", "password", "secret", "api_key", "apikey",
    "telegram_bot_token", "bot_token", "authorization",
})


def get_tool_spec(name: str) -> dict[str, Any] | None:
    spec = TOOL_SPECS.get((name or "").strip())
    return dict(spec) if spec else None


def tool_risk_level(name: str) -> str:
    n = (name or "").strip()
    if n in _TOOL_RISK:
        return _TOOL_RISK[n]
    spec = TOOL_SPECS.get(n) or {}
    if spec.get("requires_confirmation"):
        return "high"
    return "medium" if n in TOOL_SPECS else "unknown"


def tool_requires_confirmation(name: str) -> bool:
    """Fail-closed: high/critical risk always requires HITL; also honor catalog flag."""
    n = (name or "").strip()
    risk = tool_risk_level(n)
    if risk in {"high", "critical"}:
        return True
    spec = TOOL_SPECS.get(n) or {}
    return bool(spec.get("requires_confirmation"))


def tool_required_params(name: str) -> tuple[str, ...]:
    return _REQUIRED_PARAMS.get((name or "").strip(), ())


def validate_tool_params(name: str, params: dict[str, Any] | None) -> tuple[bool, list[str]]:
    """Validate required params present (non-empty)."""
    params = dict(params or {})
    missing = []
    for key in tool_required_params(name):
        val = params.get(key)
        if val is None or (isinstance(val, str) and not val.strip()):
            missing.append(key)
    # Unknown tool
    if (name or "").strip() not in TOOL_SPECS and (name or "").strip() not in _TOOL_RISK:
        return False, ["unknown_tool"]
    return (len(missing) == 0, missing)


def redact_secrets(params: dict[str, Any] | None) -> dict[str, Any]:
    """Return params copy with secret values replaced by redacted markers."""
    out: dict[str, Any] = {}
    for k, v in dict(params or {}).items():
        lk = str(k).lower()
        if lk in _SECRET_PARAM_KEYS or any(s in lk for s in ("token", "secret", "password", "key")):
            if v:
                out[k] = "***REDACTED***"
            else:
                out[k] = v
        else:
            out[k] = v
    return out
