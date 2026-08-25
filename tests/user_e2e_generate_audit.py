from pathlib import Path
import json
import tempfile
from lumen.engine import generate_bot

SPEC = """
اعمل بوت تليجرام باسم SmokeOps لإدارة مهام وعملاء.
الأوامر:
/start - ترحيب وعرض القائمة
/help - مساعدة
/register - تسجيل مستخدم يجمع الاسم والبريد والهاتف
/new_task - إنشاء مهمة يجمع العنوان والوصف والأولوية
/my_tasks - عرض مهامي
/all_tasks - عرض كل المهام
/complete_task - إكمال مهمة
/new_client - إضافة عميل
/my_clients - عرض العملاء
/stats - إحصائيات
"""

def main():
    out = Path("/tmp/user_e2e_generated")
    out.mkdir(parents=True, exist_ok=True)
    result = generate_bot(SPEC, work_dir=out, user_id=424242)
    print("RESULT_TYPE", type(result).__name__)
    print("RESULT", repr(result))
    print("OUT", out)
    for p in sorted(out.rglob("*")):
        if p.is_file():
            print("FILE", p.relative_to(out), p.stat().st_size)
    meta = getattr(result, "metadata", None)
    if meta is not None:
        print("META", json.dumps(meta, ensure_ascii=False, default=str, indent=2))

if __name__ == "__main__":
    main()
