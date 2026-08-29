# Lumen Bot — Fix exfil_env Guardrail + Zip Delivery + Deterministic Repair + Live Run

## Root Cause Analysis
- [x] Identified: `exfil_env` guardrail pattern `(print|show|dump|leak|reveal).{0,40}(api[_-]?key|token|secret|TELEGRAM_BOT|GEMINI_API)` is too aggressive
- [x] Confirmed: On retry/next-task, `build_worker_context()` reads existing `main.py` → `repo_block` includes `print("Error: TELEGRAM_BOT_TOKEN...")` → appended to `full_goal` → `scan_user_input()` triggers `exfil_env` → agent blocked
- [x] Confirmed: Generated `main.py` at gen_20260829_214257 contains `print("Error: TELEGRAM_BOT_TOKEN not found in environment.")`

## Fix 1: Refine exfil_env guardrail pattern (commit 67bf0d9)
- [x] Made pattern only match actual exfiltration (verb + secret + context), with negative lookahead to exclude "not found"/"missing"/"required" error-guard patterns
- [x] Added second `exfil_send` pattern for explicit "send secret to URL/endpoint" attacks
- [x] Test: 9/9 legitimate bot code passes, 7/7 injection attempts blocked (test_guardrail_fix.py)
- [x] Verified: actual generated main.py + full_goal with repo_block both pass

## Fix 2: Only scan user's original input, not accumulated context (commit 67bf0d9)
- [x] Added `scan_user_request_only()` to `prompt_guard.py` — extracts only user's original request (before `---`, `TARGET FILES:`, `REPO CONTEXT:` markers) and scans just that
- [x] Updated `agent_loop.py` to use `scan_user_request_only()` as primary scan, with secondary full-goal scan only for DANGEROUS code-exec patterns (os.system, eval, exec, etc.)
- [x] Mock test passes, imports verified

## Fix 3: Ensure zip delivery to user after successful generation (commit 67bf0d9)
- [x] Found root cause: `try_handle_hitl_message()` returned only text — never called `deliver_generation_result()`
- [x] Modified `try_handle_hitl_message()` to return 3-tuple `(handled, reply, state)` — includes final AgentState
- [x] Modified `callback_router.py` `_handle_hitl_callback()` to call `deliver_generation_result()` when state status is DELIVERED/PASSED and project_path exists
- [x] Updated `message_router.py` to handle 3-tuple return
- [x] All imports verified OK

## Fix 4: Run deterministic repair BEFORE acceptance check (commit 39c3eb2)
- [x] Root cause: Agent generates main.py + requirements.txt but NOT README.md or app/handlers.py
- [x] Acceptance check in node_work fails because README.md missing → scaffold task FAILED → generation FAILED
- [x] apply_deterministic_repairs() creates missing files but only ran in repair node (AFTER critique), not in node_work (BEFORE acceptance)
- [x] Added apply_deterministic_repairs() call in node_work BEFORE acceptance check
- [x] Removed destructive 'align_main_to_app_handlers' — no longer overwrites agent's main.py
- [x] Verified: agent main.py preserved, app/handlers.py + README.md created, gen_verify passes, acceptance passes

## Fix 5: Verify full flow end-to-end
- [x] Bot restarted with all fixes (pid 19856, polling started 22:15)
- [ ] User tests via @lum9n_bot: send request → confirm plan → verify zip delivered
- [ ] Verify generated bot has README with run instructions
- [x] Committed all fixes (67bf0d9, 39c3eb2)
