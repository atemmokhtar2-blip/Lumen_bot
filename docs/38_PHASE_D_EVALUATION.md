# Phase D — Evaluation (منافسة عالمية = قياس)

## القاعدة الثابتة

> كل مرحلة تُبنى **بأدوات حقيقية** (مكتبات/SDK رسمية)، **مش سكربتات وهمية**.  
> معيار النجاح: مقاييس قابلة للقياس — success rate، attempts، latency، cost — عبر منصات متعددة.

## المكوّنات

| مكوّن | مسار |
|--------|------|
| EvalRunRecord | `evaluation/run_record.py` |
| JSONL store | `evaluation/eval_store.py` |
| Bot-bench runner | `evaluation/bot_bench_runner.py` |
| Metrics cost/outcome | `multi_agent/metrics.py` |

## تشغيل

```bash
PYTHONPATH=. python -c "from lumen.engine.services.evaluation import run_bot_bench_suite; import json; print(json.dumps(run_bot_bench_suite(), indent=2))"
PYTHONPATH=. pytest tests/bot_bench/ -q
```

## ملخص المقاييس

`summarize_evals()` يعيد:

- `success_rate`
- `avg_attempts`
- `avg_latency_s`
- `avg_cost_usd`
- `by_platform`


## تعزيز D (مسار حي)

| طبقة | الوظيفة |
|------|---------|
| `cost_model` | تقدير USD من tokens (أسعار عبر env) |
| `live_bridge` | AgentState / run_report → EvalRunRecord |
| `write_run_report` | يكتب أيضًا سجل تقييم تلقائيًا |
| `regression` | مقارنة مع baseline ورفض الانحدار |
| `markdown_report` | تقرير CI مقروء |

```bash
export LUMEN_COST_INPUT_PER_1M=0.15
export LUMEN_COST_OUTPUT_PER_1M=0.60
export LUMEN_EVAL_DIR=/var/lumen/eval
```


## تشغيل حي

```bash
./scripts/hosting/run_phase_d_eval.sh
```

آخر تشغيل مرجعي: `docs/eval/REPORT.md` و `docs/eval/baseline.json`.


## Hard generation (تعميق D)

مسار متوسط/صعب نهاية-لنهاية بدون ادعاء نجاح وهمي:

1. platform scaffold  
2. توسعة multi-module (worker-like)  
3. Critic → deterministic_repair → Critic  
4. `quality_score` (syntax + platform + features)  
5. اختياري: `LUMEN_BENCH_LIVE_LLM=1` → `execute_ir`

CI: `pytest tests/bot_bench/` كامل في `.github/workflows/ci.yml`.
