# Security Vulnerabilities Remediation — Round 2

## Confirmed Vulnerabilities — Fixes
- [x] 1. Environment-Dependent Cryptographic Weakness — `lumen/platform/tenants.py` `_key_pepper()` — reject known-weak peppers even in dev (fail-closed)
- [x] 2. Argument Injection in Dependency Scanner — `lumen/engine/services/dependency_scanner.py` `_run_pip_audit()` — strict req_path validation + sandbox isolation
- [x] 3. Inconsistent Multi-Node State Management — `lumen/engine/services/hosting/state_store.py` + `service.py` — SQLite WAL + multi-node guard
- [x] 4. Fragile Access Control Logic — `lumen/bot/helpers.py` `is_allowed()` — simplify + deduplicate

## Verification
- [x] Write tests for each fix (29 tests in test_security_hardening_v2.py)
- [x] Run all tests, confirm no regressions (29/29 new pass, 34/34 v1 pass; 26 pre-existing failures due to Redis not running — identical on original code)
- [ ] Commit and push to GitHub (Lumen + security-hardening-v1)
