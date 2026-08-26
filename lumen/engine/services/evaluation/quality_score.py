"""Project quality score for Phase D hard bench (0..1).

Checks structure, syntax, platform fidelity, and feature keyword coverage —
no mock metrics.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any


def score_generated_project(
    root: str | Path,
    *,
    platform: str = "telegram",
    spec: str = "",
) -> dict[str, Any]:
    root_p = Path(root)
    checks: dict[str, bool] = {}
    details: dict[str, Any] = {}

    checks["has_main"] = (root_p / "main.py").is_file()
    checks["has_handlers"] = (root_p / "app" / "handlers.py").is_file() or any(
        (root_p / "app").glob("*.py")
    ) if (root_p / "app").is_dir() else False
    checks["has_requirements"] = (root_p / "requirements.txt").is_file()
    checks["has_readme"] = (root_p / "README.md").is_file()
    checks["has_env_example"] = (root_p / ".env.example").is_file()

    py_files = list(root_p.rglob("*.py"))
    details["py_files"] = len(py_files)
    syn_ok = 0
    syn_fail = 0
    for py in py_files[:40]:
        try:
            ast.parse(py.read_text(encoding="utf-8", errors="replace"), filename=str(py))
            syn_ok += 1
        except SyntaxError:
            syn_fail += 1
    checks["all_syntax_ok"] = syn_fail == 0 and syn_ok > 0
    details["syntax_ok"] = syn_ok
    details["syntax_fail"] = syn_fail

    blob = ""
    for py in py_files[:20]:
        try:
            blob += py.read_text(encoding="utf-8", errors="replace").lower()
        except OSError:
            pass
    plat = (platform or "telegram").lower()
    if plat == "discord":
        checks["platform_marker"] = "discord" in blob
    elif plat == "whatsapp":
        checks["platform_marker"] = "whatsapp" in blob or "graph.facebook" in blob
    elif plat == "web":
        checks["platform_marker"] = "httpserver" in blob.replace("_", "").lower() or "http" in blob
    else:
        checks["platform_marker"] = "telegram" in blob or "bot_token" in blob

    # feature keywords from spec
    tokens = [t for t in re.findall(r"[a-zA-Z\u0600-\u06FF]{4,}", (spec or "").lower()) if t not in {
        "with", "that", "this", "from", "have", "want", "need", "bot", "using", "please",
        "علي", "هذا", "هذه", "بوت", "عايز", "أريد",
    }]
    tokens = list(dict.fromkeys(tokens))[:12]
    hit = 0
    for t in tokens:
        if t in blob or t in (root_p / "README.md").read_text(encoding="utf-8", errors="replace").lower() if (root_p / "README.md").is_file() else "":
            hit += 1
    feat_ratio = (hit / len(tokens)) if tokens else 0.5
    checks["feature_coverage_half"] = feat_ratio >= 0.25
    details["feature_tokens"] = tokens
    details["feature_hits"] = hit
    details["feature_ratio"] = round(feat_ratio, 3)

    # file count pressure (harder projects have more modules)
    checks["multi_file"] = len(py_files) >= 3
    details["checks"] = dict(checks)

    weights = {
        "has_main": 0.15,
        "has_handlers": 0.1,
        "has_requirements": 0.1,
        "has_readme": 0.05,
        "has_env_example": 0.05,
        "all_syntax_ok": 0.25,
        "platform_marker": 0.15,
        "feature_coverage_half": 0.1,
        "multi_file": 0.05,
    }
    score = sum(weights[k] for k, v in checks.items() if v and k in weights)
    return {
        "ok": score >= 0.7 and checks.get("all_syntax_ok", False),
        "score": round(score, 4),
        "checks": checks,
        "details": details,
        "engine": "quality_score",
    }


__all__ = ["score_generated_project"]
