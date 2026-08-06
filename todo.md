# Task 3: Implement the engine overhaul (spec-driven, zero hardcoded templates)

## Phase 1: Scaffold & RichSpec schema [x]
- [ ] Create `telegram_bot_engine/formal_engine/schemas/rich_spec.py` — deep JSON schema (20+ fields)
- [ ] Define RichSpec, RichCommand, RichButton, RichEntity, RichRule, RichFlowStep, RichEvidence

## Phase 2: Multi-pass SpecTranslator [x]
- [ ] Rewrite `spec_translator.py` — 4-pass LLM pipeline (extraction → fidelity → inference → grounding)
- [ ] Output RichSpec JSON directly (no spec_to_text lossy round-trip)
- [ ] Evidence-based grounding (no _SYN synonym lists)

## Phase 3: ContractBuilder (direct JSON→Contract, no text) [x]
- [ ] Create `telegram_bot_engine/formal_engine/spec_pipeline/contract_builder.py`
- [ ] Build ProgramContract directly from RichSpec
- [ ] Eliminate lossy text round-trip entirely

## Phase 4: SpecDrivenInference [x]
- [ ] Create `telegram_bot_engine/formal_engine/spec_pipeline/spec_inference.py`
- [ ] Infer from RichSpec fields only (no _INPUT_VERBS, _SKIP_CMDS, _PROMPT, etc.)
- [ ] Use command kind, collects_fields, post_action from spec

## Phase 5: SpecDrivenTranspiler [x]
- [ ] Create `telegram_bot_engine/formal_engine/spec_pipeline/spec_transpiler.py`
- [ ] Generate code from ProgramContract only (no hardcoded cmd_kind lists)
- [ ] Unified cmd_kind source (no duplicate)

## Phase 6: ArchitecturalGroundingGate [x]
- [ ] Create `telegram_bot_engine/formal_engine/spec_pipeline/grounding_gate.py`
- [ ] Evidence-based grounding with semantic similarity fallback (0.7 threshold)
- [ ] No synonym lists

## Phase 7: Wire new pipeline [x] VERIFIED
- [ ] Update `__init__.py` generate_bot() to use new spec-driven pipeline
- [ ] Update `pipeline_formal.py` build_from_text to accept RichSpec
- [ ] Keep fallback to old pipeline only if RichSpec fails

## Phase 8: Test & verify [x]
- [x] Write benchmark test script
- [x] Test with multiple Arabic specs (delivery bot, course booking, store inventory, info bot)
- [x] Verify generated bots have working commands
- [x] py_compile all generated bots
- [x] Runtime store test (create/get/list_all/list_by_user/update_status)
- [x] Verify no hardcoded classification in new pipeline
- [x] Fix SQL reserved word quoting (e.g. "order" table)
- [x] Fix old fallback transpiler f-string bug

## Phase 9: Push to repo [ ]
- [ ] Commit all changes
- [ ] Push branch feat/spec-driven-engine-overhaul
- [ ] Create Pull Request
