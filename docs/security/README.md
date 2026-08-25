# Security documentation index

**Purpose:** keep security maintainable as the codebase grows to hundreds of thousands / millions of lines.

**Rule of structure:** one concern → one module → one workflow → one doc page. Do not merge phases.

| Doc | Concern |
|-----|---------|
| [00_DEVELOPER_RULES.md](00_DEVELOPER_RULES.md) | **Strict rules for every developer** (mandatory) |
| [01_ARCHITECTURE.md](01_ARCHITECTURE.md) | Separation of concerns, ownership boundaries |
| [02_PHASE_MAP.md](02_PHASE_MAP.md) | Phase 1–4 map: workflow ↔ engine ↔ gate |
| [03_MAINTENANCE.md](03_MAINTENANCE.md) | How to add routes, engines, policies without breaking isolation |
| [04_IDOR_OWNERSHIP.md](04_IDOR_OWNERSHIP.md) | `lumen/api/ownership.py` + route wiring checklist |
| ../29_PHASES_FULL_AUDIT.md | Full engine audit matrix |
| ../26_SECURITY_ENGINES.md | Engine catalog |
| ../27_PHASE3_SUPPLY_CHAIN.md | Phase 3 detail |
| ../28_PHASE4_POLICY_AS_CODE.md | Phase 4 detail |

## Workflows (do not collapse into one file)

| Workflow | Phase | Gate job name |
|----------|-------|----------------|
| `.github/workflows/security.yml` | 1 | `Phase-1 security gate` |
| `.github/workflows/dast-zap.yml` | 2 | `Phase-2 DAST gate` |
| `.github/workflows/supply-chain.yml` | 3 | `Phase-3 admission gate` |
| `.github/workflows/policy-as-code.yml` | 4 | `Phase-4 policy gate` |
| `.github/workflows/security-attack.yml` | 2 support | offensive regression |

## Verified locally (unit layer)

```bash
PYTHONPATH=. pytest tests/test_security_idor_dast.py \
  tests/test_security_baseline.py \
  tests/test_security_attack_surface.py \
  tests/test_welcome_credits.py -q
PYTHONPATH=. python scripts/security/security_baseline_check.py --strict
```

CI live ZAP / Grype / OSV run on GitHub runners (Docker engines).
