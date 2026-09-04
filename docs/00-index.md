# فهرس التوثيق

هذا المجلد هو **المصدر الوحيد** لتوثيق المشروع. أي Markdown خارج `README.md` و`docs/` لا يُعتبر رسميًا.

| # | الملف | المحتوى |
|---|--------|---------|
| 01 | [01-architecture.md](01-architecture.md) | الطبقات، تدفق الطلب من تيليجرام للمحرك |
| 02 | [02-telegram-bot.md](02-telegram-bot.md) | handle_message، البوابات، UI، MarkdownV2، الإلغاء |
| 03 | [03-session-context.md](03-session-context.md) | Redis sessions، المفاتيح الدائمة، Pro TTL |
| 04 | [04-llm-catalog-routing.md](04-llm-catalog-routing.md) | الكتالوج، Foundry، R2، ModelChoice، المفاتيح |
| 05 | [05-agent-runtime.md](05-agent-runtime.md) | agent_brain، agent_loop، أدوات، قبول، تقدم |
| 06 | [06-multi-agent.md](06-multi-agent.md) | Orchestrator، أدوار، HITL، LangGraph، Temporal |
| 07 | [07-generation-delivery.md](07-generation-delivery.md) | من النية إلى ZIP والـ smoke test |
| 08 | [08-hosting.md](08-hosting.md) | orchestration، Firecracker، حدود ضعيفة |
| 09 | [09-pro-subscription.md](09-pro-subscription.md) | أسعار، حدود، دفع Stars، Mongo+Redis |
| 10 | [10-config-env.md](10-config-env.md) | كل متغيرات البيئة ذات الصلة |
| 11 | [11-security.md](11-security.md) | sanitize، أسرار الجلسة، fail-closed |

عند تعارض بين تعليق قديم في الكود وهذا التوثيق، **الكود الحالي في فرع `Lumen` هو المرجع** — حدّث التوثيق معه.
