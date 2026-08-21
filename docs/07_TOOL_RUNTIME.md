# أداة التشغيل — tool_runtime

## المبدأ

```
Chat يختار اسم الأداة + params
        ↓
execute_tool(name, params, user_id, user_data)
        ↓
محرك / خدمة حقيقية تنفّذ
```

الحزمة: `telegram_bot_engine/services/tool_runtime/`

| ملف | دور |
|-----|-----|
| `registry.py` | `TOOL_SPECS` — وصف الأدوات للموديل والواجهة |
| `executor.py` | `execute_tool` + تنفيذ كل أداة |
| `__init__.py` | تصدير عام |

## أدوات مسجّلة (أمثلة)

| الاسم | ماذا تفعل |
|-------|-----------|
| `clone_repo` | سحب Git لمساحة المستخدم |
| `create_repo` | إنشاء مستودع GitHub (يحتاج PAT + تأكيد) |
| `git_push` / `git_pull` | دفع/سحب مع سياسة أمان |
| `repo_inspect` | قياسات سريعة |
| `repo_understand` | toolkit + شرح للمستخدم |
| `repo_modify` | طلب تعديل عبر المحرك |
| `generate_bot` / `refine_bot` | توليد/تحسين عبر spec_core |
| `host_start` / `host_stop` / `host_status` / `host_diagnose` | استضافة |
| تحليلات | `static_analysis`, `package_health`, … |

## الاستخدام

```python
from telegram_bot_engine.services.tool_runtime import execute_tool

tr = execute_tool(
    "repo_understand",
    {"path": "/path/to/repo", "text": "كم سطر؟"},
    user_id=123,
    user_data={"active_repo": {...}},
)
# tr.ok, tr.message, tr.data
```

## الأمان

قبل التنفيذ الحساس: سياسة في `security/policy.py` + sandbox.  
`git_push` وعمليات مدمّرة تتطلب تأكيداً (`requires_confirmation`).
