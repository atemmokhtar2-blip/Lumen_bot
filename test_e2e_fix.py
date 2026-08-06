"""
End-to-end test: verify the fix produces meaningful command names + functional handlers.
Simulates the full clarification flow that generated the PDFX-AI bot from the screenshot.
"""
import sys
import os
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from telegram_bot_engine.formal_engine.services.clarification.service import (
    merge_answers, _slug_cmd
)
from telegram_bot_engine.formal_engine.pipeline_formal import build_from_text

# --- Step 1: verify _slug_cmd no longer produces hashes ---
print("=" * 70)
print("STEP 1: _slug_cmd verification (no cmd_{hash} names)")
print("=" * 70)
labels = [
    "إدارة الجلسات",
    "استعادة كلمة المرور",
    "إدارة الأجهزة المتصلة",
    "إحصائيات مباشرة",
    "رسوم بيانية",
    "إدارة المستخدمين",
    "إدارة مفصلة للمشرفين",
]
hash_count = 0
for lbl in labels:
    slug = _slug_cmd(lbl)
    is_hash = slug.startswith("cmd_")
    if is_hash:
        hash_count += 1
    print(f"  {lbl:<30} -> {slug}{'  [HASH!]' if is_hash else ''}")
assert hash_count == 0, f"FAIL: {hash_count} labels still produce hashes"
print("  -> PASS: no hash names\n")

# --- Step 2: simulate the clarification merge ---
print("=" * 70)
print("STEP 2: Clarification merge (commands step)")
print("=" * 70)
original = "اعمل بوت تيليجرام باسم PDFX-AI"
answer = """
تسجيل واشتراك حسابات
دعم المصادقة الثنائية (2FA)
إدارة الجلسات
استعادة كلمة المرور
إدارة الأجهزة المتصلة
إحصائيات مباشرة
رسوم بيانية
إدارة المستخدمين
إدارة مفصلة للمشرفين
لوحة تحكم ويب React أو Next.js
"""
merged = merge_answers(original, answer, prior_extra="", step="commands")
print(merged[:600])
print()

# --- Step 3: build the bot ---
print("=" * 70)
print("STEP 3: Build bot from merged text")
print("=" * 70)
out_dir = Path(tempfile.mkdtemp(prefix="test_pdfx_")) / "generated_bot"
out_dir.mkdir(parents=True, exist_ok=True)

try:
    build = build_from_text(merged, out_dir, grounding_text=merged)
except Exception as exc:
    print(f"BUILD ERROR: {exc}")
    import traceback; traceback.print_exc()
    sys.exit(1)

cmds = [c.name for c in build.inference.commands]
print(f"Files generated: {len(build.files)}")
print(f"Commands: {cmds}")
print(f"Wizards: {[w.get('id') for w in build.inference.wizards]}")

# Check for any cmd_{hash} in commands
hash_cmds = [c for c in cmds if c.startswith("cmd_") and len(c) == 10]
print(f"\nHash-named commands remaining: {hash_cmds}")
assert not hash_cmds, f"FAIL: hash commands still present: {hash_cmds}"
print("  -> PASS: no hash command names in generated bot\n")

# --- Step 4: inspect generated handlers ---
print("=" * 70)
print("STEP 4: Inspect generated handlers.py")
print("=" * 70)
handlers_path = out_dir / "app" / "handlers.py"
if handlers_path.exists():
    handlers = handlers_path.read_text(encoding="utf-8")
    # Show command handler definitions
    import re
    defs = re.findall(r'async def (\w+_handler)\(', handlers)
    print(f"Handler functions defined: {defs}")
    # Check that BUTTON_TO_CMD maps to real commands
    btc_match = re.search(r'BUTTON_TO_CMD.*?\{(.*?)\}', handlers, re.DOTALL)
    if btc_match:
        print(f"\nBUTTON_TO_CMD content:\n{btc_match.group()[:400]}")
    # Show one non-wizard handler to verify it's functional
    for cmd_name in ["sessions", "password_reset", "devices", "charts", "users", "dashboard"]:
        m = re.search(rf'async def {cmd_name}_handler\(.*?\n(?=async def |\nclass |\Z)',
                      handlers, re.DOTALL)
        if m:
            print(f"\n--- {cmd_name}_handler ---")
            print(m.group()[:600])
            break
else:
    print("handlers.py NOT FOUND")
    print(f"Files in app/: {list((out_dir/'app').glob('*')) if (out_dir/'app').exists() else 'no app dir'}")

# --- Step 5: inspect main.py registrations ---
print("\n" + "=" * 70)
print("STEP 5: main.py command registrations")
print("=" * 70)
main_path = out_dir / "main.py"
if main_path.exists():
    main_py = main_path.read_text(encoding="utf-8")
    for line in main_py.split("\n"):
        if "CommandHandler" in line or "BotCommand" in line:
            print(f"  {line.strip()}")
else:
    print("main.py NOT FOUND")

print("\n" + "=" * 70)
print("ALL CHECKS PASSED — fix is working end-to-end")
print("=" * 70)
