# الأمان والعزل

## النموذج

```
Agent / Chat
    → Tool Contract
        → Policy
            → Sandbox / Executor
```

| ملف | دور |
|-----|-----|
| `security/policy.py` | سياسات السماح/الرفض (مثلاً push يحتاج تأكيد) |
| `security/sandbox.py` | تنفيذ معزول |
| `services/user_sandbox.py` | مجلد لكل مستخدم تحت OUTPUT_DIR |
| `services/isolation_policy.py` | قواعد العزل |
| `services/secure_exec.py` | تنفيذ أوامر بحذر |
| `services/safe_fs.py` | مسارات آمنة بدون path traversal |
| `bot_interface/sanitize.py` | تنقيح أخطاء/أسرار قبل عرضها للمستخدم |

## حدود Git / Workspace / Hosting

`telegram_bot_engine/boundaries/`:

- `git_boundary.py`
- `workspace.py`
- `hosting_boundary.py`

لا تدمج الثلاثة في abstraction واحدة.

## أسرار

- لا تكتب PAT أو توكنات في اللوج الخام
- `sanitize_error` قبل `reply_text` عند الفشل
- مفاتيح API B2B hashed في التخزين
