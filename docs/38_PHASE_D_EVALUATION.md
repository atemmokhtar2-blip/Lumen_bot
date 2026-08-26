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
