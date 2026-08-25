# Security architecture — separation of concerns

```
                    ┌─────────────────────────────────────┐
                    │           GitHub CI gates           │
                    │  P1 security │ P2 DAST │ P3 supply │ P4 policy │
                    └─────────────────────────────────────┘
                         │            │           │            │
                         ▼            ▼           ▼            ▼
                   Official        ZAP docker   Syft/Grype   Checkov/
                   SAST/secrets    + IDOR tests  OSV/Trivy    OPA/Hadolint
                         │            │
                         ▼            ▼
              ┌──────────────────────────────┐
              │         Runtime API          │
              │  require_tenant/admin        │
              │  lumen/api/ownership.py            │
              │  CreditService ledger        │
              │  PolicyEngine (tools)        │
              └──────────────────────────────┘
```

## Boundaries (do not cross carelessly)

| Layer | Owns | Must not own |
|-------|------|----------------|
| `lumen/lumen/api/auth.py` | Authentication | Business credit math |
| `lumen/lumen/api/ownership.py` | IDOR primitives | Billing Stripe details |
| `lumen/lumen/api/routes/*` | HTTP mapping | Direct DB wallet edits |
| `lumen.platform/credits/` | Ledger, promo TTL | HTTP headers |
| `lumen.engine/security/` | Tool policy | Tenant API keys |
| `.github/workflows/security.yml` | Phase 1 only | ZAP / Grype |
| `.github/workflows/dast-zap.yml` | Phase 2 only | Bandit / CodeQL |
| `policy/*.rego` | OPA Dockerfile/GHA rules | Application Python |

## Scaling guidance

- New domain (e.g. `billing_v2`): new package + `tests/test_security_*` for isolation + route wiring checklist in `04_IDOR_OWNERSHIP.md`.
- New scanner: add to **one** phase workflow only; extend that phase’s gate job `needs:`.
- Never create `scripts/security/my_scanner.py` that reimplements CVE matching.
