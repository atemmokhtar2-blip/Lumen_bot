"""RepoContract — deep structured understanding of an existing repository."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class FileEntry(StrictModel):
    path: str
    size: int = 0
    kind: str = "other"


class DetectedCommand(StrictModel):
    name: str
    source_file: str = ""
    evidence: str = ""
    registration: str = ""  # CommandHandler | decorator | BotCommand | def


class DetectedHandler(StrictModel):
    kind: str
    name: str = ""
    source_file: str = ""


class EntryPoint(StrictModel):
    path: str
    reason: str = ""
    score: int = 0


class ClassInfo(StrictModel):
    name: str
    file: str
    bases: list[str] = Field(default_factory=list)
    methods: list[str] = Field(default_factory=list)
    kind: str = "class"  # class | pydantic | dataclass | engine | service


class FunctionInfo(StrictModel):
    name: str
    file: str
    is_async: bool = False
    decorators: list[str] = Field(default_factory=list)


class ModuleInfo(StrictModel):
    path: str
    imports: list[str] = Field(default_factory=list)
    classes: list[str] = Field(default_factory=list)
    functions: list[str] = Field(default_factory=list)
    lines: int = 0


class LayerInfo(StrictModel):
    name: str
    path: str
    file_count: int = 0
    role: str = ""


class EnvVarInfo(StrictModel):
    name: str
    source_file: str = ""


class RepoContract(StrictModel):
    schema_version: str = "2.0"
    root_path: str
    repo_name: str = ""
    remote_url: str = ""

    languages: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    architecture_style: str = "unknown"  # monolith | modular | microservice | library | telegram_bot | generation_engine

    entry_points: list[EntryPoint] = Field(default_factory=list)
    commands: list[DetectedCommand] = Field(default_factory=list)
    handlers: list[DetectedHandler] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)

    layers: list[LayerInfo] = Field(default_factory=list)
    key_classes: list[ClassInfo] = Field(default_factory=list)
    key_functions: list[FunctionInfo] = Field(default_factory=list)
    modules_sample: list[ModuleInfo] = Field(default_factory=list)
    env_vars: list[EnvVarInfo] = Field(default_factory=list)
    data_models: list[str] = Field(default_factory=list)
    services: list[str] = Field(default_factory=list)
    engines: list[str] = Field(default_factory=list)

    file_count: int = 0
    python_file_count: int = 0
    total_lines: int = 0
    top_files: list[FileEntry] = Field(default_factory=list)
    top_dirs: list[str] = Field(default_factory=list)

    is_telegram_bot: bool = False
    is_generation_engine: bool = False
    confidence: float = 0.0
    summary: str = ""
    architecture_summary: str = ""
    notes: list[str] = Field(default_factory=list)
    quality_signals: dict[str, Any] = Field(default_factory=dict)
    raw_stats: dict[str, Any] = Field(default_factory=dict)

    def to_user_summary(self) -> str:
        lines = [
            f"📦 *فهم المستودع (عمق عالي):* `{self.repo_name or self.root_path}`",
            f"• النوع: `{self.architecture_style}`",
            f"• ملفات: {self.file_count} | Python: {self.python_file_count} | أسطر≈{self.total_lines}",
            f"• لغات: {', '.join(self.languages) or '—'}",
            f"• أطر: {', '.join(self.frameworks) or '—'}",
            f"• بوت تليجرام: {'نعم' if self.is_telegram_bot else 'لا'}"
            f" | محرك توليد: {'نعم' if self.is_generation_engine else 'لا'}",
            f"• ثقة الفهم: {self.confidence:.0%}",
        ]
        if self.architecture_summary:
            lines.append(f"• معمارية: {self.architecture_summary}")
        if self.layers:
            lyr = ", ".join(f"{x.name}({x.file_count})" for x in self.layers[:8])
            lines.append(f"• طبقات: {lyr}")
        if self.entry_points:
            eps = ", ".join(f"`{e.path}`" for e in self.entry_points[:5])
            lines.append(f"• نقاط الدخول: {eps}")
        if self.commands:
            cmds = " ".join(f"/{c.name}" for c in self.commands[:15])
            lines.append(f"• أوامر مسجّلة: {cmds}")
        if self.engines:
            lines.append(f"• محركات: {', '.join(self.engines[:12])}")
        if self.services:
            lines.append(f"• خدمات: {', '.join(self.services[:10])}")
        if self.data_models:
            lines.append(f"• نماذج بيانات: {', '.join(self.data_models[:12])}")
        if self.key_classes:
            kc = ", ".join(c.name for c in self.key_classes[:10])
            lines.append(f"• أصناف مهمة: {kc}")
        if self.env_vars:
            lines.append(f"• متغيرات بيئة: {', '.join(v.name for v in self.env_vars[:10])}")
        if self.dependencies:
            lines.append(f"• اعتماديات: {', '.join(self.dependencies[:10])}")
        if self.summary:
            lines.append(f"• ملخص: {self.summary}")
        if self.notes:
            lines.append("• ملاحظات: " + " | ".join(self.notes[:5]))
        qs = self.quality_signals or {}
        if qs:
            bits = []
            if qs.get("has_tests"):
                bits.append("اختبارات✓")
            if qs.get("has_typing"):
                bits.append("typing✓")
            if qs.get("has_async"):
                bits.append("async✓")
            if bits:
                lines.append(f"• إشارات جودة: {', '.join(bits)}")
        return "\n".join(lines)
