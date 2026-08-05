"""
CodegenService — Formal Logic & DSL Engine only.

NO templates. NO behavior.py emission. NO framework_emit packs.
All generation: text → DSL → Inference → Micro-Transpiler → Verify.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...schemas.program_contract import ProgramContract


class CodegenService:
    """Free generation entry — formal path only."""

    def run(self, contract: ProgramContract, output_dir: str | Path) -> tuple[Path, dict]:
        root = Path(output_dir).resolve()
        text = ""
        for attr in ("source_text", "raw_text", "user_text", "description", "summary"):
            text = str(getattr(contract, attr, "") or "").strip()
            if text:
                break
        if not text:
            parts: list[str] = []
            name = getattr(contract, "bot_name", "") or "bot"
            parts.append(f"بوت {name}")
            for c in getattr(contract, "commands", None) or []:
                n = getattr(c, "name", "") or ""
                d = getattr(c, "description", "") or n
                if n:
                    parts.append(f"/{n} - {d}")
            for e in getattr(contract, "entities", None) or []:
                en = getattr(e, "name", "") or ""
                attrs = getattr(e, "attributes", None) or getattr(e, "fields", None) or []
                if hasattr(attrs, "__iter__") and not isinstance(attrs, (str, bytes)):
                    attr_s = " و ".join(str(a) for a in attrs)
                    parts.append(f"كيان {en} يحتاج {attr_s}" if attr_s else f"كيان {en}")
                elif en:
                    parts.append(f"كيان {en}")
            for b in getattr(contract, "buttons", None) or []:
                lab = getattr(b, "label", "") or ""
                if lab:
                    parts.append(f"• {lab}")
            text = "\n".join(parts) if parts else "بوت /start"
        return self.run_from_text(text, root)

    def run_from_text(self, user_text: str, output_dir: str | Path) -> tuple[Path, dict]:
        from ...pipeline_formal import build_from_text

        root = Path(output_dir).resolve()
        result = build_from_text(user_text or "", root)
        verify = result.verification.to_dict() if result.verification else {"ok": False, "errors": ["no verify"]}
        verify["engine_path"] = "dsl_formal"
        verify["dsl_relations"] = result.dsl_relations
        verify["dsl_operations"] = result.dsl_operations
        verify["dsl_rules"] = result.dsl_rules
        verify["files"] = list(result.files)
        return root, verify


def generate_from_contract(contract: ProgramContract, output_dir: str | Path) -> tuple[Path, dict]:
    return CodegenService().run(contract, output_dir)


def generate_from_text(user_text: str, output_dir: str | Path) -> tuple[Path, dict]:
    return CodegenService().run_from_text(user_text, output_dir)
