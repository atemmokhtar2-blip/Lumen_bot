# Multi-Agent

## التفعيل

`MULTI_AGENT_ORCHESTRATOR` — افتراضي **مفعّل** (off فقط بـ 0/false/off).  
`MULTI_AGENT_MAX_ATTEMPTS` — سقف المحاولات (يُقصّ بين 1 و8).

## الأوركسترا (`orchestrator.py`)

حلقة مغلقة:

**Planner (architect) → Worker (builder) → Critic (QA) → Repair → إعادة** حتى PASSED أو نفاد المحاولات.

- `BlackboardStore` — حالة مشتركة
- `AgentRegistry` — تسجيل الأدوار
- `AgentState` — status، attempts، مسار المشروع، user_id
- عند الإنهاء: `persist_state_evaluation` + حدث `generation.finished|failed`

نص المستخدم يُمرَّر عبر `prompt_fence.sanitize_user_text`.

## backends للمواصفات (`architect_backends.py`)

- جسر القواعد: `engine_groq_bridge.analyze_and_prepare` (**بدون** LLM translate)
- backends أخرى حسب الأولوية؛ `DeterministicSpecBackend` ملاذ أخير

## `engine_turn.py`

دور العامل يستدعي **`agent_brain.decide`** — لا switch مزوّد قديم ثابت.

## HITL

- `hitl.py` + `langgraph_pipeline/`
- البوت: `multi_agent_bridge` و`message_generation` يعرضان موافقة خطة/تسليم
- الحالة في الجلسة: `multi_agent_state_id`, `multi_agent_pending`

## Temporal (اختياري)

`temporal_client_run.py`, `temporal_worker.py`, `temporal_stages.py`, `temporal_defs.py` — تشغيل مراحل طويلة عند تهيئة Temporal؛ يجب أن تحمل `user_id` كما في المسار المتزامن.

## عزل العمل

`worktree_isolation.py` — عزل ملفات المحاولة عند التفعيل.
