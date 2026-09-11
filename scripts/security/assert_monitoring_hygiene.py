#!/usr/bin/env python3
"""Phase E continuous verification: Dependabot + gitleaks + alert wiring."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def check(name: str, ok: bool, detail: str, fails: list) -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    if not ok:
        fails.append(name)


def main() -> int:
    fails: list[str] = []
    dep = ROOT / ".github/dependabot.yml"
    check("dependabot.yml", dep.is_file(), "exists", fails)
    if dep.is_file():
        txt = dep.read_text(encoding="utf-8")
        check("dependabot.pip", 'package-ecosystem: "pip"' in txt, "pip ecosystem", fails)
        check("dependabot.schedule", "schedule:" in txt, "has schedule", fails)

    gl = ROOT / ".gitleaks.toml"
    check("gitleaks.toml", gl.is_file(), "exists", fails)

    sec = ROOT / ".github/workflows/security.yml"
    check("security.yml", sec.is_file(), "exists", fails)
    if sec.is_file():
        st = sec.read_text(encoding="utf-8")
        check("ci.gitleaks", "gitleaks" in st.lower(), "gitleaks job", fails)
        check("ci.schedule", "schedule:" in st, "scheduled runs", fails)

    weekly = ROOT / ".github/workflows/security-review-weekly.yml"
    check("weekly_review", weekly.is_file(), "security-review-weekly.yml", fails)

    alerts = (ROOT / "lumen/platform/security_alerts.py").read_text(encoding="utf-8")
    events = (ROOT / "lumen/platform/security_events.py").read_text(encoding="utf-8")
    check("alerts.admin", "auth.admin_rejected" in alerts, "admin watched", fails)
    check("alerts.spoof", "idor.identity_spoof" in alerts, "spoof watched", fails)
    check("alerts.webhook", "webhook.stripe_signature_failed" in alerts, "webhook watched", fails)
    check("events.dispatch", "dispatch_alert" in events, "emit dispatch", fails)
    check("events.metrics", "record_security_event" in events, "emit metrics", fails)

    billing = (ROOT / "lumen/api/routes/billing.py").read_text(encoding="utf-8")
    github = (ROOT / "lumen/api/routes/github_webhooks.py").read_text(encoding="utf-8")
    check("stripe.emit", "webhook.stripe_signature_failed" in billing, "stripe", fails)
    check("github.emit", "webhook.github_signature_failed" in github, "github", fails)

    auth = (ROOT / "lumen/api/auth.py").read_text(encoding="utf-8")
    check("admin.redis_fail_closed", "admin_rate_limit_unavailable" in auth, "redis", fails)

    print("---")
    print(f"failures={len(fails)} {fails}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
