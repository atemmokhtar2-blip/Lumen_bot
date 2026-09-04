# زمن تشغيل الوكيل (Cline runtime)

## المكوّنات

| ملف | وظيفة |
|-----|--------|
| `agent_brain.py` | `decide`، استدعاء المزوّد، usage، failover |
| `agent_loop.py` | حلقة الخطوة، حدود التقدم، إعادة تخصيص النموذج |
| `agent_fs.py` / `tools.py` | أدوات الملفات والأوامر |
| `agent_acceptance.py` | فحوصات قبول المشروع |
| `provider_agent.py` | جسر تشغيل من مسار التوليد |
| `model_router.py` | اختيار النموذج |
| `executor.py` | تنفيذ أوامر بأمان نسبي |
| `structured_recovery.py` | استرداد من مخرجات غير صالحة |
| `mcp_bridge.py` | جسر MCP إن فُعّل |
| `agent_code_intel.py` | رموز/مراجع/بحث كود |

## حلقة العمل (مفاهيم من `agent_loop`)

1. تحديد المهمة/الهدف وملفات السياق
2. `select_model_for_goal` (قد يتغيّر كل خطوة حسب last_tool / soft_parse_fail)
3. بناء system/user + تلميح JSON للأدوات
4. `decide` → أداة واحدة
5. تنفيذ الأداة؛ `progress_bus` ينشر `tool_start` / نتائج مع **provider/model**
6. تحديث `no_progress_streak`؛ إيقاف عند `no_progress_limit` أو ميزانية زمنية/خطوات
7. فحص `is_cancelled(user_id)`
8. تكرار حتى `finish` أو حد أقصى

## أدوات الوكيل

أسماء الأدوات مُعرَّفة في الحلقة (مثل قراءة/كتابة، patch، بحث، أوامر، متصفح، skills، `finish`). العقد: **كائن JSON واحد لكل دور** — ممنوع tools المدمجة للمزوّد.

## القبول

`agent_acceptance` / `acceptance_check` في multi_agent:

- وجود نقطة دخول للمشروع
- لا أخطاء syntax حرجة تمنع التشغيل
- لا يُعتبر النجاح لمجرد score جزئي إذا فشل شرط حرج

## التقدم والإلغاء

- `progress_bus`: stack handlers حتى لا يمسَح worker الـ handler الخارجي
- `generation_cancel`: ملف/علامة per user عبر العمليات
- واجهة تيليجرام تعرض التحديثات عبر `progress_tracker`

## user_id

يُمرَّر من البوت عبر multi-agent / coding_agent / temporal stages حتى الإلغاء والجلسة يبقيان صحيحين على workers منفصلة.
