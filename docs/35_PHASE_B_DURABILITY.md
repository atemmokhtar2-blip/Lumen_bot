# Phase B — Durability & Scale

> بعد إغلاق Phase A. الهدف: جلسات توليد تتحمّل crash/429 + ضغط متزامن.

## المكوّنات

| مكوّن | مسار | دور |
|--------|------|-----|
| File/Redis journal | `multi_agent/durable_workflow.py` | مصدر حقيقة للخطوات + resume |
| Workflow engines | `workflow_engine.py` | `memory` / `redis_streams` / **`temporal`** |
| Temporal defs | `temporal_defs.py` | Workflow + Activities رسمية (`temporalio`) |
| Temporal worker | `python -m lumen.engine.services.multi_agent.temporal_worker` | Worker رسمي |
| Worker pool | `worker_pool.py` | Pool محلي + backpressure للـ resume |
| Concurrency | `concurrency.py` | `orchestration_slot` (عام + لكل مستخدم) |

## تشغيل Temporal (أدوات رسمية)

```bash
# 1) خادم Temporal (مثال رسمي)
docker run --rm -p 7233:7233 temporalio/auto-setup:latest

# 2) المكتبة الرسمية
pip install temporalio

# 3) Worker
export TEMPORAL_HOST=localhost:7233
export TEMPORAL_NAMESPACE=default
export TEMPORAL_TASK_QUEUE=tbe-generate
export TBE_WORKFLOW_ENGINE=temporal
bash scripts/hosting/run_temporal_worker.sh
# أو: python -m lumen.engine.services.multi_agent.temporal_worker
```

## بدون Temporal (إنتاج بالـ journal)

```bash
export TBE_WORKFLOW_ENGINE=redis_streams   # مع REDIS_URL
# أو memory للتطوير
export MULTI_AGENT_WORKER_POOL=2
export MULTI_AGENT_QUEUE_LIMIT=50
export MULTI_AGENT_MAX_CONCURRENT=4
export MULTI_AGENT_MAX_PER_USER=2
```

## مسار resume بعد crash / 429

```text
journal.write(step) بعد كل agent
  → process crash
  → resume_generate(state_id)
  → Orchestrator.resume_run(from_step=next_step_after)
```

أو عبر Temporal activity `lumen_resume_generate` / `submit_resume_job`.

## اختبارات

```bash
PYTHONPATH=. pytest tests/test_phase_b_durability.py -q
```
