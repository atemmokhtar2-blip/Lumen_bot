"""Policy-aware tool runner — Phase 3 hardened.

Every tool call is checked against ToolSpec.enabled + env overrides.
Shell/web never run unless CLINE_ALLOW_SHELL / CLINE_ALLOW_WEB.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from .tools import ToolSpec, build_default_tools

logger = logging.getLogger(__name__)


class ToolRunner:
    def __init__(self, tools: dict[str, ToolSpec] | None = None) -> None:
        self.tools = tools or build_default_tools()
        self.history: list[dict[str, Any]] = []

    def _allowed(self, name: str) -> tuple[bool, str]:
        tool = self.tools.get(name)
        if tool is None:
            return False, "unknown_tool"
        if not tool.enabled:
            return False, "tool_disabled"
        if name == "run_shell":
            if (os.getenv("CLINE_ALLOW_SHELL") or "0").strip().lower() not in {
                "1",
                "true",
                "yes",
                "on",
            }:
                return False, "CLINE_ALLOW_SHELL required"
        if name == "fetch_web":
            if (os.getenv("CLINE_ALLOW_WEB") or "0").strip().lower() not in {
                "1",
                "true",
                "yes",
                "on",
            }:
                return False, "CLINE_ALLOW_WEB required"
        return True, "ok"

    def run(self, name: str, **kwargs: Any) -> dict[str, Any]:
        ok, reason = self._allowed(name)
        entry: dict[str, Any] = {"tool": name, "allowed": ok, "reason": reason}
        if not ok:
            entry["result"] = {"ok": False, "error": reason}
            self.history.append(entry)
            logger.warning("tool blocked %s: %s", name, reason)
            return entry["result"]
        tool = self.tools[name]
        try:
            result = tool.execute(**kwargs)
            if not isinstance(result, dict):
                result = {"ok": True, "data": result}
            entry["result"] = result
            self.history.append(entry)
            return result
        except Exception as exc:
            err = {"ok": False, "error": f"{type(exc).__name__}:{exc}"}
            entry["result"] = err
            self.history.append(entry)
            logger.exception("tool %s failed", name)
            return err


__all__ = ["ToolRunner"]
