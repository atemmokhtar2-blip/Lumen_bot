"""Tool contracts — pure description. No I/O."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List

@dataclass(frozen=True)
class ToolParamSpec:
    name: str
    description: str = ""
    required: bool = False

@dataclass(frozen=True)
class ToolContract:
    name: str
    description: str
    params: List[ToolParamSpec] = field(default_factory=list)
    requires_confirmation: bool = False
    capability: str = ""
    def to_spec_dict(self) -> Dict[str, Any]:
        return {
            "description": self.description,
            "params": {p.name: p.description for p in self.params},
            "requires_confirmation": self.requires_confirmation,
            "capability": self.capability,
        }

def build_default_contracts() -> Dict[str, ToolContract]:
    specs = [
        ToolContract("create_repo", "إنشاء مستودع جديد على GitHub",
            [ToolParamSpec("name", required=True), ToolParamSpec("token", required=True),
             ToolParamSpec("private"), ToolParamSpec("description")], True, "git"),
        ToolContract("git_push", "دفع التغييرات للمستودع",
            [ToolParamSpec("path"), ToolParamSpec("token"), ToolParamSpec("message")], True, "git"),
        ToolContract("git_pull", "سحب آخر نسخة",
            [ToolParamSpec("path"), ToolParamSpec("token")], False, "git"),
        ToolContract("clone_repo", "سحب مستودع Git",
            [ToolParamSpec("url", required=True), ToolParamSpec("token"),
             ToolParamSpec("branch"), ToolParamSpec("depth")], False, "git"),
        ToolContract("repo_inspect", "فحص مستودع", [ToolParamSpec("path")], False, "inspect"),
        ToolContract("repo_understand", "تحليل بنية المستودع", [ToolParamSpec("path")], False, "inspect"),
        ToolContract("generate_bot", "توليد بوت تيليجرام",
            [ToolParamSpec("spec_request", required=True)], False, "generation"),
        ToolContract("refine_bot", "تعديل بوت موجود",
            [ToolParamSpec("spec_request", required=True)], False, "generation"),
        ToolContract("repo_modify", "تعديل على المستودع عبر المحرك",
            [ToolParamSpec("path"), ToolParamSpec("change", required=True)], True, "generation"),
        ToolContract("host_status", "حالة الاستضافة", [], False, "hosting"),
        ToolContract("host_start", "تشغيل استضافة بوت",
            [ToolParamSpec("project_path")], True, "hosting"),
        ToolContract("host_stop", "إيقاف استضافة بوت",
            [ToolParamSpec("project_path")], True, "hosting"),
    ]
    return {c.name: c for c in specs}

__all__ = ["ToolParamSpec", "ToolContract", "build_default_contracts"]
