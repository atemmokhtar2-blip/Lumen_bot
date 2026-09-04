# Lumen Bot

منصة **توليد وتشغيل بوتات تيليجرام** عبر وكيل برمجة (agent) متعدد الأدوات، مع جلسات Redis، كتالوج نماذج موحّد، استضافة معزولة، واشتراك **Lumen Pro** عبر Telegram Stars.

## ماذا يفعل النظام؟

1. المستخدم يصف البوت داخل تيليجرام (عربي/إنجليزي).
2. البوت يجمع الاحتياجات عبر **Engine UI** (slots) أو مسار توليد مباشر.
3. المحرك يشغّل **وكيلًا** (أو multi-agent: Planner → Worker → Critic → Repair) على مجلد مشروع معزول.
4. اختيار النموذج من **`model_catalog`** عبر Foundry Model Router أو R2 allocator محلي.
5. تقدم حي عبر `progress_bus` على رسالة الحالة في تيليجرام.
6. قبول + smoke test ثم تسليم ZIP عند النجاح.
7. مع Pro: استضافة دائمة ضمن حدود الموارد المعرّفة في الكود.

## مسار LLM الوحيد للتوليد

```
select_model_for_goal / select_model
  → Foundry (إن وُجدت المفاتيح) أو r2_allocator + model_catalog
  → ModelChoice(catalog_id, provider, model_id, base_url)
  → agent_brain.decide → _invoke_choice → HTTP للمزوّد
  → JSON tool واحد → agent_loop ينفّذ على الملفات
```

**محذوف نهائيًا من مسار التوليد:** `translate_request`، `chat_request`، `llm/facade`، `llm_budget_gate`.

## هيكل المستودع

| مسار | الدور |
|------|--------|
| `lumen/bot/` | تيليجرام: routers، UI، session_store، تسليم التوليد |
| `lumen/engine/services/cline_runtime/` | الدماغ، الحلقة، الأدوات، الراوتر |
| `lumen/engine/services/llm/` | كتالوج، Foundry، R2، key_pool |
| `lumen/engine/services/multi_agent/` | أوركسترا متعددة الأدوار + HITL + Temporal اختياري |
| `lumen/engine/services/ui_state/` | آلة حالات Engine UI + تعريف Pro |
| `lumen/hosting/` | تشغيل/إيقاف المستضاف، عزل، فوترة استخدام |
| `lumen/domain/` + `infrastructure/` | مستودعات tenant/jobs/billing |
| `docs/` | التوثيق الرسمي الوحيد المطابق للكود |

## التوثيق

ابدأ من [`docs/00-index.md`](docs/00-index.md). كل نظام له ملف منفصل.

## فرع التطوير

`Lumen`
