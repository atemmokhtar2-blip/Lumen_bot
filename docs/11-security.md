# الأمان

## أسرار في السجلات والأخطاء

`lumen/bot/sanitize.py` ينقّي:

- توكنات تيليجرام، GitHub PAT، Stripe، مفاتيح LLM، JWT، أنماط `API_KEY=`، Bearer، …

يُستخدم قبل رسائل المستخدم وتخزين الوظائف حيث ينطبق.

## البوت المغلق افتراضيًا

`ALLOW_ALL_USERS` غير مفعّل → رفض الغرباء يقلل استنزاف أرصدة API.

## الجلسات

- Redis مصدر حقيقة للسياق العابر للـ workers
- Pro: خادمي فقط (Redis/Mongo + تحقق Stars)

## الاستضافة

عزل لكل بوت؛ أسرار الاستضافة عبر `hosting/secrets_env` عند الاستخدام.

## التبعيات

راجع `requirements.txt` / `requirements-security.txt` و Dependabot على GitHub عند النشر.

## أسرار Git

لا تضع توكنات في التوثيق أو الكود. استخدم متغيرات البيئة / Doppler / أسرار المنصة فقط.
