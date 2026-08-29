# Lumen Bot — Fix exfil_env Guardrail + Zip Delivery + Live Run

## Root Cause Analysis
- [x] Identified: `exfil_env` guardrail pattern `(print|show|dump|leak|reveal).{0,40}(api[_-]?key|token|secret|TELEGRAM_BOT|GEMINI_API)` is too aggressive
- [x] Confirmed: On retry/next-task, `build_worker_context()` reads existing `main.py` → `repo_block` includes `print("Error: TELEGRAM_BOT_TOKEN...")` → appended to `full_goal` → `scan_user_input()` triggers `exfil_env` → agent blocked
- [x] Confirmed: Generated `main.py` at gen_20260829_214257 contains `print("Error: TELEGRAM_BOT_TOKEN not found in environment.")`

## Fix 1: Refine exfil_env guardrail pattern
- [x] Made pattern only match actual exfiltration (verb + secret + context), with negative lookahead to exclude "not found"/"missing"/"required" error-guard patterns
- [x] Added second `exfil_send` pattern for explicit "send secret to URL/endpoint" attacks
- [x] Test: 9/9 legitimate bot code passes, 7/7 injection attempts blocked (test_guardrail_fix.py)
- [x] Verified: actual generated main.py + full_goal with repo_block both pass

## Fix 2: Only scan user's original input, not accumulated context
- [x] Added `scan_user_request_only()` to `prompt_guard.py` — extracts only user's original request (before `---`, `TARGET FILES:`, `REPO CONTEXT:` markers) and scans just that
- [x] Updated `agent_loop.py` to use `scan_user_request_only()` as primary scan, with secondary full-goal scan only for DANGEROUS code-exec patterns (os.system, eval, exec, etc.)
- [x] Mock test passes, imports verified

## Fix 3: Ensure zip delivery to user after successful generation
- [x] Found root cause: `try_handle_hitl_message()` returned only text — never called `deliver_generation_result()`
- [x] Modified `try_handle_hitl_message()` to return 3-tuple `(handled, reply, state)` — includes final AgentState
- [x] Modified `callback_router.py` `_handle_hitl_callback()` to call `deliver_generation_result()` when state status is DELIVERED/PASSED and project_path exists
- [x] Updated `message_router.py` to handle 3-tuple return
- [x] All imports verified OK

## Fix 4: Verify full flow end-to-end
- [x] Restarted the bot (pid 16746, polling started)
- [ ] Send a test request → user needs to test via @lum9n_bot
- [ ] Confirm plan
- [ ] Wait for generation to complete
- [ ] Verify zip file is delivered
- [x] Committed and pushed all fixes (commit 67bf0d9)
