"""
Structure materializer — Phase 1.

Writes ONLY structural stubs + structure_manifest.json from a StructurePlan.
Never invents domain features. Bodies are empty signatures (pass / ...).

Code Engine (Phase 2) is responsible for real logic.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..schemas.structure_plan import FileRole, FileStubKind, StructurePlan


def _safe_ident(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_]", "_", (name or "").strip())
    if not s:
        return "item"
    if s[0].isdigit():
        s = "n_" + s
    return s


def _stub_main(plan: StructurePlan) -> str:
    cmds = plan.command_names or []
    lines = [
        '"""Structure stub — entry. Code Engine wires handlers."""',
        "from __future__ import annotations",
        "",
        "# Bound commands (from user contract only):",
    ]
    for c in cmds:
        lines.append(f"#   /{c}")
    lines += [
        "",
        "def main() -> None:",
        '    """Entry point — filled by Code Engine."""',
        "    raise NotImplementedError('structure_stub: awaiting Code Engine')",
        "",
        "",
        'if __name__ == "__main__":',
        "    main()",
        "",
    ]
    return "\n".join(lines)


def _stub_config(plan: StructurePlan) -> str:
    return "\n".join(
        [
            '"""Structure stub — config. Code Engine fills settings."""',
            "from __future__ import annotations",
            "",
            "class Settings:",
            '    """Typed settings placeholder — no domain fields invented."""',
            "    telegram_bot_token: str = \"\"",
            "",
            "",
            "def get_settings() -> Settings:",
            "    return Settings()",
            "",
        ]
    )


def _stub_models(plan: StructurePlan) -> str:
    lines = [
        '"""Structure stub — models from user entities only."""',
        "from __future__ import annotations",
        "",
        "from dataclasses import dataclass, field",
        "from typing import Any",
        "",
    ]
    ents = plan.entity_names or []
    if not ents:
        lines += [
            "# No entities declared in user contract.",
            "",
        ]
    for name in ents:
        cls = _safe_ident(name)
        if not cls[:1].isupper():
            cls = cls[:1].upper() + cls[1:] if cls else "Entity"
        lines += [
            "@dataclass",
            f"class {cls}:",
            f'    """Entity `{name}` — fields filled by Code Engine from contract."""',
            "    id: str = \"\"",
            "    data: dict[str, Any] = field(default_factory=dict)",
            "",
            "",
        ]
    return "\n".join(lines)


def _stub_handlers(plan: StructurePlan) -> str:
    lines = [
        '"""Structure stub — handlers bound to user commands only."""',
        "from __future__ import annotations",
        "",
        "from typing import Any",
        "",
    ]
    cmds = plan.command_names or []
    if not cmds:
        lines += [
            "# No commands in user contract.",
            "",
        ]
    for c in cmds:
        fn = "cmd_" + _safe_ident(c)
        lines += [
            f"async def {fn}(update: Any, context: Any) -> None:",
            f'    """Handler for /{c} — body filled by Code Engine."""',
            "    ...",
            "",
            "",
        ]
    # optional callback placeholder if buttons exist
    if plan.button_labels:
        lines += [
            "async def on_callback(update: Any, context: Any) -> None:",
            '    """Callback router — labels from user buttons only."""',
            "    ...",
            "",
            "",
        ]
    return "\n".join(lines)


def _stub_requirements(plan: StructurePlan) -> str:
    return "python-telegram-bot>=21.0,<22\npython-dotenv>=1.0.0\n"


def _stub_env_example(plan: StructurePlan) -> str:
    return "TELEGRAM_BOT_TOKEN=\n"


def _stub_readme(plan: StructurePlan) -> str:
    name = plan.bot_name or "generated_bot"
    cmds = ", ".join(f"/{c}" for c in (plan.command_names or [])[:20]) or "(none)"
    ents = ", ".join(plan.entity_names or []) or "(none)"
    lines = [
        f"# {name}",
        "",
        "Generated from your description (deterministic formal engine).",
        "",
        f"- Commands: {cmds}",
        f"- Entities: {ents}",
        "",
        "## Run",
        "",
        "1. Copy `.env.example` to `.env` and set `TELEGRAM_BOT_TOKEN`",
        "2. `pip install -r requirements.txt`",
        "3. `python main.py`",
        "",
    ]
    return chr(10).join(lines)


def _stub_other(plan: StructurePlan, path: str) -> str:
    return (
        f'"""Structure stub: {path} — reserved by Structure Engine."""\n'
        "from __future__ import annotations\n"
    )


_ROLE_WRITERS = {
    FileRole.ENTRY: _stub_main,
    FileRole.CONFIG: _stub_config,
    FileRole.MODELS: _stub_models,
    FileRole.HANDLERS: _stub_handlers,
    FileRole.REQUIREMENTS: _stub_requirements,
    FileRole.ENV_EXAMPLE: _stub_env_example,
    FileRole.README: _stub_readme,
}


def render_stub(plan: StructurePlan, role: FileRole, path: str) -> str:
    writer = _ROLE_WRITERS.get(role)
    if writer:
        return writer(plan)
    return _stub_other(plan, path)


def materialize_structure(
    plan: StructurePlan,
    out_dir: str | Path,
    *,
    overwrite: bool = True,
) -> list[str]:
    """
    Write signature stubs + structure_manifest.json under out_dir.

    Returns list of relative paths written.
    """
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    written: list[str] = []

    # Force signature stubs in Phase 1 plan copy for materialization
    for pf in plan.files:
        if not pf.required and pf.role == FileRole.OTHER:
            # skip optional OTHER unless we explicitly want them
            continue
        rel = pf.path.replace("\\", "/")
        if rel.startswith("./"):
            rel = rel[2:]
        if not rel or ".." in rel.split("/"):
            continue
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and not overwrite:
            continue
        content = render_stub(plan, pf.role, rel)
        # Mark stub kind signatures in content is enough; plan may still say WIRED upstream
        target.write_text(content if content.endswith("\n") else content + "\n", encoding="utf-8")
        written.append(rel)

    # Always ensure app package init if any app/ file
    if any(p.startswith("app/") for p in written):
        init = root / "app" / "__init__.py"
        if not init.exists() or overwrite:
            init.write_text(
                '"""App package — structure stage."""\n',
                encoding="utf-8",
            )
            if "app/__init__.py" not in written:
                written.append("app/__init__.py")

    manifest = {
        "schema_version": plan.schema_version,
        "bot_name": plan.bot_name,
        "command_names": list(plan.command_names),
        "entity_names": list(plan.entity_names),
        "button_labels": list(plan.button_labels),
        "flow_ids": list(plan.flow_ids),
        "files": [f.to_dict() for f in plan.files],
        "notes": list(plan.notes) + ["phase1_materialized_signatures"],
        "written": list(written),
    }
    man_path = root / "structure_manifest.json"
    man_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if "structure_manifest.json" not in written:
        written.append("structure_manifest.json")

    return written
