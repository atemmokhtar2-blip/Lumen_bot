# Maintenance playbook

## Weekly
- Review failed gates on `main` / PRs
- Dependabot security PRs (pip daily)

## Adding an API route
1. Implement with `require_tenant` or `require_admin`
2. Call `reject_identity_spoof` if body JSON
3. Use `tenant.tenant_id` only for data access
4. Add IDOR test (self vs other tenant)
5. Run: `pytest tests/test_security_idor_dast.py -q`

## Adding a security engine
1. Choose phase (1–4) — do not invent phase 5 in a random workflow without a gate
2. Official Action or `docker run ghcr.io/...` only
3. Wire into that phase’s `needs:` gate job
4. Document in `docs/26_SECURITY_ENGINES.md` + phase doc
5. Never `continue-on-error: true` on the failing check itself

## Upgrading an engine version
- Pin Action major versions deliberately; test on a branch
- ZAP image: `ZAP_IMAGE` env in `dast-zap.yml`

## Credits / promo changes
- Update `lumen.platform/credits/` only
- Tests: `test_welcome_credits.py`, `test_credits_ledger.py`
- Docs: `docs/20_CREDITS_LEDGER.md`, `docs/23_BALANCE_LIFECYCLE.md`

## Local verification (no Docker engines)
```bash
PYTHONPATH=. pytest tests/test_security_*.py tests/test_welcome_credits.py -q
PYTHONPATH=. python scripts/security/security_baseline_check.py --strict
```

## Local full DAST (requires Docker)
```bash
bash scripts/security/run_live_dast.sh
```
