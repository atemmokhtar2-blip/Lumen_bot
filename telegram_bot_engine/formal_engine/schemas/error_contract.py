"""ErrorContract — structured understanding of runtime / install logs."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


ErrorCategory = Literal[
    "dependency",
    "syntax",
    "config",
    "telegram_api",
    "telegram_conflict",
    "runtime",
    "network",
    "permission",
    "timeout",
    "conflict",
    "unknown",
]

SuggestedAction = Literal[
    "install_package",
    "fix_requirements",
    "set_env",
    "fix_syntax",
    "fix_code",
    "retry",
    "check_token",
    "delete_webhook",
    "check_network",
    "escalate",
    "none",
]


class StackFrame(StrictModel):
    file: str = ""
    line: int = 0
    function: str = ""
    code: str = ""


class TracebackInfo(StrictModel):
    exception_type: str = ""
    exception_message: str = ""
    frames: list[StackFrame] = Field(default_factory=list)
    raw: str = ""

    @property
    def location(self) -> str:
        if not self.frames:
            return ""
        f = self.frames[-1]
        name = f.file.rsplit("/", 1)[-1] if f.file else "?"
        return f"{name}:{f.line}" if f.line else name


class LogEvent(StrictModel):
    level: str = "INFO"  # DEBUG|INFO|WARNING|ERROR|CRITICAL
    message: str = ""
    source: str = ""  # install | run | system
    line_no: int = 0


class DiagnosedError(StrictModel):
    """One understood error with category, evidence, and recommended action."""

    category: ErrorCategory = "unknown"
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    title: str = ""
    summary_ar: str = ""
    exception_type: str = ""
    exception_message: str = ""
    location: str = ""  # file:line
    missing_module: str = ""
    suggested_package: str = ""
    suggested_action: SuggestedAction = "none"
    confidence: float = 0.5
    evidence: list[str] = Field(default_factory=list)
    traceback: TracebackInfo | None = None


class ErrorContract(StrictModel):
    """
    Contract produced by Error Intelligence from raw logs.

    This is the foundation for:
      - LiveRunner auto-heal decisions
      - User-facing health reports
      - Future hosting / deployment monitoring
    """

    schema_version: str = "1.0"
    ok: bool = True
    phase: str = ""  # install | run | validate | unknown
    exit_code: int | None = None

    events: list[LogEvent] = Field(default_factory=list)
    errors: list[DiagnosedError] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    primary: DiagnosedError | None = None
    healable: bool = False
    heal_packages: list[str] = Field(default_factory=list)
    auto_actions: list[str] = Field(default_factory=list)

    raw_install_log_tail: str = ""
    raw_run_log_tail: str = ""
    notes: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)

    def to_user_summary(self) -> str:
        if self.ok and not self.errors:
            return "✅ لا توجد أخطاء مفهومة في اللوج."
        lines: list[str] = []
        if self.primary:
            p = self.primary
            icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(p.severity, "⚪")
            lines.append(f"{icon} *{p.title or p.category}*")
            if p.summary_ar:
                lines.append(f"• {p.summary_ar}")
            if p.location:
                lines.append(f"• الموقع: `{p.location}`")
            if p.exception_type:
                lines.append(f"• النوع: `{p.exception_type}`")
            if p.suggested_package:
                lines.append(f"• حزمة مقترحة: `{p.suggested_package}`")
            if p.suggested_action and p.suggested_action != "none":
                lines.append(f"• إجراء: `{p.suggested_action}`")
            lines.append(f"• ثقة التشخيص: {p.confidence:.0%}")
        if len(self.errors) > 1:
            lines.append(f"• أخطاء إضافية: {len(self.errors) - 1}")
        if self.healable and self.heal_packages:
            lines.append(f"• قابل للإصلاح التلقائي (حزم): {', '.join(self.heal_packages)}")
        if self.auto_actions:
            lines.append(f"• إجراءات ذاتية: {', '.join(self.auto_actions)}")
        return "\n".join(lines) if lines else "❌ أخطاء غير مصنّفة في اللوج."


__all__ = [
    "ErrorContract",
    "DiagnosedError",
    "TracebackInfo",
    "StackFrame",
    "LogEvent",
    "ErrorCategory",
    "SuggestedAction",
]
