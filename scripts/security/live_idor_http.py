#!/usr/bin/env python3
"""Live IDOR against a *running* HTTP API using two seeded tenant keys.

Fail-closed: any unexpected 2xx cross-tenant is exit 1.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

SEED = Path(os.environ.get("DAST_SEED_FILE", "/tmp/dast-tenants.json"))


def _req(base: str, method: str, path: str, headers: dict, body: dict | None = None):
    data = None
    hdrs = dict(headers)
    if body is not None:
        data = json.dumps(body).encode()
        hdrs["Content-Type"] = "application/json"
    r = urllib.request.Request(base + path, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, (e.read().decode() if e.fp else "")


def main() -> int:
    if not SEED.exists():
        print("missing seed file", SEED)
        return 2
    seed = json.loads(SEED.read_text(encoding="utf-8"))
    base = seed["base"]
    a, b = seed["tenant_a"], seed["tenant_b"]
    failures = []

    def auth(t):
        return {"Authorization": f"Bearer {t['key']}"}

    # 1) me isolation
    for t, other in ((a, b), (b, a)):
        code, raw = _req(base, "GET", "/v1/me", auth(t))
        if code != 200:
            failures.append(f"me_{t['name']}_{code}")
            continue
        if other["id"] in raw:
            failures.append(f"me_leak_{t['name']}")
        if t["id"] not in raw:
            failures.append(f"me_missing_self_{t['name']}")

    # 2) admin with tenant key
    for t in (a, b):
        for path in (
            f"/v1/admin/credits/{a['id']}/overview",
            f"/v1/admin/credits/{b['id']}/overview",
        ):
            code, _ = _req(
                base,
                "GET",
                path,
                {**auth(t), "X-Admin-Token": t["key"]},
            )
            if 200 <= code < 300:
                failures.append(f"admin_with_tenant_key {t['name']} {path} {code}")

    # 3) spoof body on generate
    code, raw = _req(
        base,
        "POST",
        "/v1/generate",
        auth(a),
        {"description": "بوت اختبار عزل المستأجرين", "tenant_id": b["id"]},
    )
    if code != 403:
        failures.append(f"generate_spoof_expected_403_got_{code}")

    # 4) credits routes no cross leak
    for path in (
        "/v1/me/credits/overview",
        "/v1/me/credits/ledger",
        "/v1/usage",
        "/v1/invoices",
        "/v1/dashboard",
        "/v1/jobs",
    ):
        code, raw = _req(base, "GET", path, auth(a))
        if code != 200:
            # some may 402/503 without billing backend — not IDOR fail unless 2xx leak
            if 200 <= code < 300 and b["id"] in raw:
                failures.append(f"leak_{path}")
            continue
        if b["id"] in raw:
            failures.append(f"leak_{path}")

    # 5) unauth
    for path in ("/v1/me", "/v1/generate", f"/v1/admin/credits/{a['id']}/overview"):
        code, _ = _req(base, "GET", path, {})
        if 200 <= code < 300:
            failures.append(f"unauth_2xx_{path}_{code}")

    report = {"ok": not failures, "failures": failures, "tenants": [a["id"], b["id"]]}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
