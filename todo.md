# Lumen Root Fix — ONE Strong Path (from foundation)

## STATUS AUDIT (weaknesses 1-6)
| # | Weakness | Status | Evidence |
|---|----------|--------|----------|
| 1 | Message path heavy/complex | PARTIAL | Dead code removed (1434->1398). Still 254 branches, 1398 lines. Needs further simplification. |
| 2 | Generation time not guaranteed | DONE | 3-layer timeout (OUTER 180s / INNER 150s / PER-CALL 45s). Commit 3190cec. |
| 3 | Multi-agent optional + fallback UX unequal | PARTIAL | Both paths -> same deliver_generation_result (delivery parity OK). BUT no clear user log when fallback fires (looks like "stuck"). |
| 4 | Code huge/sprawling | PARTIAL | 3 dead modules deleted (commit 594a2e5). Audit confirmed rest is LIVE. |
| 5 | Hosting/live depends on real env | DESIGN-OK | Dockerfile + HEALTHCHECK + live_runner (token validate, webhook clear, syntax repair, trial chat, sandbox). Not a code weakness - runtime infra. |
| 6 | Generated code quality not guaranteed | GAP | delivery.py injects Dockerfile but does NOT ensure README/token-setup. Acceptance checks README only IF criterion includes "readme". No mandatory gate. |

## COMPLETED (already pushed)
- [x] Phase 0: Research & Plan
- [x] Phase 1 (#2): Generation time guarantee - 3-layer timeout. Commit 3190cec PUSHED.
- [x] Phase 2 (#1 partial): Simplify router - delete dead code. Commit debebcc PUSHED.
- [x] Phase 3 (#4 partial): Delete 3 dead modules. Commit 594a2e5 PUSHED.

## REMAINING WORK (fix from root, push after EACH)

### Phase 4: Weakness #6 - Guarantee generated code quality (README + token setup)
- [x] 4.1 Added ensure_project_readme() to helpers.py - injects clear README (token setup + run + Docker) if missing/thin
- [x] 4.2 Wired into delivery.py after Dockerfile injection (before smoke test) - every shipped zip has README
- [x] 4.3 5 tests in test_readme_guarantee.py - ALL PASS (inject/thin/adequate/docker/empty-request)
- [x] 4.4 Verified no regressions + COMMIT ea3b63e + PUSH (594a2e5..ea3b63e)

### Phase 5: Weakness #3 - Fallback UX parity (clear user-visible signal)
- [ ] 5.1 When Cline fallback fires, send user a clear message instead of silence
- [ ] 5.2 Write test for fallback notification
- [ ] 5.3 Verify tests + COMMIT + PUSH

### Phase 6: Weakness #1 - Further router simplification
- [ ] 6.1 Audit remaining 254 branches - identify further dead/redundant logic
- [ ] 6.2 Simplify where safe (without breaking behavior)
- [ ] 6.3 Verify tests + COMMIT + PUSH
