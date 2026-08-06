"""
Test 3: Full generation with the clarification-merged text to see
the actual generated handlers and confirm commands don't work.
"""
import sys
import os
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from telegram_bot_engine.formal_engine.services.clarification.service import merge_answers
from telegram_bot_engine.formal_engine.pipeline_formal import build_from_text

# Simulate the full clarification flow
original = "اعمل بوت تيليجرام باسم PDFX-AI"
answer = """تسجيل واشتراك حسابات
دعم المصادقة الثنائية
إدارة الجلسات
استعادة كلمة المرور
إدارة الأجهزة المتصلة
إحصائيات مباشرة
رسوم بيانية
إدارة المستخدمين
إدارة مفصلة للمشرفين
لوحة تحكم ويب React أو Next.js"""

merged = merge_answers(original, answer, prior_extra="", step="commands")

# Generate the bot
out_dir = Path(tempfile.mkdtemp(prefix="test_pdfx_")) / "generated_bot"
out_dir.mkdir(parents=True, exist_ok=True)

build = build_from_text(merged, out_dir, grounding_text=merged)
print(f"Files: {len(build.files)}")
print(f"Commands: {[c.name for c in build.inference.commands]}")
print(f"Wizards: {[w['id'] for w in build.inference.wizards]}")
print()

# Show the generated handlers for the cmd_{hash} commands
handlers = (out_dir / "app" / "handlers.py").read_text()
print("=" * 70)
print("GENERATED handlers.py (showing cmd_{hash} handlers)")
print("=" * 70)
# Find and show the cmd_ handlers
for line_num, line in enumerate(handlers.split('\n'), 1):
    if 'cmd_' in line and 'handler' in line.lower():
        # print this handler and the next 15 lines
        lines = handlers.split('\n')
        start = line_num - 1
        print(f"\n--- Line {line_num} ---")
        for l in lines[start:start+20]:
            print(l)
        print("---")
        break

# Show the main.py command registrations
main_py = (out_dir / "main.py").read_text()
print()
print("=" * 70)
print("GENERATED main.py (command registrations)")
print("=" * 70)
for line in main_py.split('\n'):
    if 'CommandHandler' in line or 'BotCommand' in line:
        print(line)

print()
print("=" * 70)
print("ANALYSIS: What happens when user sends /cmd_414424?")
print("=" * 70)
# Show the handler for a cmd_ command
import re
# Find cmd_414424_handler
match = re.search(r'async def cmd_414424_handler.*?(?=\nasync def |\nclass |\Z)', handlers, re.DOTALL)
if match:
    print("cmd_414424_handler:")
    print(match.group()[:500])
else:
    print("cmd_414424_handler NOT FOUND - searching for any cmd_ handler...")
    for m in re.finditer(r'async def (cmd_\w+)_handler', handlers):
        print(f"  Found: {m.group(1)}")
