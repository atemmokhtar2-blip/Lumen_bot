# Fix: Generated bot commands not working (cmd_{hash} names + stub handlers)

## Phase 1: Exploration  [x]
- [x] Clone repo, inspect engine structure
- [x] Identify the generation pipeline (SpecTranslator -> DSL -> grounding -> inference -> transpiler)
- [x] Examine screenshot of PDFX-AI bot

## Phase 2: Root Cause Analysis  [x]
- [x] Confirm `_slug_cmd` generates cmd_{hash} for unmapped Arabic labels
- [x] Confirm generated handlers for hash commands are echo-only stubs
- [x] Confirm buttons route to "استخدم /cmd" dead-end
- [x] Confirm AI translator under-extracts (secondary issue)

## Phase 3: Fix  [x]
- [x] Expand `_slug_cmd` stems (16 -> ~45 Arabic/English patterns)
- [x] Add `_transliterate_ar()` fallback for unmapped Arabic words
- [x] Reorder file-op stems before generic 'profile/ملف' stem
- [x] Expand transpiler `cmd_kind` to classify new command names (stats/list/mine)
- [x] Improve generic handler fallback (show record count, not just echo)
- [x] Improve callback handler (buttons now run command logic, not dead-end)
- [x] Run end-to-end test -> ALL PASS

## Phase 4: Delivery  [ ]
- [ ] Clean up temp scripts and test files
- [ ] Commit fix to a new branch
- [ ] Push and create Pull Request
- [ ] Explain problem + solution to user (Arabic)
