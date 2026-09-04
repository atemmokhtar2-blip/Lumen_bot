# الأمان

## تنقية المخرجات

`lumen/bot/sanitize.py` — أنماط متعددة: توكن تيليجرام، GitHub PAT، Stripe، مفاتيح LLM، JWT، `KEY=value`، Bearer، …  
يُطبَّق قبل رسائل الخطأ للمستخدم ومسارات التخزين الحساسة.

## الجلسات

- لا تُكتب توكنات البوت نصًا في Redis (`_redact_secrets`)
- أسرار أخرى: محاولة `seal_token` أو الحذف
- hydrate/persist على كل رسالة يقلل فقدان السياق دون توسيع سطح الهجوم على القرص المحلي

## الاشتراك

- التحقق من **المبلغ والعملة والـ payload** قبل المنح
- Mongo مصدر حقيقة؛ Redis كاش
- entitlement fail-closed للحدود الأعلى

## الاستضافة

- إنتاج: Firecracker فقط (لا docker ضعيف افتراضيًا)
- `TBE_HOST_ALLOW_WEAK_BACKEND` محصور في non-production

## البوت المغلق

بدون `ALLOW_ALL_USERS=1` يرفض الغرباء — يقلل حرق أرصدة API.

## LLM

- بدون مفتاح → النموذج خارج التجمع، لا انهيار عام مطلوب
- حقن تعليمات: لا تستخدم tools المدمجة للمزوّد؛ JSON لأدوات Lumen فقط
- `prompt_fence` على نص المستخدم في مسارات multi-agent

## أسرار التطوير

لا تُدرج مفاتيح في Git أو Markdown. استخدم أسرار المنصة / Doppler / env فقط.
