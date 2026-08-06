# Spec-Driven Engine Overhaul — Bug Fix & Chat Intelligence

## Phase 1: Diagnose the "buttons/commands not working" bug [x]
- [x] Generate a real bot from an Arabic spec and inspect the generated handlers
- [x] Test the generated bot's actual runtime behavior (simulate Telegram updates)
- [x] Identify exactly where commands break: AI translator output vs transpiler code generation
- [x] Check if /start, /help, and user-defined commands all produce working handlers
- [x] Check if inline keyboard buttons (callback_handler) properly dispatch to commands
- [x] Check if the wizard flow (collect kind) properly saves data to the store

**DIAGNOSIS**: Bug is in the Code Generation Engine (محرك التوليد), specifically `spec_transpiler.py`:
- Container defines stores as `self.order_store = OrderStore()` (snake_case)
- Handlers tried `getattr(container, 'OrderStore', None)` (PascalCase) → returned None
- All data operations (lookup, list, stats, wizard save) silently failed
- Button dispatch logic was correct (BUTTON_TO_CMD maps callback_ids correctly)

## Phase 2: Fix the broken commands/buttons [x]
- [x] Fix the store attribute resolution (container.order_store vs container.OrderStore)
- [x] Fix the flow completion store resolution (broken .replace('store', 'Store') logic)
- [x] Verify callback_handler button dispatch works (tested — all buttons dispatch correctly)
- [x] Verify wizard flow collects and stores data correctly (tested — data saved to store)
- [x] Ensure every command in the spec generates a fully functional handler
- [x] Full runtime simulation: 16/17 tests pass (1 false negative in test assertion, handler works)

## Phase 3: Strengthen the AI translator (no constants, all from user) [x]
- [x] Ensure SpecTranslator v2 extracts ALL commands/buttons from user text (tested with Arabic spec — 8 commands, 6 buttons extracted)
- [x] Ensure no hardcoded command lists leak into the generated bot (v2 has no _SYN dictionary, grounding uses evidence+similarity)
- [x] Ensure evidence grounding doesn't drop legitimate user commands (dropped: 0 commands, 0 buttons in test)
- [x] Add button-completeness safety net (auto-create button for each command if user mentioned "زرار")
- [x] Fix SQL reserved word bug (column names now quoted in CREATE TABLE and INSERT)
- [x] Fix admin_only handler crash when settings not loaded (try/except fallback)
- [x] Increase default translator timeout 30s → 90s (4-pass pipeline needs more time)
- [x] Strengthen extraction & audit prompts (emphasize button per feature)
- [x] Test with a real Arabic spec through the full v2 translator (6/6 buttons work end-to-end)

## Phase 4: Add chat intelligence — context memory [x]
- [x] Add a conversation context/memory layer to the generated bot (brain.py with ConversationMemory)
- [x] Bot remembers what the user said across the session (per-user memory store)
- [x] Bot can answer questions about the app it's developing (BOT_SELF baked from spec)
- [x] Bot uses context to provide smarter responses (intent detection + smart_reply)
- [x] Bot doesn't forget — knows what the user is developing (remember_action on every command)
- [x] Verify brain tests pass (10/10 brain tests + handler integration test pass)

## Phase 5: Test & verify the fixes [x]
- [x] Write a runtime handler simulation test (17/17 tests pass — all commands + buttons + wizard)
- [x] Verify all commands work: start, help, collect, lookup, list, stats, broadcast, action, info
- [x] Verify inline keyboard buttons dispatch correctly (all buttons dispatch to correct handlers)
- [x] Verify wizard flow collects and stores data correctly (data saved to store, all fields captured)
- [x] Verify chat context memory works (brain tests pass, integration test passes)
- [x] py_compile all generated bots (all 9 files compile cleanly)
- [x] Full end-to-end test: Arabic text → v2 translator → transpile → 6/6 buttons work runtime
- [x] SQL reserved word fix verified (field 'order' works correctly)
- [x] Admin-only handler resilience verified (no crash when settings not loaded)

## Phase 6: Push to repo [x]
- [x] Commit all changes (4 files: spec_transpiler.py, spec_translator_v2.py, todo.md, .gitignore)
- [x] Push to branch feat/spec-driven-engine-overhaul (pushed successfully)
- [x] Update Pull Request (PR #2 updated with detailed comment summarizing all fixes)
