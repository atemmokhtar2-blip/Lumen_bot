"""
Test: run the full generation pipeline with a sample Arabic request
to see exactly what commands are generated and whether they work.
"""
import sys
import os
import json
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Sample request similar to what the user sent (PDFX-AI bot)
SAMPLE_REQUEST = """
اعمل بوت تيليجرام باسم PDFX-AI
البوت يقدم خدمة آلاف المستخدمين في نفس الوقت
يجب أن تحتوي المنصة على نظام تسجيل واشتراك حسابات
مع دعم المصادقة الثنائية 2FA
إدارة الجلسات
استعادة كلمة المرور
إدارة الأجهزة المتصلة
لوحة تحكم ويب React أو Next.js
إدارة مفصلة للمشرفين
إحصائيات مباشرة
رسوم بيانية
إدارة المستخدمين
"""

print("=" * 70)
print("TEST: Full Bot Generation Pipeline")
print("=" * 70)
print(f"Input: {SAMPLE_REQUEST[:200]}")
print()

# Step 1: Test SpecTranslator
print("--- Step 1: SpecTranslator (AI translator) ---")
try:
    from telegram_bot_engine.chat_ai.spec_translator import prepare_formal_text
    formal_text, tr = prepare_formal_text(SAMPLE_REQUEST)
    print(f"Translator OK: {tr.ok}")
    print(f"Model used: {tr.model_used}")
    print(f"Error: {tr.error}")
    print(f"Grounded commands: {len((tr.grounded_json or {}).get('commands') or [])}")
    print(f"Dropped: {json.dumps(tr.dropped, ensure_ascii=False, indent=2)}")
    print()
    print("=== STRUCTURED TEXT (fed to formal engine) ===")
    print(formal_text[:2000])
    print()
    print("=== GROUNDED JSON ===")
    print(json.dumps(tr.grounded_json, ensure_ascii=False, indent=2)[:2000])
except Exception as e:
    print(f"Translator FAILED: {e}")
    traceback.print_exc()
    formal_text = SAMPLE_REQUEST

print()
print("--- Step 2: DSL Extraction ---")
try:
    from telegram_bot_engine.formal_engine.dsl.extractor import extract_dsl
    prog = extract_dsl(formal_text)
    print(f"Commands extracted: {[c.name for c in prog.commands]}")
    print(f"Entities: {[e.name for e in prog.entities]}")
    print(f"Buttons: {[b.label for b in prog.buttons]}")
    print(f"Operations: {[op.name for op in prog.operations]}")
except Exception as e:
    print(f"DSL extraction FAILED: {e}")
    traceback.print_exc()

print()
print("--- Step 3: Grounding Gate ---")
try:
    from telegram_bot_engine.formal_engine.dsl.extractor import extract_dsl
    from telegram_bot_engine.formal_engine.verification.grounding_gate import apply_grounding_gate
    prog = extract_dsl(formal_text)
    cleaned, report = apply_grounding_gate(prog, SAMPLE_REQUEST)
    print(f"Commands after grounding: {[c.name for c in cleaned.commands]}")
    print(f"Removed commands: {report.removed_commands}")
    print(f"Removed buttons: {report.removed_buttons}")
    print(f"Warnings: {report.warnings}")
except Exception as e:
    print(f"Grounding FAILED: {e}")
    traceback.print_exc()

print()
print("--- Step 4: Full build_from_text ---")
try:
    import tempfile
    from pathlib import Path
    from telegram_bot_engine.formal_engine.pipeline_formal import build_from_text
    out_dir = Path(tempfile.mkdtemp(prefix="test_bot_")) / "generated_bot"
    out_dir.mkdir(parents=True, exist_ok=True)
    build = build_from_text(formal_text, out_dir, grounding_text=SAMPLE_REQUEST)
    print(f"Files created: {build.files}")
    print(f"Grounding report: {json.dumps(build.grounding.to_dict(), ensure_ascii=False, indent=2)}")
    print(f"Verification OK: {build.verification.ok if build.verification else 'N/A'}")
    if build.inference:
        print(f"Inferred commands: {[c.name for c in build.inference.commands]}")
        print(f"Inferred wizards: {[w['id'] for w in build.inference.wizards]}")
except Exception as e:
    print(f"build_from_text FAILED: {e}")
    traceback.print_exc()

print()
print("--- Step 5: Check generated handlers.py ---")
try:
    handlers_path = out_dir / "app" / "handlers.py"
    if handlers_path.exists():
        print(f"handlers.py exists at {handlers_path}")
        content = handlers_path.read_text()
        print(content[:3000])
    else:
        # Maybe different structure
        for p in out_dir.rglob("*.py"):
            print(f"  Generated file: {p}")
        # Try to find handlers
        for p in out_dir.rglob("handlers.py"):
            print(f"\n=== {p} ===")
            print(p.read_text()[:3000])
except Exception as e:
    print(f"Read handlers FAILED: {e}")
    traceback.print_exc()

print()
print("--- Step 6: Check generated main.py ---")
try:
    for p in out_dir.rglob("main.py"):
        print(f"\n=== {p} ===")
        print(p.read_text()[:3000])
except Exception as e:
    print(f"Read main FAILED: {e}")

print()
print("=" * 70)
print("TEST COMPLETE")
print("=" * 70)
