# المستودع و Git

## الفصل المهم

| مفهوم | المعنى | أين |
|--------|--------|-----|
| **Workspace** | مكان التعديل المحلي للمستخدم | `boundaries/workspace.py`, `user_sandbox` |
| **Git** | حدود الإصدار (clone/push/pull) | `git_safe_import`, `git_router`, أدوات git |
| **Hosting** | تشغيل وقت التنفيذ | `services/hosting` |
| **Repo Intelligence** | نموذج **مشتق** من الملفات — مش مصدر حقيقة | `repo_understanding`, `repo_intelligence` |

```
Repository on disk = source of truth
Repo Intelligence  = derived only
```

## السحب (Clone)

1. المستخدم يرسل رابط أو «اسحب …»
2. `git_router` أو `clone_repo` → `smart_clone` من `git_safe_import`
3. المسار تحت sandbox المستخدم في `OUTPUT_DIR/users/.../clones/`
4. يُضبط `user_data["active_repo"]` + dossier اختياري + `understand_repo`

## فهم المستودع

`lumen.engine/services/repo_understanding/`

| ملف | دور |
|-----|-----|
| `repo_tools.py` | أدوات قياس: stats, tree, find_files, read_file, search_code, … |
| `llm_explain.py` | يجمع TOOL_RESULTS ويسأل النموذج **للإجابة فقط من النتائج** |
| `scanner.py` | مسح أقدم/مكمل |

`run_core_toolkit(root, user_question=...)` يشغّل أدوات حسب السؤال (مثلاً هات ملف → find + read).

## أسئلة حرة بعد السحب

مع `active_repo` صالح:

- أسئلة قياس/ملفات → EARLY bind أو Phase-4 → `repo_understand`
- أوصاف بوت جديدة → **لا** تُربط بالمستودع — مسار التوليد

## Git من الشات

- PAT يُطلب عند الحاجة ويُعامل بحذر (sanitize)
- Push يحتاج تأكيد
- لا تخلط توكن التيليجرام مع PAT GitHub
