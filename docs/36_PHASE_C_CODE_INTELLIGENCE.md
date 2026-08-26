# Phase C — Codebase Intelligence

> بعد إغلاق B. الهدف: فهم المستودع بدقة قبل التعديل (Cursor-class foundation).

## أدوات رسمية

| مكوّن | المكتبة / المسار |
|--------|------------------|
| AST | **tree-sitter** + **tree-sitter-python** |
| Graph | `code_intelligence/symbol_graph.py` |
| Retrieval | BM25 (`rank-bm25`) + vectors محلية / Voyage اختياري |
| Blast radius | `code_intelligence/blast_radius.py` |

## API

```python
from lumen.engine.services.code_intelligence import (
    index_python_repo,
    build_symbol_graph,
    hybrid_search,
    blast_radius,
)

idx = index_python_repo("/path/to/repo")
g = build_symbol_graph("/path/to/repo")
hits = hybrid_search("/path/to/repo", "where is auth validated?")
impact = blast_radius("/path/to/repo", path="pkg/a.py", symbol_name="helper")
```

## Embeddings

- افتراضي: `local_hash` (offline، حتمي)
- اختياري: `CODE_EMBEDDING_PROVIDER=voyage` + `VOYAGE_API_KEY` → Voyage Code embeddings API

## اختبارات

```bash
pip install tree-sitter tree-sitter-python rank-bm25
PYTHONPATH=. pytest tests/test_phase_c_code_intelligence.py -q
```


## تعزيزات (أدوات حقيقية)

| أداة | الدور |
|------|------|
| **tree-sitter Query** | استخراج calls/defs الرسمي |
| **Jedi** | goto definition + find references على مستوى المشروع |
| **rank-bm25** | retrieval معجمي |
| **fastembed** (اختياري) | embeddings عصبية محلية |
| **Voyage API** (اختياري) | embeddings كود متخصصة |
| **persistent_index** | حفظ graph على القرص |

Critic يرفق `details.code_intelligence` بعد فحص المشروع المولَّد.


## Preflight قبل التعديل (مسار Cursor-like)

عند `edit_file` / `apply_patch` يُحسب:

1. Tree-sitter blast radius للملف/الرموز
2. Jedi `find_references` على الرموز المستهدفة
3. Hybrid BM25 + vector مع **RRF**
4. `risk`: low|medium|high + قائمة الملفات المتأثرة

```bash
CODE_INTEL_PREFLIGHT=1   # افتراضي
```

النتيجة داخل `tool_result.preflight` للـ agent.


## C+ اتجاه المنافسة العالمية (نطاق المنتج)

المنتج **مش تيليجرام فقط**: بوتات (Telegram / Discord / WhatsApp) + تطبيقات + مواقع — نفس طبقة فهم الكود.

| طبقة | أداة |
|------|------|
| AST متعدد | tree-sitter Python + JavaScript |
| فهرسة تزايدية | `ensure_incremental_index` (mtime) |
| Vector store | numpy persistent (`.lumen_code_index/`) |
| Hybrid | BM25 + vectors + RRF + vector store |
| قبل التعديل | preflight (Jedi + blast) |
| بعد التعديل | postflight (syntax + reindex) |

```bash
PYTHONPATH=. pytest tests/test_phase_c_code_intelligence.py -q
```
