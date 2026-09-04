# طبقة تيليجرام

## نقطة الدخول

`lumen/bot/routers/message_router.py` → `handle_message`.

### البوابات المبكرة (`message_stages/early_gates.py`)

- **auth + rate:** allowlist / `ALLOW_ALL_USERS`، حد معدّل الطلبات
- **groups:** في المجموعات يُطلب منشن أو رد على البوت
- **cancel / token:** مسارات مبكرة للإلغاء ولصق توكن بوت

### بعد البوابات

1. **hydrate** من Redis (`session_store`)
2. **busy guard** عبر `progress_tracker.is_generation_busy`:
   - أثناء التوليد: رسالة تشرح التحديثات الحية
   - `/cancel` أو «إلغاء» → `generation_cancel.request_cancel(user_id)`
3. `_handle_message_body`: Engine UI slots، أوامر، routers فرعية، توليد
4. **persist** في `finally` عبر `persist_ui_session`

## الموجّهات الفرعية

| ملف | مسؤولية |
|-----|---------|
| `message_generation.py` | تشغيل التوليد، HITL plan approve |
| `message_intent.py` | هل الرسالة طلب توليد / تأكيد |
| `git_router.py` | استنساخ/دفع git |
| `hosting_router.py` | لوحات الاستضافة |
| `repo_dev_router.py` | تطوير على مستودع مربوط |

## UI

| ملف | مسؤولية |
|-----|---------|
| `ui/callback_router.py` | أزرار inline موقّعة |
| `ui/keyboards.py` | بناء لوحات المفاتيح |
| `ui/payment_handlers.py` | pre-checkout + successful_payment لـ Pro |
| `ui/pro_plan_entitlement.py` | هل المستخدم Pro فعّال؟ |
| `ui/subscription_store.py` | قراءة/كتابة الاشتراك Mongo+Redis |
| `ui/input_prompt.py` | مطالبات إدخال (placeholders / ForceReply حيث يُستخدم) |
| `ui/state_store.py` | تحميل/حفظ `engine_ui` في user_data + persist |

## Markdown Hell — الحل في الكود

`lumen/bot/telegram_text.py`:

1. نص الوكيل الاعتباطي يُرسل **plain text** (بدون `parse_mode`) عند الشك
2. تنسيق الواجهة: **MarkdownV2** أو HTML مع `escape_markdown_v2` / `escape_html`
3. **لا** يُستخدم `ParseMode.MARKDOWN` القديم (ينكسر على `_` `*` `[`)
4. الرسائل أطول من **4096** تُقسَّم على حدود فقرات/أسطر

`sanitize.py` ينقّي الأسرار قبل عرض الأخطاء أو التخزين.

## التقدم الحي (Dead Wait)

- المحرك يدفع أحداثًا إلى `progress_bus`
- `progress_tracker` يربطها برسالة حالة تُحدَّث (تعديل نص) ليعرض الأداة/المزوّد/الخطوة
- المستخدم يرى شغلًا حقيقيًا بدل «جاري الكتابة» الصامت

## الإلغاء

- `generation_cancel.request_cancel(user_id)` يضع علامة
- الحلقة والعامل يقرآن `is_cancelled` ولا يمسحان طلب المستخدم عند بدء الحلقة بشكل خاطئ

## التنقّل

أزرار الحالة تُبنى من `ui_state.controller.buttons_for_state` + `keyboards.build_inline_keyboard`. مسارات عميقة (GEN_SLOTS → GEN_CONFIRM → توليد) تعتمد على `EngineUiPhase` المحفوظ في الجلسة الدائمة حتى لا يضيع المستخدم بعد restart.
