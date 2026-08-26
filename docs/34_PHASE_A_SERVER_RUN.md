# Phase A — تشغيل السيرفر (Cline + Multi-Agent)

> إغلاق بند A-5 من `docs/33_AGENTS_12_PHASES.md`.  
> المسار الوحيد لطلبات المستخدم: **Cline SDK** عبر `execute_ir` → `cline_runtime`.  
> المحرك الحتمي (catalog) **محظور** على مسار المستخدم.

## متغيرات إلزامية

```bash
# Cline sole engine
CLINE_ENABLED=1
CLINE_MODE=agent
CLINE_LLM_PROVIDER=gemini
GEMINI_MODEL=gemini-3.6-flash
GEMINI_API_KEYS=key1,key2   # على السيرفر فقط — لا تُرفع لـ git

# Multi-agent orchestration
MULTI_AGENT_ORCHESTRATOR=1
MULTI_AGENT_MAX_ATTEMPTS=4

# Agent loop
CLINE_AGENT_MAX_STEPS=24
```

## حظر المسار الحتمي

- `ENGINE_MODE_FORCE` لأي وضع catalog/hybrid/infinite **يُتجاهل** ويُحوَّل إلى `CLINE`.
- لا تستخدم `generate_bot` / templates كمسار أساسي لطلبات المستخدم.
- راجع `lumen/engine/services/engine_router.py`.

## مسار التشغيل

```text
User → translation → BuildIR (CLINE)
  → Orchestrator (إن MULTI_AGENT_ORCHESTRATOR=1)
       Planner → ExecutionPlan
       Worker  → execute_ir → agent_loop + agent_fs
       Critic  → findings + smoke
       فشل → deterministic_repair → incremental_repair → Critic
  → deliver / host
```

## تحقق سريع بعد النشر

```bash
# 1) عقود Phase A (بدون مفاتيح)
PYTHONPATH=. python -m pytest tests/bot_bench/test_phase_a_contracts.py -q

# 2) وجود المزوّد
python -c "from lumen.engine.services.cline_runtime.model_router import describe_runtime; print(describe_runtime())"

# 3) تشغيل البوت/API
python main.py
# أو
python api_main.py
```

## التكلفة (Phase A)

`run_report` يكتب حقل `cost` يشمل:

- `attempts` / `max_attempts`
- `usage` من مزود LLM عند توفره (`prompt_tokens` / `completion_tokens` / `total_tokens`)
- إشارات `execution_plan_present` و `findings_count`

التقارير تحت: `$OUTPUT_DIR/multi_agent_reports/` (أو `~/.lumen/multi_agent_reports`).

## ممنوع

- Mock LLM كبديل دائم في الإنتاج.
- سكربتات تقليد تولّد ملفات بوت خارج `agent_fs` / Orchestrator.
- فتح المرحلة B قبل إغلاق بنود A المتبقية في `33_AGENTS_12_PHASES.md`.


## Analytics (Phase A)

```python
from lumen.engine.services.multi_agent.trajectory import failure_board, analyze_trajectory
failure_board(limit=20)
analyze_trajectory("<state_id>")
```

## Model difficulty + cache

```bash
# decision cache (default on)
CLINE_DECISION_CACHE=1
CLINE_DECISION_CACHE_TTL=1800
```

```python
from lumen.engine.services.cline_runtime.model_router import (
    estimate_task_difficulty, select_model_for_goal, cache_stats
)
```
