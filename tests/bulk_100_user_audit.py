from __future__ import annotations
import json, os, shutil, sys, time, traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from telegram_bot_engine import generate_bot

CASES = [
    ('clinic', 'عيادة طبية لحجز المواعيد وإلغاء الحجز وعرض مواعيد الطبيب', ['/start','/book','/cancel','/appointments']),
    ('restaurant', 'مطعم توصيل يعرض القائمة ويستقبل طلبات الطعام ويتابع حالة الطلب', ['/start','/menu','/order','/status']),
    ('school', 'مدرسة تدير تسجيل الطلاب والواجبات والحضور وإعلانات المعلمين', ['/start','/register','/homework','/attendance','/announcements']),
    ('gym', 'نادي رياضي لإدارة الاشتراكات وحجز الحصص ومتابعة المدرب', ['/start','/plans','/subscribe','/classes','/coach']),
    ('realestate', 'مكتب عقارات يبحث عن شقق ويضيف عقاراً ويحجز موعد معاينة', ['/start','/search','/add_property','/viewing','/favorites']),
    ('hotel', 'فندق للحجز وتعديل الحجز وعرض الغرف والخدمات وطلب المغادرة', ['/start','/rooms','/book','/modify','/checkout']),
    ('library', 'مكتبة لإعارة الكتب والبحث عنها وتجديد الإعارة وتسجيل الغرامات', ['/start','/search','/borrow','/renew','/fines']),
    ('delivery', 'شركة شحن تنشئ شحنة وتتبعها وتغير العنوان وتصدر إثبات التسليم', ['/start','/create_shipment','/track','/address','/proof']),
    ('lawfirm', 'مكتب محاماة يسجل قضية ويحدد جلسة ويرفع مستنداً ويرسل تحديثاً للعميل', ['/start','/case','/hearing','/document','/update']),
    ('hr', 'نظام موارد بشرية لتقديم إجازة وعرض الرصيد وطلب شهادة راتب', ['/start','/leave','/balance','/salary_certificate']),
    ('banking', 'مساعد بنكي يعرض الرصيد وآخر الحركات ويستقبل طلب دعم آمن', ['/start','/balance','/transactions','/support']),
    ('ecommerce', 'متجر إلكتروني للمنتجات والسلة والدفع وتتبع الشحنات', ['/start','/products','/cart','/checkout','/track']),
    ('marketplace', 'سوق للخدمات يضيف عرضاً ويبحث عن مقدم خدمة ويقيم الطلب', ['/start','/offer','/find','/request','/review']),
    ('travel', 'وكالة سفر تبحث عن رحلات وتنشئ برنامجاً وتحفظ الحجز', ['/start','/flights','/itinerary','/bookings']),
    ('events', 'منصة فعاليات تنشر فعالية وتسجل الحضور وترسل تذكرة QR', ['/start','/events','/register','/ticket']),
    ('ngo', 'جمعية خيرية تستقبل تبرعاً وتسجل متطوعاً وتعرض المشاريع', ['/start','/donate','/volunteer','/projects']),
    ('news', 'قناة أخبار تتيح الأقسام والبحث والاشتراك في التنبيهات', ['/start','/sections','/search','/subscribe']),
    ('podcast', 'منصة بودكاست تعرض الحلقات وتحفظ المفضلة وتستقبل اقتراح موضوع', ['/start','/episodes','/favorite','/suggest']),
    ('course', 'منصة دورات تعرض الدورات وتسجيل الطالب والاختبار والشهادة', ['/start','/courses','/enroll','/quiz','/certificate']),
    ('language', 'مدرس لغة يحدد مستوى الطالب ويرسل درساً ويجري اختباراً', ['/start','/level','/lesson','/test']),
    ('invoice', 'خدمة فواتير تنشئ فاتورة وترسلها وتعرض المدفوعات والتقارير', ['/start','/invoice','/send','/payments','/report']),
    ('accounting', 'مكتب محاسبة يسجل مصروفاً وإيراداً ويصدر تقريراً شهرياً', ['/start','/expense','/income','/monthly_report']),
    ('project', 'فريق عمل يتابع المشاريع والمهام والمواعيد والتعليقات', ['/start','/projects','/task','/due','/comment']),
    ('kanban', 'لوحة كانبان تنشئ بطاقة وتنقلها بين الأعمدة وتعرض المتأخرات', ['/start','/card','/move','/overdue']),
    ('crm', 'نظام مبيعات يسجل عميلاً محتملاً ويتابع الصفقة ويحدد اتصالاً', ['/start','/lead','/deal','/call','/pipeline']),
    ('support', 'مركز دعم يفتح تذكرة ويضيف رداً ويغير الأولوية ويغلقها', ['/start','/ticket','/reply','/priority','/close']),
    ('survey', 'استبيان يجمع إجابات المستخدم ويمنع التكرار ويعرض الملخص', ['/start','/survey','/answer','/summary']),
    ('poll', 'بوت تصويت ينشئ استطلاعاً ويستقبل الأصوات ويعرض النتائج', ['/start','/create_poll','/vote','/results']),
    ('community', 'مجتمع نقاش ينشر موضوعاً ويبلغ عن محتوى ويعرض المشرفين', ['/start','/topic','/report','/moderators']),
    ('dating', 'منصة تعارف تحفظ الملف الشخصي وتعرض اقتراحاً وتدير المطابقة', ['/start','/profile','/discover','/match']),
    ('parenting', 'مساعد أسرة يسجل نشاط الطفل ويرسل تذكيراً ويعرض السجل', ['/start','/child','/reminder','/history']),
    ('pet', 'عيادة حيوانات تسجل حيواناً وتحجز تطعيماً وتعرض الوصفة', ['/start','/pet','/vaccination','/prescription']),
    ('pharmacy', 'صيدلية تعرض الدواء وتستقبل وصفة وتجهز طلب استلام', ['/start','/medicine','/prescription','/pickup']),
    ('fitness', 'مدرب لياقة ينشئ خطة تمرين ويسجل التقدم ويحسب الهدف', ['/start','/plan','/workout','/progress','/goal']),
    ('nutrition', 'خبير تغذية يبني وجبة ويسجل السعرات ويرسل خطة أسبوعية', ['/start','/meal','/calories','/weekly_plan']),
    ('meditation', 'تطبيق تأمل يختار جلسة ويسجل المزاج ويرسل تذكيراً يومياً', ['/start','/session','/mood','/daily_reminder']),
    ('music', 'مدرس موسيقى يحجز درساً ويرسل تمريناً ويتابع مستوى العازف', ['/start','/lesson','/exercise','/level']),
    ('art', 'استوديو فنون يستقبل طلب لوحة ويحدد السعر وموعد التسليم', ['/start','/commission','/quote','/delivery']),
    ('photography', 'مصور يدير جلسات التصوير والاختيارات والفواتير', ['/start','/session','/gallery','/invoice']),
    ('printing', 'مطبعة تستقبل ملفاً وتحدد المقاس وتحسب السعر وتتابع التنفيذ', ['/start','/upload','/size','/quote','/status']),
    ('construction', 'مقاول يتابع مواقع البناء والمواد والعمال والمراحل', ['/start','/sites','/materials','/workers','/milestones']),
    ('maintenance', 'شركة صيانة تستقبل بلاغاً وتعين فنياً وتغلق أمر العمل', ['/start','/request','/technician','/work_order','/close']),
    ('automotive', 'ورشة سيارات تحجز موعد صيانة وتسجل قطع الغيار وترسل الفاتورة', ['/start','/service','/parts','/invoice']),
    ('beauty', 'صالون يحجز خدمة ويختار موظفاً ويرسل تذكيراً بالموعد', ['/start','/services','/staff','/book','/reminder']),
    ('fashion', 'مصمم ملابس يجمع المقاسات ويتابع التصميم وموعد التسليم', ['/start','/measurements','/design','/delivery']),
    ('crafts', 'حرفي يستقبل طلب منتج مخصص ويعرض النماذج وحالة الطلب', ['/start','/custom','/catalog','/status']),
    ('agriculture', 'مزرعة تسجل المحاصيل وتتابع الري وتبيع الإنتاج', ['/start','/crops','/irrigation','/sales']),
    ('farmers', 'سوق مزارعين يربط المنتج بالمشتري ويحدد موعد التسليم', ['/start','/produce','/buy','/delivery']),
    ('weather', 'خدمة طقس تحفظ المدن وترسل توقع اليوم وتنبيهاً للعواصف', ['/start','/city','/forecast','/alert']),
    ('environment', 'مبادرة بيئية تسجل بلاغ تلوث وتعرض الحملات وتحسب المشاركات', ['/start','/pollution','/campaigns','/participate']),
    ('energy', 'شركة طاقة تعرض الاستهلاك والفاتورة وبلاغ انقطاع الخدمة', ['/start','/usage','/bill','/outage']),
    ('internet', 'مزود إنترنت يفحص حالة الاشتراك ويستقبل بلاغ عطل ويحدد زيارة', ['/start','/plan','/diagnose','/ticket','/visit']),
    ('telecom', 'شركة اتصالات تدير الباقات والشحن والدعم الفني', ['/start','/packages','/recharge','/support']),
    ('mobile', 'متجر هواتف يبحث عن جهاز ويقارن الأسعار ويتابع الضمان', ['/start','/devices','/compare','/warranty']),
    ('software', 'شركة برمجيات تستقبل طلب ميزة وتتبع الإصدار وتعرض التوثيق', ['/start','/feature','/release','/docs']),
    ('devops', 'فريق DevOps يعرض الخدمات ويفتح incident ويتابع deploy', ['/start','/services','/incident','/deploy']),
    ('security', 'مركز أمن معلومات يسجل حادثة ويصنفها ويرسل تقريراً', ['/start','/incident','/classify','/report']),
    ('data', 'خدمة بيانات تستقبل طلب تقرير وتعرض مصادر البيانات وجدول التحديث', ['/start','/request','/sources','/refresh']),
    ('ai', 'مساعد ذكاء اصطناعي يستقبل سؤالاً ويحفظ المحادثات ويصنف الطلبات', ['/start','/ask','/history','/classify']),
    ('translation', 'مكتب ترجمة يستقبل نصاً ويحدد اللغة والسعر وموعد التسليم', ['/start','/text','/language','/quote','/delivery']),
    ('design', 'وكالة تصميم تجمع brief وتقدم مراحل ومراجعات العميل', ['/start','/brief','/milestone','/revision']),
    ('marketing', 'وكالة تسويق تنشئ حملة وتحدد الجمهور وتعرض أداء الإعلانات', ['/start','/campaign','/audience','/performance']),
    ('social', 'مدير شبكات اجتماعية يكتب منشوراً ويحدد موعد النشر ويعرض التقويم', ['/start','/post','/schedule','/calendar']),
    ('email', 'خدمة بريد تنشئ قائمة وترسل رسالة وتعرض معدل الفتح', ['/start','/list','/send','/analytics']),
    ('sms', 'خدمة رسائل تنشئ حملة وتختبر النص وتتابع التسليم', ['/start','/campaign','/test','/delivery']),
    ('loyalty', 'نظام ولاء يسجل النقاط ويستبدل مكافأة ويعرض الرصيد', ['/start','/points','/redeem','/balance']),
    ('payments', 'بوابة دفع تنشئ رابط دفع وتتحقق من العملية وتصدر إيصالاً', ['/start','/payment_link','/verify','/receipt']),
    ('subscriptions', 'خدمة اشتراكات تعرض الخطط وتبدأ اشتراكاً وتوقف التجديد', ['/start','/plans','/subscribe','/cancel']),
    ('saas', 'منصة SaaS تدير مساحة عمل وأعضاء وصلاحيات وفاتورة', ['/start','/workspace','/members','/roles','/invoice']),
    ('inventory', 'مخزن يتابع المنتجات والكميات وحركات الإدخال والإخراج', ['/start','/products','/stock','/in','/out']),
    ('procurement', 'قسم مشتريات ينشئ طلب شراء ويقارن عروض الموردين ويعتمد الطلب', ['/start','/purchase','/vendors','/approve']),
    ('vendors', 'بوابة موردين تسجل المورد وتستقبل عرضاً وتتابع التقييم', ['/start','/vendor','/quote','/rating']),
    ('shipping', 'ناقل شحن يدير الطرود والمسارات وإثبات التسليم', ['/start','/parcel','/route','/proof']),
    ('fleet', 'مدير أسطول يتابع المركبات والسائقين والصيانة والرحلات', ['/start','/vehicles','/drivers','/maintenance','/trips']),
    ('parking', 'موقف سيارات يحجز مكاناً ويحسب الرسوم ويعرض السعة', ['/start','/reserve','/fees','/capacity']),
    ('transport', 'خدمة نقل تحجز رحلة وتختار نقطة الالتقاط وتتبع السائق', ['/start','/ride','/pickup','/track']),
    ('tickets', 'منصة تذاكر تبيع تذكرة وتتحقق من رمز الدخول وتعيد الحجز', ['/start','/events','/buy','/checkin','/refund']),
    ('cinema', 'سينما تعرض الأفلام والمواعيد وتحجز المقعد وترسل التذكرة', ['/start','/movies','/showtimes','/seat','/ticket']),
    ('games', 'مجتمع ألعاب ينشئ بطولة ويسجل لاعباً ويعرض الترتيب', ['/start','/tournament','/join','/leaderboard']),
    ('sports', 'نادي رياضي ينظم مباراة ويسجل النتيجة ويعرض الجدول', ['/start','/match','/score','/schedule']),
    ('football', 'فريق كرة قدم يدير اللاعبين والتدريبات والمباريات', ['/start','/players','/training','/matches']),
    ('school_bus', 'خدمة نقل مدرسي تسجل الطالب وتحدد المسار وترسل إشعار الوصول', ['/start','/student','/route','/arrival']),
    ('exam', 'منصة امتحانات تنشئ اختباراً وتجمع الإجابات وتعرض الدرجة', ['/start','/exam','/answer','/grade']),
    ('research', 'مختبر بحثي يسجل تجربة ويدير العينات ويصدر نتيجة', ['/start','/experiment','/sample','/result']),
    ('museum', 'متحف يحجز زيارة ويعرض المعروضات وينظم جولة مرشدة', ['/start','/visit','/exhibits','/tour']),
    ('library2', 'أرشيف رقمي يبحث عن وثيقة ويطلب نسخة ويتابع الطلب', ['/start','/document','/copy','/request']),
    ('government', 'خدمة حكومية تستقبل طلب معاملة وتعرض حالتها وترسل موعداً', ['/start','/application','/status','/appointment']),
    ('visa', 'مكتب تأشيرات يجمع بيانات الطلب ويحدد موعداً ويتابع الحالة', ['/start','/application','/appointment','/status']),
    ('passport', 'خدمة جوازات تحجز موعداً وتتحقق من المستندات وتعرض الجاهزية', ['/start','/appointment','/documents','/ready']),
    ('insurance', 'شركة تأمين تسجل مطالبة وتطلب مستنداً وتعرض قرار التعويض', ['/start','/claim','/documents','/decision']),
    ('claims', 'مركز مطالبات يستقبل بلاغاً ويعين مراجعاً ويعرض المرحلة الحالية', ['/start','/claim','/reviewer','/stage']),
    ('emergency', 'مركز طوارئ يسجل البلاغ ويرسل الموقع ويتابع فرق الاستجابة', ['/start','/report','/location','/response']),
    ('helpdesk', 'مكتب مساعدة داخلي يبحث في قاعدة المعرفة ويفتح تذكرة', ['/start','/knowledge','/ticket','/escalate']),
    ('onboarding', 'نظام تهيئة موظف جديد يجمع المستندات ويعرض المهام الأولى', ['/start','/profile','/documents','/checklist']),
    ('recruiting', 'توظيف يستقبل سيرة ذاتية ويفرز المرشحين ويحدد مقابلة', ['/start','/cv','/screen','/interview']),
    ('freelance', 'منصة مستقلين تنشر مشروعاً وتستقبل عروضاً وتدير التسليم', ['/start','/project','/proposal','/delivery']),
    ('consulting', 'استشارات تحجز جلسة وتجمع المتطلبات وترسل ملخصاً', ['/start','/session','/requirements','/summary']),
    ('translation2', 'مترجم مستقل يدير الأعمال والعملاء والفواتير والمواعيد', ['/start','/jobs','/clients','/invoices','/calendar']),
    ('account', 'مدير شخصي يتابع المهام والمواعيد والمصروفات والملاحظات', ['/start','/tasks','/calendar','/expenses','/notes']),
    ('household', 'إدارة منزل تقسم الأعمال وقائمة التسوق والمواعيد العائلية', ['/start','/chores','/shopping','/family_calendar']),
    ('travel2', 'مسافر يحفظ الرحلات والمطاعم والأماكن ويستقبل تذكير المغادرة', ['/start','/trip','/places','/restaurants','/reminder']),
    ('recipe', 'مساعد وصفات يبحث بالمكونات ويحفظ المفضلة وينشئ قائمة شراء', ['/start','/recipe','/favorite','/shopping_list']),
    ('books', 'نادي قراءة يضيف كتاباً وينشئ جلسة نقاش ويسجل الأعضاء', ['/start','/book','/session','/members']),
    ('volunteer', 'منصة تطوع تعرض الفرص وتسجل المتطوع وتؤكد ساعات الخدمة', ['/start','/opportunities','/join','/hours']),
    ('donation', 'منصة تبرعات تنشئ حملة وتستقبل التبرع وتعرض التقدم', ['/start','/campaign','/donate','/progress']),
    ('fundraising', 'حملة تمويل جماعي تسجل داعماً وتعرض الهدف وترسل تحديثاً', ['/start','/back','/goal','/update']),
    ('analytics', 'لوحة مؤشرات تجمع بيانات المبيعات وتعرض ملخصاً وتنبيهاً للشذوذ', ['/start','/dashboard','/summary','/alerts']),
    ('generic', 'بوت خدمات عام يتيح التسجيل والإضافة والقائمة والحذف والبحث والتقارير', ['/start','/register','/add','/list','/delete','/search','/report']),
]
CASES = CASES[:100]
assert len(CASES) == 100, len(CASES)

def main():
    root = Path('/tmp/bulk_100_user_audit')
    if root.exists(): shutil.rmtree(root)
    root.mkdir(parents=True)
    def run_case(item):
        idx, (name, desc, commands) = item
        request = f"اعمل بوت تليجرام باسم {name.title()}Hub. {desc}. يجب أن تكون الأوامر التالية واضحة وقابلة للتشغيل: " + ', '.join(commands) + ". يجب أن يرد على أي رسالة عادية برد واضح وألا يتوقف عند خطوة متعددة الرسائل."
        out = root / f"bot_{idx:03d}_{name}"
        t = time.time()
        row = {'index': idx, 'name': name, 'request': request, 'commands': commands}
        try:
            result = generate_bot(request, work_dir=out, user_id=900000 + idx)
            meta = getattr(result, 'metadata', {}) or {}
            row.update({'elapsed_s': round(time.time()-t, 3), 'result_type': type(result).__name__,
                        'success': bool(getattr(result, 'success', False)),
                        'ready_for_token': meta.get('ready_for_token'),
                        'syntax_ok': meta.get('syntax_ok'),
                        'verified_commands': meta.get('verified_commands', []),
                        'errors': meta.get('errors', []),
                        'files': sum(1 for p in out.rglob('*') if p.is_file())})
        except Exception as exc:
            row.update({'elapsed_s': round(time.time()-t, 3), 'success': False,
                        'exception': repr(exc), 'traceback': traceback.format_exc(limit=8)})
        return row

    rows = []
    workers = max(1, min(8, int(os.getenv('BULK_WORKERS', '8'))))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(run_case, item) for item in enumerate(CASES, 1)]
        for future in as_completed(futures):
            row = future.result()
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
    rows.sort(key=lambda r: r['index'])
    (root/'results.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    summary={'total':len(rows),'success':sum(bool(r.get('success')) for r in rows),'ready':sum(bool(r.get('ready_for_token')) for r in rows),'syntax_ok':sum(bool(r.get('syntax_ok')) for r in rows),'exceptions':sum('exception' in r for r in rows),'missing_verified':sum(len(r.get('verified_commands',[]))<len(r['commands'])-1 for r in rows)}
    (root/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print('SUMMARY',json.dumps(summary,ensure_ascii=False))
    return 0 if summary['exceptions']==0 else 2
if __name__=='__main__': raise SystemExit(main())
