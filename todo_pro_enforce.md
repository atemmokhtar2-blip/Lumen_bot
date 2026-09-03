# Lumen Pro — Hard Enforcement Todo (real limits, not display-only)

## Audit findings (verified by reading actual code)
- Payment flow: WORKS (send_invoice XTR 2000 stars, pre_checkout ok, successful_payment records user_data["pro_plan"])
- Bot limit: NOT enforced by plan — uses TBE_MAX_BOTS_PER_USER env (default 50), ignores Pro
- Storage: NOT enforced by plan — disk_quota.py uses TBE_USER_DISK_MB (default 512MB), ignores Pro
- RAM: NOT enforced by plan — project_manifest uses TBE_BOT_MEMORY_MB (default 256MB), ignores Pro
- CPU: NOT enforced by plan — project_manifest uses TBE_BOT_CPU (default 0.5), ignores Pro
- Expiry: NOT checked — expires_at written but never read to revoke access
- user_data["pro_plan"] written but NEVER READ by any enforcement code

## Implementation plan
- [x] 1. Create `pro_plan_entitlement.py` — secure entitlement resolver (reads persisted subscription, checks expiry, returns active plan or None). Tamper-resistant: signed, server-side, not client-trusted.
- [x] 2. Persist subscription durably (Redis/session_store) — added "pro_plan" to _DURABLE_KEYS (was being silently dropped!)
- [x] 3. Enforce bot limit: HostingService.start checks Pro entitlement → 3 bots for Pro, else default env limit (both scale and non-scale paths)
- [x] 4. Enforce storage: disk_quota.max_user_bytes(user_id) → 2GB for Pro, else default
- [x] 5. Enforce RAM: project_manifest.default_resources_for_user(user_id) → 512MB for Pro, else default
- [x] 6. Enforce CPU: project_manifest.default_resources_for_user(user_id) → 0.5 for Pro, else default
- [x] 7. Enforce expiry: entitlement resolver returns None if expires_at < now → all limits revert to defaults
- [x] 8. Verify exact payment amount (2000 stars) in successful_payment handler (security hardening)
- [x] 9. Write tests for entitlement resolution + enforcement (12 tests, all pass)
- [ ] 10. Commit + push to Lumen
