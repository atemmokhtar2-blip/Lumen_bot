# إصلاح الضعف الثاني: "الانتظار الميت" (Dead Wait) — دقيق وحقيقي

## التحليل (تم)
- [x] قراءة progress_tracker.py — ProgressHeartbeat بفاصل 3.0s موجود ✓
- [x] قراءة agent_loop.py — _emit_step متوصل بعد كل tool call عبر ContextVar ✓
- [x] قراءة message_generation.py — feed بيتعمل create ويتفعل ✓
- [x] قراءة generate_bridge.py — **مش بيمرّر feed!** مشكلة حرجة ✗
- [x] قراءة callback_router.py — **مفيش busy guard** ضد concurrent generation ✗
- [x] قراءة format_agent_action — بيستخدم "الخطوة N" (مصطلح تقني) ✗

## الإصلاحات
- [x] إصلاح 1: generate_bridge.py — تمرير feed= إلى run_with_heartbeat
- [x] إصلاح 2: callback_router.py + message_generation.py — busy guard يمنع concurrent generation + رد ودي
- [x] إصلاح 3: progress_tracker.py — إزالة "الخطوة N" + basename masking + أيقونات يونيكود
- [x] إصلاح 4: ProgressHeartbeat — عرض تاريخ مختصر (آخر 4 أفعال) + header عربي
- [x] إصلاح 5: رسائل الـ phases الـ fallback — عربية ودودة بدون مصطلحات تقنية

## الاختبار
- [x] اختبارات: feed في generate_bridge (3 test)
- [x] اختبارات: busy guard (5 test) — source inspection + flow verification
- [x] اختبارات: format_agent_action بدون jargon (10 test) — basename, icons, no step leak
- [x] اختبارات: heartbeat history (7 test) — end-to-end + source
- [x] تشغيل كل اختبارات الـ UI: 220 test كلها تعدّت ✓

## الدفع
- [x] commit + push — 4882013
