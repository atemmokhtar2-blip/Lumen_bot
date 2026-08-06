# Task 6: Fix ALL commands not working — Root cause fix

## Root Causes Identified
1. wizard_cmds only includes COLLECT — LOOKUP commands with flow_steps are excluded from wizard flow
2. Flow completion ALWAYS does store.create() — doesn't handle LOOKUP (should search instead)
3. Store has no search_by_field method — can't search by collected field values
4. requirements.txt missing g4f — brain.py imports g4f but it's not in requirements

## Fixes to Apply
- [x] Read and understand all affected code sections in spec_transpiler.py
- [x] Fix 1: wizard_cmds includes LOOKUP (and any kind with flow_steps)
- [x] Fix 2: Add search_by_field to MemoryStore and SQLite stores
- [x] Fix 3: Flow completion handles LOOKUP (search) vs COLLECT (store)
- [x] Fix 4: Add g4f to requirements.txt
- [x] Fix 5: Button sanitization — auto-fill callback_id from target_command/label
- [x] Re-run behavior_test.py — 25/25 PASSED
- [x] E2E search test — 22/22 PASSED (search flow completion works)
- [x] Full AI E2E test — 24/24 PASSED (AI translate → transpile → all commands work)
- [x] Push fixes to repo (commit 45e3330 on feat/spec-driven-engine-overhaul)
