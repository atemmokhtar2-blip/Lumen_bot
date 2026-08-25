# Security Policy

## Supported versions

| Branch | Supported |
|--------|-----------|
| `main` | ✅ |

## Reporting a vulnerability

Do **not** open a public issue for security vulnerabilities.

Email / contact the maintainers privately with:
- description and impact
- reproduction steps
- affected endpoints or modules (e.g. `/v1/admin/credits/*`, `execute_tool`)

We aim to acknowledge within 72 hours.

## Automated controls

See [docs/25_SECURITY_MONITORING.md](docs/25_SECURITY_MONITORING.md).

Pipeline includes: Gitleaks, pip-audit, Bandit, Semgrep, CodeQL, Trivy, OpenSSF Scorecard,
credits privilege tests, daily promo/drift monitor, static security baseline.
