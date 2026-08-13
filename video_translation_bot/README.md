# Local Telegram Video Translation Bot

هذا المكوّن يضيف خط معالجة مستقلًا إلى المستودع القائم، ويقسم المنتج إلى طبقات واضحة: طبقة Telegram للاستقبال والتسليم، إدارة Jobs وWorker، طبقة Media/Audio، محرك Speech محلي، حزمة Transcript، محرك Translation محلي، Subtitle Timeline، ثم محرك تصميم ورندر محلي باستخدام FFmpeg.

## سياسة الذكاء الاصطناعي

لا يحتوي هذا المكوّن على أي استدعاء لخدمة AI سحابية أو API Key. محرك الكلام الاختياري يستخدم `faster-whisper` محليًا، ومحرك الترجمة الاختياري يستخدم `Argos Translate` مع حزم اللغات المثبتة محليًا. إذا لم يوجد نموذج محلي، يفشل النظام بوضوح بدل اختلاق ترجمة أو الاتصال بخدمة خارجية.

## التشغيل

ثبّت `ffmpeg` و`ffprobe` على النظام، ثم ثبّت الاعتماديات الأساسية من `requirements-video-translation.txt`. لتفعيل التفريغ، ثبّت `faster-whisper` وجهّز نموذجًا محليًا. لتفعيل الترجمة، ثبّت `argostranslate` وحزمة اللغة المطلوبة محليًا. بعد ذلك اضبط `TELEGRAM_BOT_TOKEN`؛ هذا التوكن خاص بواجهة Telegram وليس خدمة AI، وهو مطلوب فقط لتشغيل البوت.

```bash
pip install -r requirements-video-translation.txt
export TELEGRAM_BOT_TOKEN='ضع_توكن_بوت_تلجرام_هنا'
export LOCAL_SPEECH_BACKEND='faster-whisper'
export LOCAL_SPEECH_MODEL='small'
export LOCAL_TRANSLATION_BACKEND='argos'
PYTHONPATH=. python -m video_translation_bot.main
```

يمكن تغيير `VIDEO_BOT_DATA_DIR`، و`VIDEO_BOT_MAX_FILE_SIZE_MB`، و`VIDEO_BOT_KEEP_INTERMEDIATES`، وخصائص نموذج الكلام من خلال متغيرات البيئة. الملفات المؤقتة معزولة داخل مجلد لكل `job_id`، ولا يضع محرك الرندر منطق Telegram أو الترجمة داخله.

## العقود

ينتج Specification 1 كائن `TranscriptPackage`، ويستقبل Specification 2 هذا الكائن لإنتاج `TranslationPackage` و`SubtitlePackage`. يستقبل Specification 3 الفيديو الأصلي و`SubtitlePackage` و`RenderConfiguration`، ثم ينتج `FinalVideoPackage`. جميع النماذج معرفة في `models.py` ومصممة لتقبل حقولًا إضافية مستقبلًا.

## حدود النسخة الحالية

المسار التنفيذي والواجهات الأساسية جاهزة وقابلة للتوسع، لكن جودة التفريغ والترجمة تعتمد على تثبيت النماذج المحلية المناسبة. التعرّف الدقيق على هوية المتحدثين يحتاج إضافة نموذج diarization محلي مثل `pyannote.audio` بأوزان محلية؛ لم يتم جعل هذا الاعتماد إجباريًا حتى يعمل النظام على CPU بدون تنزيل خدمة مغلقة. وبالمثل، تجنب النظام أي fallback يوهم المستخدم بوجود ترجمة حقيقية عند غياب نموذج محلي.
