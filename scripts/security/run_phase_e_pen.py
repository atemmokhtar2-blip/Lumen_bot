#!/usr/bin/env python3
"""Run Phase E penetration + monitoring hygiene; exit 1 on any failure."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    rc = 0
    print("== assert_monitoring_hygiene ==")
    p1 = subprocess.run([sys.executable, str(ROOT / "scripts/security/assert_monitoring_hygiene.py")])
    if p1.returncode != 0:
        rc = 1
    print("== pytest Phase E pen ==")
    p2 = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(ROOT / "tests/test_phase_e_monitoring_pen.py"),
            "-q",
            "--tb=line",
        ],
        cwd=str(ROOT),
    )
    if p2.returncode != 0:
        rc = 1
    # Fail if any skipped core tests (pytest reports skipped in summary — re-run with strict)
    p3 = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(ROOT / "tests/test_phase_e_monitoring_pen.py"),
            "-q",
            "--tb=line",
            "-W",
            "error::pytest.PytestUnhandledThreadExceptionWarning",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    out = (p3.stdout or "") + (p3.stderr or "")
    print(out)
    if "skipped" in out.lower() and "passed" in out.lower():
        # allow zero skips preferred
        if "ss" in out or " skipped" in out:
            # count skips
            import re
            m = re.search(r"(\d+) skipped", out)
            if m and int(m.group(1)) > 0:
                print("FAIL: Phase E tests must not skip core probes")
                rc = 1
    if p3.returncode != 0:
        rc = 1
    print("phase_e_result", "FAIL" if rc else "OK")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
