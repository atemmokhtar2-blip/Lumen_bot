# الاستضافة

## الحزم

- `lumen/hosting/` — gateway، orchestration، backup، secrets_env، usage_billing
- `lumen/engine/services/hosting/` و`live_deployment` / `sandbox_runtime` — عزل وتشغيل

## مع اشتراك Pro

عند تفعيل Pro (بعد دفع Stars والتحقق الخادمي):

- استضافة دائمة ضمن مدة الاشتراك
- حدود من `ui_state/pro_plan.py` (انظر `09-pro-subscription.md`): مساحة، RAM مشتركة، CPU، عدد بوتات

## العزل

كل بوت في بيئة معزولة قدر الإمكان حسب مستوى النشر (حاوية / Firecracker عند التفعيل في الإنتاج).

## الحالة

مراقبة وحالة لحظية عبر مكوّنات hosting و`platform_status` عند التهيئة.
