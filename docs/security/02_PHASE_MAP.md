# Phase map — one phase, one workflow, one gate

## Phase 1 — Static & secrets
- **Workflow:** `.github/workflows/security.yml`
- **Gate:** `Phase-1 security gate`
- **Engines:** Gitleaks, pip-audit, Bandit, Semgrep, CodeQL, Trivy (fs+config), Scorecard
- **Product tests:** credits privilege pytest, `security_baseline_check.py`

## Phase 2 — Dynamic & tenant isolation
- **Workflow:** `.github/workflows/dast-zap.yml`
- **Gate:** `Phase-2 DAST gate`
- **Engines:** OWASP ZAP (`ghcr.io/zaproxy/zaproxy:stable`) baseline + API + auth
- **Product:** IDOR pytest, `live_idor_http.py`, `lumen/api/ownership.py`
- **Support:** `security-attack.yml`

## Phase 3 — Supply chain
- **Workflow:** `.github/workflows/supply-chain.yml`
- **Gate:** `Phase-3 admission gate`
- **Engines:** Dependency Review, OSV, Syft, Grype, Trivy secrets/image, Cosign, attest

## Phase 4 — Policy-as-code
- **Workflow:** `.github/workflows/policy-as-code.yml`
- **Gate:** `Phase-4 policy gate`
- **Engines:** Hadolint, actionlint, ShellCheck, Checkov, KICS, Conftest/OPA, Trivy config

## GitHub branch protection (platform, not a scanner)

Template: `.github/rulesets/main-protection.json`  
Require the four gate job names above on `main`.
