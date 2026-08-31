# Lumen Bot — رفع الواجهة لمستوى احترافي منافس عالمياً

## المرحلة 1: إعادة كتابة render.py — نصوص احترافية
- [x] HOME: ترحيب احترافي + وصف ما تسويه Lumen + الأزرار (لا سطر واحد جاف)
- [x] GEN_TYPE: شرح واضح + أمثلة + placeholder (لا "اكتب وصف البوت.")
- [x] GEN_SLOTS: سؤال واضح + تقدّم + تلميح (لا "المحرك يتطلب توضيحات")
- [x] GEN_CONFIRM: ملخص بصري + تأكيد (لا "تأكيد التوليد" + desc فقط)
- [x] GENERATING: مراحل + تقدير زمني + reassure (لا "جار التوليد عبر المحرك…")
- [x] GEN_DONE: احتفال + ملخص + خيارات واضحة (لا "اكتمل التوليد." + مسار تقني)
- [x] DASHBOARD: لوحة بصرية + حالة بوتات باللغة المستخدم (لا HostService/instance)
- [x] BILLING: رصيد + تكلفة + كيف تُشحن + خطة (لا "رصيدك: 0 كريديت" فقط)
- [x] HELP: دليل شامل منظم (لا 4 bullet points)
- [x] CONTEXT/events: رسائل خطأ واضحة + حلول (لا "تنبيه: فشل التوليد" فقط)
- [x] اختبار: كل نص جديد يظهر صحيح + يحتوي على المعلومات الأساسية
- [x] التحقق: اختبارات render موجودة تعدّلت + تتجاوز
- [x] اختبارات جديدة: test_pro_ux_render.py — 38 test تتحقق من كل شاشة

## المرحلة 2: Validation للإدخال
- [x] bot_token: validation (format: digits:alphanum35)
- [x] bot_name: validation (no spaces, length 3-64, starts with letter)
- [x] github_token: validation (ghp_ or github_pat_)
- [x] webhook_url: validation (https URL only)
- [x] رسائل خطأ validation واضحة بالعربية
- [x] اختبار: validation ترفض وتقبل صح (43 test)
- [x] تكامل: message_router يستخدم validate_slot قبل تخزين القيمة

## المرحلة 3: Onboarding flow
- [x] أول /start: شرح + أمثلة بوتات جاهزة + دعوة للتجربة
- [x] العودة: القائمة الرئيسية المختصرة
- [x] اختبار: onboarding يظهر مرة واحدة فقط

## المرحلة 4: مراجعة وتكامل
- [x] فحص: لا مصطلحات تقنية مكشوفة (HostService, instance, plane, intent_kind, slots)
- [x] فحص: كل النصوص MarkdownV2-safe (إيموجي + تنسيق)
- [x] فحص: chat_hygiene تعمل مع الرسائل الجديدة + event sanitization
- [x] اختبارات شاملة (جديدة + موجودة)

## المرحلة 5: Commit + Push + PR
- [x] Commit رسالة واضحة (المرحلة 1)
- [x] Push إلى فرع (المرحلة 1)
- [x] تحديث PR أو إنشاء PR جديد (المرحلة 1)
- [x] Commit + Push (المرحلة 2)
- [x] Commit + Push (المرحلة 3)
- [x] Commit + Push (المرحلة 4)
- [x] PR نهائي
