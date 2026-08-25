# Dependency pinning policy (Lumen)

## Source of truth

| File | Role |
|------|------|
| `requirements.txt` | Direct runtime deps, exact `==` pins |
| `requirements.lock` | Full transitive lock from `pip-compile` |
| `requirements-security.txt` | CI-only tools (bandit, pip-audit, semgrep) |

## Install (production)

```bash
pip install -r requirements.lock
```

## Bump procedure

1. Edit `requirements.txt` (direct pins only).
2. `pip-compile -o requirements.lock requirements.txt`
3. `pip-audit -r requirements.lock`
4. Run CI supply-chain workflow; commit both files together.

Never deploy production from unpinned `>=` ranges.
