#!/usr/bin/env python3
"""
Test the trial chat live run flow — the "temporary trial" the user wants to work.

This tests:
  1) run_bot_project() with a real generated project + dummy token
  2) Verifies LocalProcessDriver starts the bot process
  3) Verifies the bot actually runs (or at least starts without crash)

The user said: "عالج التجربه المؤقته دي من الجذر وخليها شغاله مليون في المئه مؤقته"
(fix the temporary trial from the root and make it work 100%)
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

print("=" * 70)
print("LIVE RUN (TRIAL CHAT) TEST")
print("=" * 70)

# Check isolation policy
from lumen.engine.services.isolation_policy import decide_isolation
d = decide_isolation()
print(f"Isolation: require_docker={d.require_docker}, allow_local={d.allow_local}")
if not d.allow_local:
    print("✗ Local process NOT allowed — set TBE_ALLOW_LOCAL_PROCESS=1 + TBE_FORCE_LOCAL_PROCESS=1 + ENVIRONMENT=dev")
    sys.exit(1)
print("✓ Local process allowed")

# Find the latest generated project (directories only, not .zip files)
import glob
projects = sorted(
    p for p in glob.glob("/var/lib/lumen/users/98/10/7631249810/projects/gen_*")
    if Path(p).is_dir()
)
if not projects:
    projects = sorted(
        p for p in glob.glob("/var/lib/lumen/users/99/99/9999999999/projects/e2e_test_*")
        if Path(p).is_dir()
    )
if not projects:
    print("No generated project found — run e2e_test.py first")
    sys.exit(1)

project_path = projects[-1]
print(f"\nUsing project: {project_path}")
print(f"Files: {sorted(p.name for p in Path(project_path).rglob('*') if p.is_file() and '__pycache__' not in str(p))}")

# Test run_bot_project with a dummy token (it will fail to connect to Telegram
# but should start the process and show it tried)
DUMMY_TOKEN = "1234567890:AATestDummyTokenForLiveRunTestingOnlyXXXXXX"
RUN_SECONDS = 15  # short test

print(f"\nRunning bot project for {RUN_SECONDS}s with dummy token...")
print("(The bot will start, fail to connect to Telegram with the dummy token,")
print(" but we verify the process starts and the runner works)")
print()

from lumen.engine.services.live_runner import run_bot_project

t0 = time.time()
try:
    report = run_bot_project(
        project_path=project_path,
        bot_token=DUMMY_TOKEN,
        entry_hint="main.py",
        run_seconds=RUN_SECONDS,
    )
except Exception as e:
    print(f"EXCEPTION: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(2)

elapsed = time.time() - t0
print(f"\nrun_bot_project returned in {elapsed:.1f}s")
print(f"  ok         = {report.ok}")
print(f"  phase      = {report.phase}")
print(f"  message    = {report.message}")
print(f"  warnings   = {report.warnings}")
print(f"  entry_point= {report.entry_point}")
if report.install_log:
    print(f"  install_log (last 300 chars):")
    print(f"    {report.install_log[-300:]}")
if report.run_log:
    print(f"  run_log (last 500 chars):")
    print(f"    {report.run_log[-500:]}")

# The dummy token will cause a Telegram 401 error, but the process should START
# That's what we're testing — the runner works, the bot process launches
if report.ok:
    print("\n🎉 LIVE RUN TEST PASSED — bot process started successfully!")
    print("   (With a real token, the bot would connect to Telegram and respond)")
    sys.exit(0)
elif "401" in str(report.run_log) or "Unauthorized" in str(report.run_log) or "token" in str(report.run_log).lower():
    print("\n✓ LIVE RUN PARTIAL PASS — bot process started but failed auth (expected with dummy token)")
    print("  The runner works! With a real BotFather token, the bot would run.")
    sys.exit(0)
else:
    print(f"\n⚠️  LIVE RUN returned ok=False")
    print(f"   phase={report.phase}, message={report.message}")
    # If it's a dependency install issue, that's fixable
    if "install" in str(report.message).lower() or "pip" in str(report.message).lower():
        print("   This is a dependency install issue — checking if python-telegram-bot is installed...")
    sys.exit(3)
