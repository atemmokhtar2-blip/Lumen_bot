# Dependency pinning policy (Lumen)
#
# - requirements.txt uses exact == pins for runtime packages.
# - requirements-security.txt remains tool-only (bandit, pip-audit, semgrep).
# - After any pin bump: run `pip-audit -r requirements.txt` and CI supply-chain workflow.
# - Do not deploy production with unpinned >= ranges.
