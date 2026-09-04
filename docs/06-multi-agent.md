# Multi-agent

## الموقع

`lumen/engine/services/multi_agent/`

مكوّنات بارزة:

- `orchestrator.py` — تنسيق
- `engine_turn.py` — دور يعتمد على `agent_brain.decide` (ليس switch مزوّد قديم)
- `architect_backends.py` — مواصفات؛ `BridgeSpecBackend` يستدعي `engine_groq_bridge.analyze_and_prepare` (قواعد، لا LLM translate)
- `coding_agent.py` — جلسة برمجة
- `hitl.py` / `langgraph_pipeline/` — موافقة بشرية على الخطة/التسليم
- `acceptance_check.py` — بوابة قبول

## HITL

رسائل الموافقة تُربط عبر `multi_agent_bridge` وحالة في الجلسة الدائمة (`multi_agent_pending`, …).

## ربط النموذج

نفس كتالوج + راوتر التوليد؛ المخطّط والعامل يمكن أن يحصلا على نماذج مختلفة حسب `task` (plan vs build) عبر `select_model_for_goal`.
