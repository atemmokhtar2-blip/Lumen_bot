# هوية المنصة — Lumen فقط

## مصدر الحقيقة الوحيد

`lumen/identity.py`

أي اسم منتج / برومبت / watermark / مسار بيانات / service id يُقرأ من هنا.

## ممنوع

Maestro، ميسترو، Maya، capability_maestro، AI Agent 7h، ai_agent_7h

## المستودع

الاسم: **Lumen_bot**  
المنتج المعروض للمستخدم: **Lumen**

## اختبار

`tests/test_lumen_identity.py`

## Package foundation (radical)

All product code lives under the `lumen` namespace:

```
lumen/
  identity.py     # brand only
  engine/         # was telegram_bot_engine
  platform/       # was b2b_platform
  bot/            # was bot_interface
  api/            # was api/
```

Imports: `from lumen.engine...`, `from lumen.platform...`, `from lumen.bot...`, `from lumen.api...`.

Old top-level package directories must not exist.
