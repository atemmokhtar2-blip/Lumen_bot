# المعمارية

## الطبقات

```
Telegram (PTB handlers)
    → lumen/bot/routers, ui, session_store
        → lumen/bot/generation_flow / multi_agent_bridge
            → lumen/engine (cline_runtime, multi_agent, llm)
                → tools (agent_fs, shell, browser, …)
                → hosting / object storage
```

- **Presentation:** `lumen/bot/` — لا منطق اختيار نموذج هنا؛ يمرّر الطلب للمحرك.
- **Application wiring:** `lumen/bootstrap.py` — مستودعات tenant/job/billing.
- **Domain:** `lumen/domain/` — عقود بدون تفاصيل بنية تحتية.
- **Infrastructure:** `lumen/infrastructure/persistence/` — Mongo/Redis adapters.
- **Engine:** `lumen/engine/services/` — التوليد، الوكيل، LLM، الاستضافة، الذاكرة.

## تدفق رسالة توليد (مختصر)

1. `message_router` / handlers: allowlist، rate limit، استعادة جلسة Redis.
2. اكتشاف نية توليد أو أوامر UI.
3. `analyze_and_prepare` (`engine_groq_bridge`) — **قواعد وcapabilities فقط**، بدون LLM translate.
4. بناء IR / استدعاء multi-agent أو Cline agent loop.
5. اختيار نموذج: `select_model_for_goal` → Foundry إن وُجد وإلا R2 + `model_catalog`.
6. `agent_brain.decide` → `_invoke_choice` → مزوّد HTTP.
7. تنفيذ أدوات على ملفات المشروع.
8. بوابة قبول + smoke test قبل ZIP (`generation_steps`).
9. تحديث تقدم عبر `progress_bus` → تعديل رسالة تيليجرام.

## مبدأ LLM واحد

- المصدر: `lumen/engine/services/llm/model_catalog.py`
- التوجيه: `model_router.select_model` / `select_model_for_goal` + `r2_allocator` + `foundry_router`
- التنفيذ: `cline_runtime/agent_brain.py`
- **ممنوع:** مسارات `translate_request` / `chat_request` / `llm/facade` / `llm_budget_gate` (محذوفة)

## الاستمرارية

- جلسات المستخدم: Redis (`session_store`) — انظر `03-session-context.md`
- اشتراك Pro: Redis + Mongo (`subscription_store`) — انظر `09-pro-subscription.md`
