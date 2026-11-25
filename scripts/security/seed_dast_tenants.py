#!/usr/bin/env python3
"""Seed two tenants against a *running* API for authenticated DAST + live IDOR.

Writes JSON:
  { "admin": "...", "tenant_a": {"id","key"}, "tenant_b": {"id","key"} }
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = os.environ.get("DAST_BASE_URL", "http://127.0.0.1:8765").rstrip("/")
ADMIN = (os.environ.get("PLATFORM_ADMIN_TOKEN") or "").strip()
OUT = Path(os.environ.get("DAST_SEED_FILE", "/tmp/dast-tenants.json"))


def _req(method: str, path: str, *, headers: dict | None = None, body: dict | None = None):
    data = None
    hdrs = dict(headers or {})
    if body is not None:
        data = json.dumps(body).encode()
        hdrs.setdefault("Content-Type", "application/json")
    r = urllib.request.Request(BASE + path, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raw = e.read().decode() if e.fp else ""
        try:
            payload = json.loads(raw or "{}")
        except Exception:
            payload = {"raw": raw[:300]}
        return e.code, payload


def main() -> int:
    if not ADMIN:
        print("missing PLATFORM_ADMIN_TOKEN; provide an ephemeral admin credential")
        return 2
    # This file contains temporary tenant API keys.
    os.umask(0o077)
    # Create tenants via admin API
    tenants = []
    for name in ("DastLiveA", "DastLiveB"):
        code, body = _req(
            "POST",
            "/v1/tenants",
            headers={"X-Admin-Token": ADMIN},
            body={"name": name, "plan_id": "free"},
        )
        if code not in (200, 201) or not body.get("api_key"):
            print(json.dumps({"ok": False, "step": "create", "name": name, "code": code, "error": body.get("error", "tenant_create_failed")}, indent=2))
            return 1
        tenants.append(
            {
                "id": body.get("tenant", {}).get("tenant_id") or body.get("tenant_id"),
                "key": body["api_key"],
                "name": name,
            }
        )

    a, b = tenants[0], tenants[1]
    # Sanity: each /v1/me
    for t in (a, b):
        code, body = _req("GET", "/v1/me", headers={"Authorization": f"Bearer {t['key']}"})
        if code != 200 or body.get("tenant", {}).get("tenant_id") != t["id"]:
            print(json.dumps({"ok": False, "step": "me", "tenant_id": t["id"], "code": code, "error": body.get("error", "tenant_auth_failed")}, indent=2))
            return 1

    payload = {"ok": True, "base": BASE, "tenant_a": a, "tenant_b": b}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.chmod(OUT, 0o600)
    print(json.dumps({"ok": True, "tenant_ids": [a["id"], b["id"]]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
