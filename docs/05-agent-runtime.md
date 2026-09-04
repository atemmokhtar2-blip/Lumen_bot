# زمن تشغيل الوكيل

## الملفات الأساسية

| ملف | دور |
|-----|-----|
| `lumen/engine/services/cline_runtime/agent_brain.py` | استدعاء النموذج + failover |
| `lumen/engine/services/cline_runtime/agent_loop.py` | حلقة الأدوات، إعادة تخصيص النموذج لكل خطوة |
| `lumen/engine/services/cline_runtime/model_router.py` | اختيار النموذج |
| `lumen/engine/services/progress_bus.py` | بث التقدم للواجهة |
| `lumen/engine/services/generation_cancel.py` | إلغاء عبر marker |

## الحلقة

1. اختيار نموذج للجولة (`select_model_for_goal` مع goal/task/files/tools)
2. `decide` → JSON أداة واحدة
3. تنفيذ الأداة على مساحة المشروع
4. تحديث progress (اسم المزوّد/النموذج، الأداة، الحالة)
5. عند الحاجة: إعادة تخصيص النموذج (مثلاً بعد فشل parse أو نوع خطوة مختلف)
6. التحقق من الإلغاء بين الخطوات
7. `finish` أو استنفاد الميزانية الزمنية/الخطوات

## الأدوات (أسماء من الكود)

تشمل قراءة/كتابة ملفات، patch، بحث، أوامر، متصفح، skills، `finish` — انظر `AGENT_TOOL_NAMES` في agent_loop.

## القبول

مسارات التوليد تمر على فحوصات قبول (وجود مدخل، لا أخطاء syntax حرجة، …) قبل اعتبار المشروع ناجحًا للتسليم.

## user_id

يُمرَّر عبر multi-agent / coding session حتى تبقى الجلسة والإلغاء مرتبطين بالمستخدم الصحيح عبر الـ workers.
