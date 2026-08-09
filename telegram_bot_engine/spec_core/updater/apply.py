"""Apply researched dependency updates into the zero-AI coding engine safely.

Only auto-updates dependency pins and a machine-readable update stamp.
Does not rewrite business logic from arbitrary web pages.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .research import ResearchReport, research_stack

ROOT = Path(__file__).resolve().parents[1]  # spec_core
CODING = ROOT / "coding.py"
STAMP = ROOT / "updater" / "last_update.json"


@dataclass
class ApplyResult:
    ok: bool
    changed: bool = False
    requirements_line: str = ""
    notes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    report: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "changed": self.changed,
            "requirements_line": self.requirements_line,
            "notes": list(self.notes),
            "errors": list(self.errors),
            "report": self.report,
        }


def _build_emit_fn(requirements: list[str]) -> str:
    body_lines = []
    for line in requirements:
        body_lines.append(f"        {(line + chr(10))!r}")
    inner = "\n".join(body_lines) if body_lines else '        "python-telegram-bot>=21.0,<23\\n"'
    return (
        "def _emit_requirements() -> str:\n"
        "    return (\n"
        f"{inner}\n"
        "    )\n"
    )


def apply_research(report: ResearchReport | None = None, *, write: bool = True) -> ApplyResult:
    report = report or research_stack()
    result = ApplyResult(ok=report.ok, report=report.to_dict())
    if not CODING.exists():
        result.ok = False
        result.errors.append("coding_py_missing")
        return result

    reqs = report.recommended_requirements or [
        "python-telegram-bot>=21.0,<23",
        "python-dotenv>=1.0.0",
    ]
    result.requirements_line = " | ".join(reqs)
    text = CODING.read_text(encoding="utf-8")
    new_fn = _build_emit_fn(reqs)

    pattern = re.compile(
        r"def _emit_requirements\(\) -> str:\n(?:.*?\n)*?(?=\ndef )",
        re.MULTILINE,
    )
    if not pattern.search(text):
        result.errors.append("emit_requirements_not_found")
        result.ok = False
        return result

    new_text, n = pattern.subn(new_fn + "\n", text, count=1)
    if n != 1:
        result.errors.append("emit_requirements_replace_failed")
        result.ok = False
        return result

    result.changed = new_text != text
    result.notes.append(f"ptb_pin={reqs[:1]}")
    if write and result.changed:
        CODING.write_text(new_text, encoding="utf-8")
        result.notes.append("coding.py_requirements_updated")
    if write:
        STAMP.parent.mkdir(parents=True, exist_ok=True)
        STAMP.write_text(
            json.dumps(
                {
                    "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "changed": result.changed,
                    "recommended_requirements": reqs,
                    "telegram_api_hints": report.telegram_api_hints[:10],
                    "ptb_hints": report.ptb_hints[:10],
                    "packages": [
                        {"name": p.name, "latest": p.latest_version, "error": p.error}
                        for p in report.packages
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        result.notes.append(f"stamp_written:{STAMP}")
    return result


def run_update(*, write: bool = True) -> ApplyResult:
    return apply_research(research_stack(), write=write)


__all__ = ["ApplyResult", "apply_research", "run_update"]
