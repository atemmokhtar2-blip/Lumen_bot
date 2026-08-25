#!/usr/bin/env python3
"""Parse ZAP JSON report — fail on HIGH or MEDIUM (world-class gate)."""
from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: zap_fail_on_severity.py report.json")
        return 2
    path = Path(sys.argv[1])
    if not path.exists():
        print("missing report", path)
        return 2
    data = json.loads(path.read_text(encoding="utf-8"))
    # ZAP JSON structure varies (traditional vs site tree)
    alerts = []
    if isinstance(data, dict):
        for site in data.get("site") or []:
            for a in site.get("alerts") or []:
                alerts.append(a)
        if not alerts and "alerts" in data:
            alerts = list(data["alerts"] or [])
    bad = []
    for a in alerts:
        risk = str(a.get("risk") or a.get("riskcode") or "").lower()
        name = a.get("alert") or a.get("name") or "?"
        # riskcode: 3=high 2=medium 1=low 0=info
        code = str(a.get("riskcode", ""))
        if risk in {"high", "3"} or code == "3":
            bad.append(("HIGH", name))
        elif risk in {"medium", "2"} or code == "2":
            bad.append(("MEDIUM", name))
    print(json.dumps({"alert_count": len(alerts), "blocking": bad}, indent=2))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
