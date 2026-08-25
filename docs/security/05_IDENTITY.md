# هوية المنصة — Lumen فقط

## مصدر الحقيقة الوحيد

`lumen/identity.py`

أي اسم منتج / برومبت / watermark / مسار بيانات / service id يُقرأ من هنا.

المنتج المعروض للمستخدم والمستودع والكود: **Lumen** فقط.

## المستودع

الاسم: **Lumen_bot**  
المنتج المعروض للمستخدم: **Lumen**

## اختبار

`tests/test_lumen_identity.py`

## Package foundation

All product code lives under the `lumen` namespace:

```
lumen/
  identity.py     # brand only
  engine/         # generation, tools, LLM, hosting
  platform/       # credits, tenants, billing
  bot/            # Telegram consumer interface
  api/            # B2B HTTP API
```

Imports: `from lumen.engine...`, `from lumen.platform...`, `from lumen.bot...`, `from lumen.api...`.

Old top-level package directories must not exist.
