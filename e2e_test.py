#!/usr/bin/env python3
"""
End-to-end test of the Lumen generation pipeline.

Simulates the full user flow WITHOUT Telegram:
  1) User sends request  -> orchestrate_generate()  (runs LangGraph -> HITL pause)
  2) User confirms plan  -> resume_langgraph_hitl()  (resumes LangGraph -> work -> deliver)
  3) Verify final state: DELIVERED/PASSED, README.md, app/handlers.py, acceptance passed

This is the test the user demanded: "اعمل اختبارات عندك وشوف ايه السبب"
(do tests yourself and find the cause).
"""
from __future__ import annotations

import os
import sys
import time
import json
import traceback
from pathlib import Path

# Ensure we import from the Lumen_bot package
sys.path.insert(0, str(Path(__file__).parent))

# --- env already sourced by the shell that launches this script ---
# But double-check critical vars
_required = ["GEMINI_API_KEYS", "TELEGRAM_BOT_TOKEN"]
for v in _required:
    if not os.getenv(v):
        print(f"WARNING: env var {v} is not set")

OUTPUT_DIR = os.getenv("OUTPUT_DIR") or "/var/lib/lumen"
os.environ.setdefault("OUTPUT_DIR", OUTPUT_DIR)
os.environ.setdefault("LUMEN_OUTPUT_DIR", OUTPUT_DIR)

TEST_USER_ID = 9999999999  # synthetic test user (not a real Telegram user)
TEST_REQUEST = "بوت تيليجرام بسيط يرد على الرسائل بكلمة مرحبا ويعرض زر بدء"

print("=" * 70)
print("LUMEN END-TO-END PIPELINE TEST")
print("=" * 70)
print(f"OUTPUT_DIR    = {OUTPUT_DIR}")
print(f"TEST_USER_ID  = {TEST_USER_ID}")
print(f"TEST_REQUEST  = {TEST_REQUEST}")
print(f"Python        = {sys.executable}")
print()

# ── Step 1: orchestrate_generate (initial run -> should pause at HITL) ──
print("─" * 70)
print("STEP 1: orchestrate_generate()  (expect HITL pause at plan approval)")
print("─" * 70)

from lumen.engine.services.multi_agent import orchestrate_generate

work_dir = Path(OUTPUT_DIR) / "users" / "99" / "99" / str(TEST_USER_ID) / "projects" / f"e2e_test_{int(time.time())}"
work_dir.mkdir(parents=True, exist_ok=True)
print(f"work_dir = {work_dir}")

t0 = time.time()
try:
    result = orchestrate_generate(
        TEST_REQUEST,
        work_dir,
        user_id=TEST_USER_ID,
    )
except Exception:
    print("EXCEPTION in orchestrate_generate:")
    traceback.print_exc()
    sys.exit(1)

elapsed = time.time() - t0
print(f"orchestrate_generate returned in {elapsed:.1f}s")
print(f"  success       = {getattr(result, 'success', '?')}")
print(f"  project_path  = {getattr(result, 'project_path', '?')}")
meta = getattr(result, "metadata", {}) or {}
print(f"  status        = {meta.get('status', '?')}")
print(f"  qa_passed     = {meta.get('qa_passed', '?')}")
print(f"  awaiting_hitl = {meta.get('awaiting_hitl', '?')}")
print(f"  langgraph_interrupt = {meta.get('langgraph_interrupt', '?')}")
print(f"  state_id      = {meta.get('state_id', '?')}")
print(f"  thread_id     = {meta.get('langgraph_thread_id', '?')}")
print(f"  final_message = {(meta.get('final_message') or '')[:300]}")
errs = getattr(result, "errors", []) or []
if errs:
    print(f"  errors        = {errs[:5]}")

awaiting = meta.get("awaiting_hitl") or meta.get("langgraph_interrupt")
state_id = meta.get("state_id")
thread_id = meta.get("langgraph_thread_id")

if not awaiting:
    print()
    print("!!! DID NOT PAUSE AT HITL !!!")
    print("This means either:")
    print("  - HITL is disabled (hitl_interrupt_enabled()=False)")
    print("  - The graph ran all the way through (no interrupt)")
    print("  - Or it failed before reaching the plan approval gate")
    # Check if it succeeded anyway
    if getattr(result, "success", False) and meta.get("qa_passed"):
        print("  BUT generation succeeded with QA passed — that's fine!")
        status = meta.get("status", "")
        if status in {"DELIVERED", "PASSED"}:
            print("  Status is DELIVERED/PASSED — pipeline works end-to-end!")
            sys.exit(0)
    sys.exit(2)

print()
print("✓ Generation paused at HITL plan approval gate (as expected)")

# ── Step 2: resume_langgraph_hitl (user confirms plan) ──
print()
print("─" * 70)
print("STEP 2: resume_langgraph_hitl()  (simulate user confirming the plan)")
print("─" * 70)

from lumen.engine.services.multi_agent import (
    get_blackboard,
    latest_for_user,
    resume_langgraph_hitl,
)
from lumen.engine.services.multi_agent.state import AgentState

# Retrieve the state from the blackboard
board = get_blackboard()
state = latest_for_user(TEST_USER_ID)
if state is None:
    # Try to reconstruct from blackboard by state_id
    print(f"latest_for_user returned None — trying state_id={state_id}")
    state = board.get(state_id) if state_id else None

if state is None:
    print("!!! Could not retrieve AgentState from blackboard !!!")
    print(f"state_id={state_id}, thread_id={thread_id}")
    sys.exit(3)

print(f"Retrieved state: state_id={state.state_id}")
print(f"  status        = {state.status}")
print(f"  thread_id     = {(state.extensions or {}).get('langgraph_thread_id')}")

t1 = time.time()
try:
    out_state = resume_langgraph_hitl(
        state,
        decision="approved",
        context={"work_dir": str(work_dir), "user_id": TEST_USER_ID},
        board=board,
        thread_id=thread_id or state.state_id,
    )
except Exception:
    print("EXCEPTION in resume_langgraph_hitl:")
    traceback.print_exc()
    sys.exit(4)

elapsed2 = time.time() - t1
print(f"resume_langgraph_hitl returned in {elapsed2:.1f}s")
print(f"  status        = {out_state.status}")
print(f"  qa_passed     = {out_state.qa_passed}")
print(f"  generated_path= {out_state.generated_path}")
print(f"  attempts      = {out_state.attempts}/{out_state.max_attempts}")
print(f"  build_success = {out_state.build_success}")
print(f"  final_message = {(out_state.final_message or '')[:400]}")
build_errs = list(out_state.build_errors or [])
if build_errs:
    print(f"  build_errors  = {build_errs[:5]}")

# ── Step 3: Verify deliverables ──
print()
print("─" * 70)
print("STEP 3: Verify deliverables (README.md, app/handlers.py, main.py)")
print("─" * 70)

gen_path = Path(out_state.generated_path or work_dir)
print(f"Project path: {gen_path}")

if not gen_path.exists():
    print(f"!!! Project path does not exist: {gen_path}")
    sys.exit(5)

files = sorted(p.name for p in gen_path.rglob("*") if p.is_file())
print(f"Files in project: {files}")

checks = {
    "main.py": (gen_path / "main.py").is_file(),
    "requirements.txt": (gen_path / "requirements.txt").is_file(),
    "README.md": (gen_path / "README.md").is_file(),
    "app/handlers.py": (gen_path / "app" / "handlers.py").is_file(),
    ".env.example": (gen_path / ".env.example").is_file(),
}
for name, ok in checks.items():
    mark = "✓" if ok else "✗"
    print(f"  {mark} {name}: {'exists' if ok else 'MISSING'}")

# ── Step 4: Final verdict ──
print()
print("─" * 70)
print("STEP 4: Final verdict")
print("─" * 70)

status_str = str(out_state.status).upper()
passed = status_str in {"DELIVERED", "PASSED"} and out_state.qa_passed
all_files = all(checks.values())

print(f"  status           = {status_str}")
print(f"  qa_passed        = {out_state.qa_passed}")
print(f"  all_files_exist  = {all_files}")
print(f"  PIPELINE_PASSED  = {passed and all_files}")

if passed and all_files:
    print()
    print("🎉 END-TO-END TEST PASSED! The pipeline works correctly.")
    print("   - HITL plan approval gate works")
    print("   - Generation completes after confirmation")
    print("   - Deterministic repair creates README.md + app/handlers.py")
    print("   - Acceptance check passes")
    print("   - Status is DELIVERED/PASSED")
    sys.exit(0)
else:
    print()
    print("💀 END-TO-END TEST FAILED.")
    if not all_files:
        missing = [k for k, v in checks.items() if not v]
        print(f"   Missing files: {missing}")
    if not out_state.qa_passed:
        print(f"   QA did not pass. build_errors: {build_errs[:5]}")
    if status_str not in {"DELIVERED", "PASSED"}:
        print(f"   Final status is {status_str} (not DELIVERED/PASSED)")
    print(f"   final_message: {(out_state.final_message or '')[:500]}")
    sys.exit(6)
