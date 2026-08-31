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
- [ ] bot_token: validation (format: digits:alphanum35)
- [ ] bot_name: validation (no spaces, length 3-64)
- [ ] github_token: validation (ghp_ or github_pat_)
- [ ] webhook_url: validation (https URL)
- [ ] رسائل خطأ validation واضحة بالعربية
- [ ] اختبار: validation ترفض وتقبل صح

## المرحلة 3: Onboarding flow
- [ ] أول /start: شرح + أمثلة بوتات جاهزة + دعوة للتجربة
- [ ] العودة: القائمة الرئيسية المختصرة
- [ ] اختبار: onboarding يظهر مرة واحدة فقط

## المرحلة 4: مراجعة وتكامل
- [ ] فحص: لا مصطلحات تقنية مكشوفة (HostService, instance, plane, intent_kind, slots)
- [ ] فحص: كل النصوص MarkdownV2-safe (إيموجي + تنسيق)
- [ ] فحص: chat_hygiene تعمل مع الرسائل الجديدة
- [ ] اختبارات شاملة (جديدة + موجودة)

## المرحلة 5: Commit + Push + PR
- [x] Commit رسالة واضحة (المرحلة 1)
- [x] Push إلى فرع (المرحلة 1)
- [ ] تحديث PR أو إنشاء PR جديد (المرحلة 1)
- [ ] Commit + Push (المرحلة 2)
- [ ] Commit + Push (المرحلة 3)
- [ ] Commit + Push (المرحلة 4)
- [ ] PR نهائي
