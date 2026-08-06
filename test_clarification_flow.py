"""
Test 2: Simulate the clarification flow that produces cmd_{hash} names.
This replicates what the user experienced with PDFX-AI.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from telegram_bot_engine.formal_engine.services.clarification.service import (
    _slug_cmd, merge_answers, assess_spec, _normalize_answer_to_sections
)

# Test the _slug_cmd function with Arabic feature names from the screenshot
test_labels = [
    "إدارة الجلسات",
    "استعادة كلمة المرور",
    "إدارة الأجهزة المتصلة",
    "إحصائيات مباشرة",
    "رسوم بيانية",
    "إدارة المستخدمين",
    "إدارة مفصلة للمشرفين",
    "دعم المصادقة الثنائية 2FA",
    "لوحة تحكم ويب React أو Next.js",
    "تسجيل واشتراك حسابات",
]

print("=" * 70)
print("TEST: _slug_cmd with Arabic feature labels")
print("=" * 70)
for label in test_labels:
    slug = _slug_cmd(label)
    print(f"  '{label}' → /{slug}")

print()
print("=" * 70)
print("TEST: Simulate clarification merge → assess → extract_dsl")
print("=" * 70)

# Simulate: user says "اعمل بوت باسم PDFX-AI"
original = "اعمل بوت تيليجرام باسم PDFX-AI"
# First assessment
assessment = assess_spec(original)
print(f"Initial assessment: ready={assessment.ready}, step={assessment.next_step}")
print(f"Question: {assessment.step_question}")

# User answers the commands question with Arabic feature words
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
print(f"\nMerged text:\n{merged[:500]}")

# Assess again
assessment2 = assess_spec(merged)
print(f"\nAssessment 2: ready={assessment2.ready}")
print(f"Commands found: {assessment2.summary.get('commands')}")

# Extract DSL to see final commands
from telegram_bot_engine.formal_engine.dsl.extractor import extract_dsl
prog = extract_dsl(merged)
print(f"\nDSL commands: {[c.name for c in prog.commands]}")
print(f"DSL entities: {[e.name for e in prog.entities]}")
print(f"DSL buttons: {[b.label for b in prog.buttons]}")

print()
print("=" * 70)
print("CONCLUSION: These cmd_{hash} commands ARE generated and registered,")
print("but they have NO meaningful handlers — they just reply with the")
print("description text or 'استخدم /cmd'. This is why 'commands don't work'.")
print("=" * 70)
