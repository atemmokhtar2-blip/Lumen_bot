"""
LiveRunner — real dependency install + bot process execution + error capture.

Install strategy (robust):
  1) try venv + ensure pip works
  2) if venv/pip broken → pip install --target .tbe_deps (isolated)
  3) surface real pip ERROR lines to the user (no opaque "pip install failed")
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import ast


@dataclass
class LiveRunReport:
    ok: bool
    phase: str
    message: str
    bot_username: str = ""
    bot_id: int | None = None
    install_log: str = ""
    run_log: str = ""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    pid: int | None = None
    entry_point: str = ""
    venv_path: str = ""
    duration_ms: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)

    def to_user_text(self) -> str:
        icon = "✅" if self.ok else "❌"
        lines = [f"{icon} *تشغيل حي — {self.phase}*", f"• {self.message}", "• build: `live-fix-v4`"]
        # Surface auto-heal hints clearly for the user
        hints = []
        for w in (self.warnings or []):
            if isinstance(w, str) and w.startswith("auto_heal:"):
                hints.append(w.replace("auto_heal:", "", 1)[:80])
        for h in (self.details or {}).get("auto_healed_packages") or []:
            if isinstance(h, str) and h.startswith("user_hint:"):
                hints.append(h.replace("user_hint:", "", 1))
        if hints:
            lines.append("• إصلاح تلقائي:")
            for h in hints[:6]:
                lines.append(f"  ✓ {h}")
        if self.bot_username:
            lines.append(f"• البوت: @{self.bot_username}")
        if self.entry_point:
            lines.append(f"• نقطة الدخول: `{self.entry_point}`")
        if self.details.get("install_mode"):
            lines.append(f"• وضع التثبيت: `{self.details['install_mode']}`")
        if self.errors:
            lines.append("• أخطاء:")
            for e in self.errors[:8]:
                lines.append(f"  - `{e[:220]}`")
        # Error Intelligence diagnosis (foundation for hosting health reports)
        if not self.ok:
            try:
                from ..error_intelligence import analyze_logs
                contract = analyze_logs(
                    run_log=self.run_log or "",
                    install_log=self.install_log or "",
                    phase=self.phase or "",
                    extra_errors=list(self.errors or []),
                )
                if contract.primary:
                    lines.append("• تشخيص:")
                    lines.append(contract.to_user_summary())
            except Exception:
                pass
        if self.warnings:
            lines.append("• تحذيرات:")
            for w in self.warnings[:4]:
                lines.append(f"  - {w[:160]}")
        # always show install tail on install failure
        if self.phase == "install" and self.install_log:
            tail = self.install_log.strip()[-800:]
            if tail:
                lines.append(f"• لوج pip:\n```\n{tail}\n```")
        elif self.run_log and not self.ok:
            tail = self.run_log.strip()[-500:]
            if tail:
                lines.append(f"• لوج:\n```\n{tail}\n```")
        if self.duration_ms:
            lines.append(f"• الزمن: {self.duration_ms:.0f}ms")
        return "\n".join(lines)


