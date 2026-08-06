# Task 5: Fix AI Hallucination + Real AI Chat Layer

## Problem (from user)
- AI translator STILL hallucinates: output doesn't match user's text (English field names instead of Arabic)
- AI should ONLY understand/translate, NEVER write code — add strict constraints
- Chat is dumb: treats everything as a bot command. Need a REAL AI chat layer that:
  - Understands what the user wants (AI-powered, not regex)
  - Acts as a developer companion
  - Has iron memory per user
  - Connected to the engine/translators
- Many errors in the bot/system

## Plan

### Phase 1: Strict AI Constraints + Anti-Hallucination [x]
- [x] Rewrite `_EXTRACT_SYSTEM` prompt: strict "understand only, never code" + require field names/entity names use user's own words
- [x] Rewrite `_INFER_SYSTEM` prompt: require flow_step keys grounded in original text
- [x] Add `_name_grounded()` post-grounding check: validate field names + entity names against original text (not just evidence)
- [x] Fix deep inference: re-infer commands that come back as CUSTOM with no fields
- [x] Require evidence quotes to be VERBATIM spans from original text
- [x] TESTED: fields now Arabic (اسم_الكتاب not title), kinds correct (collect/list/stats not custom)

### Phase 2: Real AI Chat Layer [x]
- [x] Replaced `_emit_brain_module` with g4f-powered AI chat (not regex)
- [x] Chat uses g4f to understand user messages with context + memory
- [x] Iron memory: UserMemory class (messages up to 80, actions up to 50, profile)
- [x] Developer companion persona: Arabic system prompt, knows bot spec
- [x] Connected to engine: BOT_SELF baked from spec (commands/entities/buttons)
- [x] Spec-aware fallback (_fallback_reply) when g4f unavailable
- [x] Syntax verified: transpiler parses OK, handlers call brain.smart_reply

### Phase 3: Fix System Errors [x]
- [x] Fixed: _ar_ident() transliterates Arabic→Latin for valid Python identifiers
- [x] Fixed: flow_step keys now meaningful (asm_alktab not 'x')
- [x] Fixed: model dataclass fields now meaningful (asm_alktab, asm_almlf, rqm_isbn)
- [x] Fixed: store columns now match model fields (consistent data flow)
- [x] Fixed: container store attributes use _ar_ident for entity names
- [x] Fixed: _emit_brain_module was missing return statement (returned None)
- [x] Verified: store create+get+list_all+list_by_user all work with Arabic data
- [x] Verified: brain BOT_SELF has correct Arabic entity fields for AI context
- [x] Verified: iron memory (messages, actions, summary, context, history) works
- [x] Verified: spec-aware fallback reply works (greeting, help, who-are-you)

### Phase 4: Test & Verify [x]
- [x] Hallucination test (library bot): field/entity names grounded in original text, dropped={}
- [x] Hallucination test (restaurant bot): all Arabic field names grounded, dropped={}
- [x] Command classification: COLLECT/LIST/STATS/LOOKUP/INFO (not all CUSTOM)
- [x] E2E test 1 (library): 12 files generated, verification ok=True
- [x] E2E test 2 (restaurant): 12 files generated, verification ok=True
- [x] Runtime test: store create+get+list works with Arabic data
- [x] Runtime test: brain iron memory + spec-aware fallback works
- [x] Runtime test: model dataclass with transliterated fields works
- [x] No meaningless 'x' field names in any generated bot
- [x] Enum sanitization: invalid post_action='action' mapped to 'none'

### Phase 5: Push to Repo [x]
- [x] Committed all changes (4 files, 928 insertions, 384 deletions)
- [x] Pushed to feat/spec-driven-engine-overhaul branch (PR #2)