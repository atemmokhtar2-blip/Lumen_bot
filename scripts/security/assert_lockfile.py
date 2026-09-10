#!/usr/bin/env python3
"""Fail if requirements.txt pins are missing from requirements.lock (Phase D)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REQ = ROOT / "requirements.txt"
LOCK = ROOT / "requirements.lock"

_PIN = re.compile(r"^([A-Za-z0-9_.-]+)\s*==\s*([^\s#]+)")


def _pins(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("-"):
            continue
        m = _PIN.match(s)
        if m:
            out[m.group(1).lower().replace("_", "-")] = m.group(2).strip()
    return out


def main() -> int:
    if not REQ.exists():
        print("FAIL: requirements.txt missing")
        return 1
    if not LOCK.exists():
        print("FAIL: requirements.lock missing — run pip-compile")
        return 1
    req = _pins(REQ)
    lock = _pins(LOCK)
    missing = []
    mismatched = []
    for name, ver in req.items():
        if name not in lock:
            missing.append(f"{name}=={ver}")
        elif lock[name] != ver:
            mismatched.append(f"{name}: txt={ver} lock={lock[name]}")
    if missing or mismatched:
        print("FAIL: requirements.lock out of sync with requirements.txt")
        for m in missing:
            print(f"  missing in lock: {m}")
        for m in mismatched:
            print(f"  version mismatch: {m}")
        return 1
    print(f"OK: {len(req)} pinned packages present in requirements.lock")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
