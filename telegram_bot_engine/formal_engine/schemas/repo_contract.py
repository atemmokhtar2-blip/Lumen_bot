"""RepoContract — structured understanding of an existing repository."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class FileEntry(StrictModel):
    path: str
    size: int = 0
    kind: str = "other"  # python | config | docs | test | other


class DetectedCommand(StrictModel):
    name: str
    source_file: str = ""
    evidence: str = ""


class DetectedHandler(StrictModel):
    kind: str  # command | callback | message | conversation
    name: str = ""
    source_file: str = ""


class EntryPoint(StrictModel):
    path: str
    reason: str = ""


class RepoContract(StrictModel):
    """What we understood about a cloned repository."""

    schema_version: str = "1.0"
    root_path: str
    repo_name: str = ""
    remote_url: str = ""

    languages: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    entry_points: list[EntryPoint] = Field(default_factory=list)
    commands: list[DetectedCommand] = Field(default_factory=list)
    handlers: list[DetectedHandler] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)

    file_count: int = 0
    python_file_count: int = 0
    top_files: list[FileEntry] = Field(default_factory=list)
    top_dirs: list[str] = Field(default_factory=list)

    is_telegram_bot: bool = False
    confidence: float = 0.0
    summary: str = ""
    notes: list[str] = Field(default_factory=list)
    raw_stats: dict[str, Any] = Field(default_factory=dict)

    def to_user_summary(self) -> str:
        lines = [
            f"📦 *فهم المستودع:* `{self.repo_name or self.root_path}`",
            f"• ملفات: {self.file_count} (Python: {self.python_file_count})",
            f"• لغات: {', '.join(self.languages) or '—'}",
            f"• أطر: {', '.join(self.frameworks) or '—'}",
            f"• بوت تليجرام: {'نعم' if self.is_telegram_bot else 'لا/غير مؤكد'}",
            f"• ثقة الفهم: {self.confidence:.0%}",
        ]
        if self.entry_points:
            eps = ", ".join(f"`{e.path}`" for e in self.entry_points[:5])
            lines.append(f"• نقاط الدخول: {eps}")
        if self.commands:
            cmds = " ".join(f"/{c.name}" for c in self.commands[:12])
            lines.append(f"• أوامر مكتشفة: {cmds}")
        if self.dependencies:
            deps = ", ".join(self.dependencies[:8])
            lines.append(f"• اعتماديات: {deps}")
        if self.summary:
            lines.append(f"• ملخص: {self.summary}")
        if self.notes:
            lines.append("• ملاحظات: " + " | ".join(self.notes[:4]))
        return "\n".join(lines)
