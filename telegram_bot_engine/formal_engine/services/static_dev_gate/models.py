"""Shared models for StaticDevGate — extensible foundation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import ast


@dataclass
class StaticFinding:
    severity: str  # error | warning | info
    code: str
    file: str
    message_ar: str
    lineno: int = 0
    rule_id: str = ""
    evidence: str = ""

    def key(self) -> str:
        return f"{self.rule_id}|{self.code}|{self.file}|{self.lineno}|{self.message_ar[:40]}"


@dataclass
class StaticReport:
    ok: bool
    findings: list[StaticFinding] = field(default_factory=list)
    files_checked: int = 0
    errors: int = 0
    warnings: int = 0
    infos: int = 0
    rules_run: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_user_text(self) -> str:
        icon = "✅" if self.ok else "❌"
        lines = [
            f"{icon} *بوابة التحقق الاستاتيكي (StaticDevGate)*",
            f"• ملفات: {self.files_checked} | أخطاء: {self.errors} | "
            f"تحذيرات: {self.warnings} | معلومات: {self.infos}",
        ]
        if self.rules_run:
            lines.append(f"• قواعد شغّالة: {len(self.rules_run)}")
        for f in self.findings[:30]:
            mark = {"error": "🔴", "warning": "🟡", "info": "🔵"}.get(f.severity, "•")
            loc = f"`{f.file}`" + (f":{f.lineno}" if f.lineno else "")
            rid = f.rule_id or f.code
            lines.append(f"{mark} [{rid}] {loc} — {f.message_ar}")
        if not self.findings:
            lines.append("• لا ملاحظات — الهيكل سليم رمزياً.")
        return "\n".join(lines)

    @staticmethod
    def from_findings(
        findings: list[StaticFinding],
        files_checked: int,
        rules_run: list[str] | None = None,
        meta: dict[str, Any] | None = None,
    ) -> "StaticReport":
        # dedupe
        seen: set[str] = set()
        uniq: list[StaticFinding] = []
        for f in findings:
            k = f.key()
            if k in seen:
                continue
            seen.add(k)
            uniq.append(f)
        errors = sum(1 for f in uniq if f.severity == "error")
        warnings = sum(1 for f in uniq if f.severity == "warning")
        infos = sum(1 for f in uniq if f.severity == "info")
        return StaticReport(
            ok=errors == 0,
            findings=uniq,
            files_checked=files_checked,
            errors=errors,
            warnings=warnings,
            infos=infos,
            rules_run=list(rules_run or []),
            meta=dict(meta or {}),
        )


@dataclass
class ModuleInfo:
    path: str  # relative
    tree: ast.AST | None = None
    source: str = ""
    syntax_error: str = ""
    functions: set[str] = field(default_factory=set)
    classes: set[str] = field(default_factory=set)
    imports: list[tuple[str, int]] = field(default_factory=list)  # module, lineno
    # command, handler_name, lineno, style
    command_regs: list[tuple[str, str, int, str]] = field(default_factory=list)


@dataclass
class AnalysisContext:
    """
    Single shared snapshot of the project for all rules.
    Build once → run N rules without re-parsing.
    """
    root: str
    modules: dict[str, ModuleInfo] = field(default_factory=dict)
    all_functions: set[str] = field(default_factory=set)
    all_classes: set[str] = field(default_factory=set)
    local_module_names: set[str] = field(default_factory=set)
    focus_only: bool = False
    expected_commands: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def module_list(self) -> list[ModuleInfo]:
        return list(self.modules.values())
