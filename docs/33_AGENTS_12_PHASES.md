# نظام الـ Agents — 12 مرحلة · الحالة · قواعد المطور

> **إلزامي لكل مطور / وكيل AI يشتغل على هذا المشروع**  
> اقرأ هذا الملف قبل أي تعديل على `multi_agent/` أو `cline_runtime/`.  
> المنصة **تحت البناء**. المسار الوحيد لتوليد طلبات المستخدم العامة: **Cline SDK** عبر `execute_ir` → `cline_runtime`.  
> المحرك الحتمي (catalog generation) **مُطهَّر من مسار المستخدم**.

---

## قاعدة ذهبية — ممنوع السكربتات الوهمية

### يُمنع منعًا باتًا

1. كتابة سكربتات “تقليد” تولّد ملفات بوت وتدّعي أنها المحرك.
2. Mock LLM كبديل دائم عن المزود في الإنتاج (مسموح فقط في unit tests معزولة).
3. استدعاء `generate_bot` / catalog templates كمسار أساسي لطلبات المستخدم العامة.
4. إصلاحات سطحية: طباعة `SUCCESS` بدون المرور على `agent_fs` / `Critic` / `trajectory`.
5. مسح أو تجاهل `CritiqueFinding` و `ExecutionPlan` و `incremental_repair`.

### يُلزم

1. استخدام **الأدوات الرسمية** فقط:
   - `lumen.engine.services.cline_runtime.agent_fs.run_tool`
   - `agent_loop.run_agent` / `agent_brain.decide`
   - `multi_agent.Orchestrator` + roles (`architect`/`builder`/`critic`)
   - `deterministic_repair.apply_deterministic_repairs` (طبقة محلية، ليست سكربت خارجي)
   - `project_context.pack_project_context` عبر `agent_fs`
2. أي توليد جديد يمر: **Planner → Worker(Cline) → Critic → (Repair تزايدي إن فشل)**.
3. بعد كل تغيير جوهري: اختبار حي محدود بمفتاح واحد + `CriticAgent` على المخرجات.
4. تحديث هذا الملف عند إكمال بند من الـ 12.

**الخلاصة للمطور:**  
> لو التعديل مش ماشي من خلال عقود `multi_agent` + `cline_runtime` الرسمية، **مش مقبول**.

---

## خريطة الـ 12 مرحلة (الفجوات الاستراتيجية)

هذه هي محاور النضج نحو منافسة أدوات بمستوى Cursor — **ليست** متاجر السوق الرقمي.

| # | المرحلة | الهدف | الحالة | ملاحظات |
|---|---------|--------|--------|---------|
| **1** | Agents متكامل (Planner/Worker/Critic) | أدوار مفصولة + حلقة إصلاح | **مغلق تشغيليًا (A)** | roles + orchestrator + plan/findings/repair + bot-bench + forced finish + cost. اختياري لاحقًا: Task Tree / Swarm / LangGraph |
| **2** | فهم المستودع (Codebase Intelligence) | AST/Graph + retrieval | **ضعيف / لم يبدأ كمرحلة C** | يوجد `repo_understanding` قديم — ليس Tree-sitter KG ولا blast-radius |
| **3** | Self-Correction | Observe→Critique→Fix مغلق | **مغلق (A)** | Critic + trajectory + repair + smoke + `analyze_trajectory` + `failure_board` |
| **4** | UX Power-User | Dashboard / Diff / Pause | **لم يبدأ (E)** | تيليجرام فقط |
| **5** | Model Router الذكي | plan/build/critique + تكلفة | **مغلق (A)** | `select_model` + `estimate_task_difficulty` + `select_model_for_goal` + `cache_get/set` + usage cost |
| **6** | Evaluation / Bot-bench | مقاييس نجاح ثابتة | **لم يبدأ رسميًا (D)** | تم اختبار حي يدوي؛ لا benchmark مُصدَّر في CI |
| **7** | Scalability | Workers أفقية + backpressure | **Phase B نشطة** | journal + resume + Temporal workflow/worker رسمي + worker_pool backpressure — انظر `docs/35_PHASE_B_DURABILITY.md` |
| **8** | Computer Use / Browser | Playwright داخل sandbox | **لم يبدأ (F)** | |
| **9** | Skills / MCP Registry | إضافات مفتوحة | **بدائي** | `mcp_bridge.py` رقيق |
| **10** | Event-driven Agents | صحوة على أحداث | **لم يبدأ (F)** | resume/checkpoint فقط |
| **11** | تكاملات خارجية عميقة | GitHub PR/Issues / Linear | **جزئي سطحي** | clone/import؛ ليس MCP GitHub كامل |
| **12** | DX + توثيق للمطورين | أدلة إضافة Engine/Skill/Tool | **هذا الملف + docs/** | يلزم أمثلة عملية إضافية |

---

## تفصيل المرحلة A — ما اكتمل / ما تبقى

### اكتمل في الكود (مسارات رسمية)

| بند | أين |
|-----|-----|
| Planner = Architect + `ExecutionPlan` | `roles/architect.py`, `plan_contract.py` |
| Worker = Builder عبر **Cline `execute_ir` فقط** | `roles/builder.py` |
| Critic منظم + `CritiqueFinding` | `roles/critic.py`, `findings.py` |
| Repair من findings | `repair.py` |
| إصلاح تزايدي (لا regenerate) | `repair_worker.py` |
| طبقة محلية بدون LLM | `deterministic_repair.py` (layout: `main.py` + `app/handlers.py`) |
| Snapshot مساحة العمل عبر `agent_fs` | `project_context.py` |
| Trajectory JSONL | `trajectory.py` |
| Model router حسب `task` | `cline_runtime/model_router.py` |
| سياسة repair: read قبل edit | `agent_loop.py` |
| افتراضي Gemini: `gemini-3.6-flash` | `model_router` / `agent_brain` / `gemini_client` |
| Smoke: mock `callback_query` | `bot/generation_steps/helpers.py` |
| اختبار حي: decide + agent_loop + Critic PASS | تم محليًا بمفاتيح (غير مُلزمة في git) |
| Trajectory analytics + failure board | `trajectory.analyze_trajectory` / `failure_board` |
| Task difficulty + decision cache | `model_router.estimate_task_difficulty` / `cache_*` / `CLINE_DECISION_CACHE` |
| Bot-bench في CI | `.github/workflows/ci.yml` → `tests/bot_bench/` |

### ناقص لإغلاق A قبل الانتقال لـ B

| # | البند | الحالة بعد الإغلاق |
|---|--------|-------------------|
| 1 | Bot-bench رسمي (10 سيناريوهات) | **مغلق** — `tests/bot_bench/test_phase_a_contracts.py` (عقود رسمية فقط) |
| 2 | إجبار `finish` بعد deliverables | **مغلق** — `agent_loop`: acceptance ok أو نَجمتين → finish إجباري |
| 3 | تمرير `execution_plan` / findings عبر metadata | **مغلق** — `builder` يضع plan + findings + mode على `ir.metadata` |
| 4 | قياس التكلفة في `run_report` | **مغلق** — حقل `cost` (attempts + usage tokens من المزود) |
| 5 | وثيقة تشغيل السيرفر | **مغلق** — `docs/34_PHASE_A_SERVER_RUN.md` |

> **Phase A — مغلقة للإكمال التشغيلي أعلاه.**  
> ما زال اختياريًا لاحقًا داخل محور 1 (Task Tree / Swarm / LangGraph) لكنه **ليس** مانع انتقال لـ B.  
> **قرار الانتقال:** يمكن فتح المرحلة B (Temporal/Scale) بعد مراجعة إنتاجية قصيرة لمسار Planner→Worker→Critic.

---

## المراحل التالية (ملخص تنفيذي)

### B — Durability & Scale (بعد A) — **قيد التنفيذ / مفعّلة في الكود**
- `TemporalWorkflowEngine` يبدأ workflow رسمي `LumenMultiAgentGenerate` + worker module
- Redis/file journal + `resume_generate` بعد crash/429
- `worker_pool` + `orchestration_slot` backpressure
- توثيق: `docs/35_PHASE_B_DURABILITY.md`

### C — Codebase Intelligence
- Tree-sitter → symbol graph
- hybrid retrieval (BM25 ثم embeddings)
- blast-radius قبل التعديل

### D — Evaluation
- `tests/bot_bench/` سيناريوهات ثابتة
- مقاييس: success rate، attempts، latency، cost

### E — UX
- Next.js: runs، agents، diff، pause/cancel
- SSE من API

### F — Skills, Browser, Events, Integrations
- Skills registry + MCP servers
- Playwright في sandbox
- event bus (Telegram / GitHub webhook / schedule)

### G — DX
- `docs/ADD_ENGINE.md`, `docs/ADD_SKILL.md`, أمثلة PR

---

## مسار التشغيل الرسمي (لا تختصر)

```text
User request
  → message_router / translation
  → BuildIR (engine_mode=CLINE)
  → multi_agent.Orchestrator (إن مفعّل)
        Planner (architect) → ExecutionPlan
        Worker (builder) → execute_ir → cline agent_loop + agent_fs tools
        Critic → findings + smoke + gen_verify
        إن فشل → deterministic_repair → incremental_repair (Cline edit) → Critic
  → deliver / host
```

متغيرات حرجة:

```bash
CLINE_ENABLED=1
CLINE_LLM_PROVIDER=gemini          # أو groq / qwen حسب المتاح
GEMINI_MODEL=gemini-3.6-flash
GEMINI_API_KEYS=...                # على السيرفر فقط — لا تُرفع لـ git
MULTI_AGENT_ORCHESTRATOR=1
MULTI_AGENT_MAX_ATTEMPTS=4
```

---

## للمراجع السريعة في الكود

| عقد | مسار |
|-----|------|
| Orchestrator | `lumen/engine/services/multi_agent/orchestrator.py` |
| Roles | `lumen/engine/services/multi_agent/roles/` |
| Cline tools | `lumen/engine/services/cline_runtime/agent_fs.py` |
| Cline loop | `lumen/engine/services/cline_runtime/agent_loop.py` |
| Engine entry | `lumen/engine/services/engine_router.py` |

---

*آخر تحديث: إغلاق بنود A المتبقية (bot-bench / forced finish / metadata / cost / server run doc).*
