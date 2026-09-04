# المعمارية

## الهدف

فصل **واجهة تيليجرام** عن **محرك التوليد** عن **الاستضافة**، مع مصدر حقيقة واحد للنماذج (`model_catalog`) ومصدر حقيقة للجلسات (Redis) وللاشتراك المدفوع (Mongo ثم Redis ككاش).

## الطبقات الفعلية في المستودع

```
┌─────────────────────────────────────────────────────────┐
│  Telegram (python-telegram-bot)                         │
│  lumen/bot/routers/message_router.py → handlers/UI      │
└───────────────────────┬─────────────────────────────────┘
                        │ hydrate/persist session_store
                        │ progress_tracker / generation_flow
┌───────────────────────▼─────────────────────────────────┐
│  Application wiring                                     │
│  lumen/bootstrap.py (tenant, job, billing repos)        │
│  lumen/bot/ui + lumen/engine/services/ui_state          │
└───────────────────────┬─────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│  Engine                                                 │
│  cline_runtime (brain, loop, tools, model_router)       │
│  llm (catalog, foundry, r2, key_pool)                   │
│  multi_agent (orchestrator, roles, HITL, temporal_*)    │
│  capability_detection / engine_groq_bridge (rules only) │
└───────────────────────┬─────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│  Hosting + Platform                                     │
│  lumen/hosting/* , sandbox_runtime, live_deployment     │
│  rate limits, mongo users, object storage               │
└─────────────────────────────────────────────────────────┘
```

## تدفق طلب توليد (من الكود)

1. **`handle_message`** (`message_router.py`):
   - `gate_auth_and_rate` ثم `gate_groups`
   - **`get_session_store().hydrate(user_id, user_data)`** قبل أي منطق UI
   - busy guard: إن كان التوليد جاريًا يرفض رسائل جديدة ما عدا إلغاء
   - جسم الرسالة في `_handle_message_body`
   - في `finally`: `persist_ui_session` لكتابة المفاتيح الدائمة

2. **Engine UI** (`ui_state`): إن كانت المرحلة `GEN_SLOTS`، النص يملأ الـ slot الحالي ثم يعيد رسم الرسالة بالأزرار.

3. **نية التوليد** (`message_intent` / generation routers): أفعال صريحة، تأكيد، أو مواصفات بوت.

4. **تحضير المواصفات** بدون LLM ترجمة:
   - `engine_groq_bridge.analyze_and_prepare` + قواعد `translator_client._rule_features_from_text`
   - `BridgeSpecBackend` في multi_agent يستدعي نفس الجسر

5. **التنفيذ**:
   - multi-agent إن `MULTI_AGENT_ORCHESTRATOR` مفعّل (الافتراضي on)
   - وإلا مسار Cline/`provider_agent` + `agent_loop`

6. **النموذج**: `select_model_for_goal` → Foundry أو R2 → `agent_brain.decide`

7. **التسليم**: قبول + smoke test في `generation_steps` ثم ZIP

## حدود المسؤولية

| الطبقة | تفعل | لا تفعل |
|--------|------|---------|
| bot/ | UX، جلسات، دفع، عرض تقدم | اختيار model_id يدوي عشوائي |
| model_catalog | SoT للنماذج | استدعاء HTTP |
| agent_brain | HTTP + JSON tools | تخزين جلسات تيليجرام |
| hosting | تشغيل الحاويات/VM | توليد الكود |

## مبدأ «مسار LLM واحد»

أي مسار توليد يمر على الكتالوج والراوتر والدماغ. لا يوجد مسار موازٍ لـ translate/chat facade.
