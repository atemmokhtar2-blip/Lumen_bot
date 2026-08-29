# Todo: Investigate why generated bots don't match user requests

## Phase 1: Map the generation pipeline
- [ ] Read agent_brain / agent_loop code — how LLM responses are parsed, where failures occur
- [ ] Read prompt construction code — how user requests become prompts
- [ ] Read LLM model configuration — which models, what parameters
- [ ] Read graph_builder — LangGraph flow, where quality could degrade
- [ ] Read deterministic_repair.py — does it overwrite or supplement agent output?

## Phase 2: Examine real generated outputs
- [ ] Inspect actual generated project code at /var/lib/lumen/users/98/10/7631249810/projects/
- [ ] Compare generated code vs what was likely requested
- [ ] Check agent_brain logs / parse failure logs from actual generation runs
- [ ] Find any saved prompts or LLM responses from real runs

## Phase 3: Identify weak points (ROOT CAUSE FOUND + FIXED)
- [x] Classify each weak point: model weakness vs prompt vs architecture vs parsing
- [x] Document evidence (actual code, actual logs, actual outputs)
  - ROOT CAUSE #1 (FIXED): _merge_agent_state reducer dropped user_text/user_id/state_id
  - ROOT CAUSE #2 (FIXED): InvalidUpdateError on last_node in parallel Send (no reducer)
  - ROOT CAUSE #3 (FIXED): BridgeSpecBackend TypeError (features_from_text include_core arg)
  - WEAK POINT #4 (model): gemini-3.1-flash-lite returns empty text for architect spec
  - WEAK POINT #5 (model): LLM generates syntax errors (duplicate lines in handlers.py)
  - WEAK POINT #6 (planner): over-decomposes simple requests (modules/telegram_bot_api.py)
  - WEAK POINT #7 (model): no maxOutputTokens set → default limit may truncate
  - WEAK POINT #8 (model): all models are flash-lite (weakest tier), no pro models
- [x] Fix the _merge_agent_state reducer to preserve identity fields from right
- [x] Fix the InvalidUpdateError by adding reducers to GraphState scalar fields
- [x] Fix the BridgeSpecBackend TypeError
- [x] Test the fix (reducer unit test + real LangGraph + full pipeline generation)
- [x] Verify generated bot matches user request (تم الاستلام handler = user's request!)
- [ ] Write findings report with recommendations

## Phase 4: Deliver findings
- [x] Present findings to user with evidence
- [x] If model weakness → recommend stronger paid models
- [x] If pipeline issue → recommend fix (3 PIPELINE BUGS FIXED + PUSHED)
- [x] PUSH the fix to GitHub (commit 4f4b816)
