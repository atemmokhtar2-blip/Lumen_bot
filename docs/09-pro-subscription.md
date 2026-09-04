# اشتراك Lumen Pro

## التعريف في الكود

`lumen/engine/services/ui_state/pro_plan.py` — **مصدر الأرقام**:

| الثابت | القيمة |
|--------|--------|
| `PRO_PLAN_ID` | `lumen_pro` |
| `PRO_PLAN_PRICE_USD` | **10** |
| `PRO_PLAN_PRICE_STARS` | **800** (XTR) |
| `PRO_PLAN_DURATION_MONTHS` | 1 |
| `PRO_PLAN_BOT_LIMIT` | **10** |
| `PRO_PLAN_DISK_MB` | **3072** (3 GB) |
| `PRO_PLAN_MEMORY_MB` | **2048** (2 GB مشتركة) |
| `PRO_PLAN_CPU` | **0.25** |
| `PRO_PLAN_INVOICE_PAYLOAD` | `lumen_pro_monthly_v2` |

يشمل: استضافة دائمة مجانية طوال الاشتراك، عزل، مراقبة، رصيد credits حسب السياسة المعروضة في الواجهة.

## مسار الدفع (`payment_handlers.py`)

1. `handle_pre_checkout` — رفض مبكر إن لزم
2. `handle_successful_payment`:
   - يتحقق: `payload == PRO_PLAN_INVOICE_PAYLOAD` و`currency == XTR` و`amount == 800`
   - يبني سجل: `plan_id`, `started_at`, `expires_at` (+30 يوم), `stars_paid`, `charge_id`
   - يكتب `user_data["pro_plan"]`
   - **`write_subscription`** → Mongo دائم + Redis كاش

أي عدم تطابق في المبلغ/العملة/الـ payload → لا تفعيل (log warning).

## الاستحقاق (`pro_plan_entitlement.py`)

- يقرأ عبر `read_subscription` (Redis ثم Mongo)
- يرفض إن انتهت `expires_at` أو `stars_paid < 800`
- fail-closed لزيادة الحدود إن تعذّر المصدر
- لا يثق بـ user_data وحدها كمصدر وحيد للحدود

## الجلسة

`pro_plan` ضمن `_DURABLE_KEYS`؛ TTL Redis للجلسة يمتد لـ 45 يومًا عند وجود اشتراك لتقليل سقوط الكاش قبل انتهاء الشهر + هامش.
