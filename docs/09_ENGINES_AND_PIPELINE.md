# المحركات وخط الأنابيب

## Pipeline

`telegram_bot_engine/pipeline/`

المراحل بالترتيب (Orchestrator فقط يعرف الترتيب):

1. **Parse** — فهم الطلب الأولي  
2. **ComposeBlueprint** — بناء المخطط  
3. **ValidateBlueprint** — التحقق  
4. **Generate** — التوليد  
5. **ValidateOutput** — التحقق من المخرجات  
6. **Package** — التعبئة (zip/مسار)

كل مرحلة: `requires` / `provides` على السياق. الفشل مع `fail_fast` يوقف السلسلة.

## السياق (Context)

بعد الفصل المعماري:

| جزء | ملف | معنى |
|-----|-----|------|
| Execution / Generation context | `core/context.py` | وسيط المراحل |
| ArtifactStore | `core/artifact_store.py` | نواتج مكتوبة بأدوار (typed) |
| Metadata | `core/metadata.py` | بيانات وصفية |
| State | `core/state.py` | شيء يعيش عبر الزمن (Project, Run…) — **مش** artifact |

**Artifact = ناتج مرحلة**  
**State = كيان طويل العمر**

## المحركات (engines/)

كل محرك يعلن عن نفسه (self-declaration):

- `get_engine_id()`
- `get_priority()`
- `get_dependencies()`
- `get_role()` — planning / generation / …  

`core/bootstrap.py` يجمع المحركات من الإعلان الذاتي؛ الـ registry لا يخزّن معرفة يدوية بكل محرك.

أمثلة تحت `engines/generators/`: تخطيط مشروع، نظام ملفات، git، نشر حي، هيكل…

## Planning ≠ Generation

```
Requirement → Planning → Validated Plan → Generation
```

المولّد لا يتخذ قرارات معمارية منفردة خارج الخطة المعتمدة.

## تشغيل محرك يدوياً (تطوير)

عبر bootstrap/manager حسب العقود في `core/contracts.py` و `core/manager.py` — للتكامل الداخلي، مش لواجهة المستخدم.
