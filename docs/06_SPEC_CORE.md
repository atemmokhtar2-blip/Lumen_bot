# محرك التوليد الحتمي — spec_core

## الفكرة

توليد بوت تيليجرام **بدون اعتماد على LLM في كتابة الكود**:

```
BotSpec / مواصفات مترجمة
    → validate
    → plan
    → write_project (emitters)
    → validate_project
    → مجلد مشروع جاهز (+ zip أحياناً)
```

الملف المحوري: `lumen.engine/spec_core/pipeline.py` → `build_from_spec`.

## المكوّنات

| جزء | مسار | وظيفة |
|-----|------|--------|
| Schema | `spec_core/schema.py` | `BotSpec` وأنواع المواصفات |
| Registry | `spec_core/registry.py` | `CAPABILITIES` — كل ميزة معروفة |
| Planning | `spec_core/planning.py` | خطة من المواصفات |
| Coding | `spec_core/coding*.py` + emitters | كتابة الملفات |
| Handlers | `spec_core/coding_handlers/` | معالجات أوامر مولَّدة |
| Validation | `spec_core/validation` (عبر pipeline) | قبول/رفض المشروع |
| Command map | `spec_core/command_map.py` | ربط أوامر بميزات |
| Arabic intent | `spec_core/arabic_intent_engine.py` | فهم نية عربية مساعدة |
| Anti-hallucination | `services/anti_hallucination` | بوابة ضد اختراع ميزات |

## كيف تستخدمه

```python
from lumen.engine.spec_core.pipeline import build_from_spec
from pathlib import Path

result = build_from_spec(
    {"features": [...], ...},  # أو BotSpec
    out_dir=Path("/tmp/out/user123"),
    request="بوت فيه /start و /help",
)
# result.ok, result.project_path, result.errors
```

من واجهة التيليجرام يتم عبر `lumen.bot/generation_flow.py` ومسارات `force_generate` / تأكيد المستخدم.

## Pipeline الأوسع (core)

`lumen.engine/pipeline/` يوفّر مراحل:

1. Parse  
2. ComposeBlueprint  
3. ValidateBlueprint  
4. Generate  
5. ValidateOutput  
6. Package  

`PipelineOrchestrator` هو الوحيد اللي يعرف ترتيب المراحل. السياق: `GenerationContext` / `ArtifactStore` / أدوار المحركات.

## قاعدة

أي ميزة غير موجودة في `CAPABILITIES` **لا تُنفَّذ ككود حقيقي** — إما clarification أو رفض. هذا جوهر منع الهلوسة.

## UX من وصف المستخدم + مطابقة بعد التوليد

- `BotSpec.ux` (في `schema.py`): ترحيب، أزرار قائمة، رقم تواصل، حالات طلب — من وصف المستخدم/الترجمة وليس قالب ثابت.
- المولد يفضّل `ux.menu_buttons` و `ux.welcome` عند وجودهما (`coding_handlers/keyboards.py`, `handlers.py`).
- بعد التوليد يمكن مقارنة المشروع بالوصف عبر `services/fidelity_compare.py` (محلي ± Gemini) ثم `apply_repairs_to_spec` وإعادة بناء.
- مدفوعات تيليجرام: `PreCheckoutQueryHandler` / `SUCCESSFUL_PAYMENT` وليست أوامر `/payment_*`.
- قدرات `creator`/`content_*` تتطلب schema تجارة كامل عند إرفاق `market.py`.
