# Lumen Bot - معالجة نقاط الضعف الخمس في واجهة التيليجرام

## مرحلة 0: الفهم والتحقق من الكود الفعلي ✅
- [x] استنساخ المستودع والوقوف على البنية
- [x] قراءة lumen/bot/sanitize.py → أسرار فقط، لا escape_markdown للـ Markdown
- [x] قراءة lumen/bot/session_store.py → SQLite WAL موجود ومستخدم (load في message_router+commands, save في mongo_sync)
- [x] قراءة lumen/bot/ui/keyboards.py → adapter فقط، الأزرار تُبنى في engine ui_state/controller.py
- [x] قراءة lumen/bot/helpers.py → escape_md يهرب Legacy فقط، safe_edit_text/reply_text تستخدم MARKDOWN (Legacy) + fallback plain
- [x] قراءة lumen/bot/progress_tracker.py → INTERVAL=20s ثابت، 4 رسائل عامة فقط
- [x] قراءة lumen/engine/services/ui_state/controller.py → كل phase يبني أزراره بدون Bottom Nav موحد
- [x] تتبع الاستدعاءات: ForceReply/input_field_placeholder غير مستخدمة إطلاقًا
- [x] بحث واختيار أقوى حل: telegramify-markdown (convert/markdownify/split_markdownv2) + PTB escape_markdown fallback

## الخلاصة (نقاط الضعف المؤكدة):
1. **Markdown Hell**: ParseMode.MARKDOWN (Legacy) + escape_md لا يهرب V2 chars + لا تقسيم رسائل طويلة (يقطع [:4000])
2. **Lost Context**: SessionStore SQLite موجود لكن load يحدث فقط في message_router (نصوص) و commands (/start) — ليس في callbacks
3. **Dead Wait**: INTERVAL=20s + 4 رسائل عامة ثابتة، لا streaming حقيقي بآخر فعل للوكيل
4. **Deep Navigation**: لا Bottom Navigation موحد [رجوع][الرئيسية][إلغاء] في كل رسالة
5. **Placeholders**: ForceReply + input_field_placeholder غير مستخدمين إطلاقًا

## مرحلة 1: الضعف الثالث - Markdown Hell (الأساس) ✅
- [x] البحث واختيار أقوى حل: telegramify-markdown + تقسيم الرسائل الطويلة
- [x] تنفيذ وحدة telegram_render.py جديدة (convert/markdownify/split) — REAL solution
- [x] تحديث escape_md في helpers.py لـ MarkdownV2 (backward-compat)
- [x] تحديث safe_edit_text / safe_reply_text لدعم MarkdownV2 + تقسيم الرسائل الطويلة (+reply_markup)
- [x] تحديث commands.py (help_cmd reply_text MARKDOWN → V2 آمن) + إزالة import الميت
- [x] تحديث message_router.py (replies الوكيل → safe_reply_text V2)
- [x] تحديث message_generation.py (HITL edit Legacy Markdown → safe_edit_text V2)
- [x] اختبار التنفيذ (telegramify-markdown حقيقي: escape_all/markdownify/split 6175→4 chunks)
- [x] التحقق من التكامل (grep: لا ParseMode.MARKDOWN Legacy متبقٍ في lumen/)

## مرحلة 2: الضعف الأول - Lost Context (UserSession في DB) ✅
- [x] فحص session_store.py الحالي ومصدر البيانات (SQLite WAL, 13 مفتاح دائم)
- [x] إضافة load() في callback_router (handle_ui_callback) — كان مفقوداً (الجذر)
- [x] إضافة engine_ui لمفاتيح session_store.save الدائمة (كان no-op → يضيع UI state)
- [x] cap needs list إلى 12 (منع blob bloat)
- [x] اختبار استمرارية السياق عبر "restart" (SessionStore جديد على نفس DB)
- [x] التحقق: pending_run/chat_history/engine_ui تبقى + الأسرار تُحذف (لا تسريب)

## مرحلة 3: الضعف الثاني - Dead Wait (Streaming + edit_message_text) ✅
- [x] فحص progress_tracker.py الحالي
- [x] تنفيذ streaming تحديثات كل ~3 ثواني (AgentProgressFeed + ContextVar propagation)
- [x] اختبار التحديثات الحية (12 test pass: feed thread-safety, format_agent_action, contextvar propagation, _emit_step fallback, e2e streaming)
- [x] التحقق من التكامل (run_with_heartbeat → set_progress_callback → asyncio.to_thread → run_agent reads _CURRENT_ON_STEP)

## مرحلة 4: الضعف الرابع - Deep Navigation (Bottom Navigation ثابت) ✅
- [x] فحص keyboards.py + controller.py الحالي
- [x] تنفيذ Bottom Navigation موحد [رجوع][الصفحة الرئيسية][إلغاء] في كل مرحلة (controller.py buttons_for_state)
- [x] إضافة action "back" في catalog + handler في apply_action (previous phase navigation)
- [x] تنظيف buttons_for_event (إزالة home rows مكررة — bottom nav يوفرها الآن)
- [x] اختبار التنقل (9 test pass: bottom nav في كل phase, back transitions, catalog, no duplicates)
- [x] التحقق من التكامل مع كل الخطوات

## مرحلة 5: الضعف الخامس - Placeholders & Hints (ForceReply + input_field_placeholder)
- [x] فحص الاستخدامات الحالية للـ prompts
- [x] تنفيذ ForceReply مع input_field_placeholder
- [x] اختبار التلميحات (17 test pass: should_send_force_reply, _placeholder_for per slot/phase, ForceReply construction with real PTB 22.7, text+placeholder truncation, integration in callback_router+message_router)
- [x] التحقق من التكامل (callback_router sends ForceReply after render when awaiting_text=1; message_router sends ForceReply after slot answer when next slot awaits text)

## مرحلة 6: المراجعة والتنظيف
- [x] فحص التغييرات الفعلية (11 modified + 5 new files, +496 -132 lines)
- [x] حذف الكود الميت والمعاد (ad-hoc back/cancel/home buttons removed from phases; ui_events home rows removed; bottom nav is single source)
- [x] مراجعة التأثير على باقي المشروع (73 tests pass; 4 pre-existing failures in batch0 confirmed unrelated via git stash)

## مرحلة 7: الاختبار النهائي
- [x] تشغيل اختبارات البوت الموجودة (batch0/2/3/4/6/needs/wiring: 73 pass, 4 pre-existing fail unrelated)
- [x] اختبارات جديدة للنقاط الخمس  # Phase 3: 12, Phase 4: 9, Phase 5: 17 = 38 new tests all pass

## مرحلة 8: Commit + Push + Verify
- [ ] Commit برسالة واضحة
- [ ] Push إلى فرع جديد
- [ ] التحقق من نجاح Push
- [ ] إنشاء PR
