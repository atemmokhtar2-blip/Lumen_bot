"""Error intelligence contracts."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional


@dataclass
class StackFrame:
    file: str = ""
    line: int = 0
    function: str = ""
    code: str = ""


@dataclass
class TracebackInfo:
    exception_type: str = ""
    exception_message: str = ""
    frames: list[StackFrame] = field(default_factory=list)
    location: str = ""
    raw: str = ""


@dataclass
class LogEvent:
    level: str = "ERROR"
    message: str = ""
    source: str = ""
    line_no: int = 0


@dataclass
class DiagnosedError:
    category: str = "unknown"
    severity: str = "error"
    title: str = ""
    summary_ar: str = ""
    exception_type: str = ""
    exception_message: str = ""
    location: str = ""
    missing_module: str = ""
    suggested_package: str = ""
    suggested_action: str = ""
    confidence: float = 0.5
    traceback: Optional[TracebackInfo] = None
    evidence: list[str] = field(default_factory=list)


@dataclass
class ErrorContract:
    ok: bool = True
    phase: str = ""
    exit_code: int | None = None
    events: list[LogEvent] = field(default_factory=list)
    errors: list[DiagnosedError] = field(default_factory=list)
    primary: Optional[DiagnosedError] = None
    healable: bool = False
    heal_packages: list[str] = field(default_factory=list)
    auto_actions: list[str] = field(default_factory=list)
    raw_install_log_tail: str = ""
    raw_run_log_tail: str = ""
    meta: dict[str, Any] = field(default_factory=dict)
