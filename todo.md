# Lumen Bot — Fix Trial Chat (Live Run) From The Root

## Root Cause Analysis
- [x] `try_bot_token()` in `early_gates.py` crashed with `AttributeError: 'str' object has no attribute 'get'` — called `handle_live_run_token(message, context, user, tok)` with WRONG args (user as token, tok as pending)
- [x] `decide_isolation()` returned `require_docker=True, allow_local=False` because `TBE_MULTI_TENANT` defaulted to "1" — blocked local process fallback
- [x] `safe_zip.py` skips ALL dotfiles (security) — `.env.example` excluded from delivered ZIP
- [x] Screenshot confirms: ZIP delivered (2KB, 7 files) but trial chat failed when user sent token

## Fix 1: Rewrite `try_bot_token()` in `early_gates.py` (DONE, NOT COMMITTED)
- [x] Retrieve `pending_run` / `pending_deploy` from `context.user_data`
- [x] Pass `tok` (string) as token and `pending_run` (dict) as pending
- [x] Added user-friendly message when no pending project exists

## Fix 2: Enable local process fallback via `.env` (DONE, NOT COMMITTED)
- [x] Added `TBE_MULTI_TENANT=0`, `TBE_ALLOW_LOCAL_PROCESS=1`, `TBE_FORCE_LOCAL_PROCESS=1`, `LIVE_RUN_SECONDS=1800`
- [x] Verified: `decide_isolation()` returns `require_docker=False, allow_local=True`

## Fix 3: Include `.env.example` in delivered ZIP (TODO)
- [ ] Add `.env.example` to dotfile allowlist in `safe_zip.py`
- [ ] Keep security: still skip `.env`, `.aws`, `.git`, etc. — only allow `.env.example`

## Fix 4: Test full trial chat flow end-to-end (TODO)
- [ ] Run `live_run_test.py` with real generated project + verify LocalProcessDriver starts
- [ ] Verify ZIP now contains `.env.example`
- [ ] Verify `try_bot_token` correctly dispatches to `handle_live_run_token`

## Fix 5: Commit and push all changes (TODO)
- [ ] Commit `early_gates.py` fix
- [ ] Commit `safe_zip.py` fix
- [ ] Push to GitHub (branch Lumen)
- [ ] Restart bot with all fixes
