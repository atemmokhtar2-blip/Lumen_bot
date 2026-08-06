"""Verify _slug_cmd produces readable names for the Arabic labels from the screenshot."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from telegram_bot_engine.formal_engine.services.clarification.service import _slug_cmd, _transliterate_ar

cases = [
    "تسجيل",                      # register
    "دعم",                        # support
    "إحصائيات مباشرة",            # stats
    "إدارة الجلسات",              # was cmd_1ae4fb -> sessions
    "استعادة كلمة المرور",        # was cmd_f9b746 -> password_reset
    "إدارة الأجهزة المتصلة",      # was cmd_725109 -> devices
    "لوحة تحكم ويب React أو Next.js",  # react_next_js
    "رسوم بيانية",                # charts
    "إدارة المستخدمين",           # users
    "إدارة مفصلة للمشرفين",       # admin
    "تقارير شهرية",               # reports
    "سجل التدقيق",                # audit_log
    "إشعارات",                    # notifications
    "محفظة",                      # wallet
    "صلاحيات الأدوار",            # permissions
    "تقسيم ملف PDF",              # split_file
    "مراقبة السيرفر",             # server_monitor
    "نسخة احتياطية",              # backup
]

print(f"{'Label':<35} {'Slug'}")
print("-" * 60)
ok = True
for c in cases:
    slug = _slug_cmd(c)
    flag = "" if not slug.startswith("cmd_") else "  <-- STILL HASH"
    if slug.startswith("cmd_"):
        ok = False
    print(f"{c:<35} {slug}{flag}")

print("\nTransliteration samples:")
for c in ["إدارة الجلسات", "استعادة كلمة المرور", "إدارة الأجهزة المتصلة"]:
    print(f"  {c} -> {_transliterate_ar(c)}")

print("\nRESULT:", "PASS - no hash names" if ok else "FAIL - still producing hashes")
sys.exit(0 if ok else 1)
