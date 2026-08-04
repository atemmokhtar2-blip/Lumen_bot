"""
Assemble project strictly from FormalBotSpec.
No domain templates. Handlers/services/models follow understood structure only.
"""

from __future__ import annotations

import logging
from pathlib import Path

from ..schemas.formal_spec import FormalBotSpec
from . import dynamic_codegen as gen

logger = logging.getLogger(__name__)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.replace("\r\n", "\n").rstrip() + "\n", encoding="utf-8")


def generate_project(spec: FormalBotSpec, output_dir: str | Path) -> Path:
    root = Path(output_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    app = root / "app"
    handlers = app / "handlers"
    services = app / "services"

    _write(root / "requirements.txt", gen.render_requirements(spec))
    _write(root / ".env.example", gen.render_env_example(spec))
    _write(root / "README.md", gen.render_readme(spec))
    _write(root / "pyproject.toml", gen.render_pyproject(spec))

    _write(app / "__init__.py", '"""Application package."""\n')
    _write(handlers / "__init__.py", '"""Handlers assembled from FormalBotSpec."""\n')
    _write(services / "__init__.py", '"""Services assembled from FormalBotSpec."""\n')

    _write(app / "config.py", gen.render_config(spec))
    _write(app / "models.py", gen.render_models(spec))
    _write(app / "main.py", gen.render_main(spec))

    _write(handlers / "start.py", gen.render_start_handler(spec))
    _write(handlers / "callbacks.py", gen.render_callbacks(spec))
    _write(handlers / "messages.py", gen.render_messages(spec))

    # One module per understood command (except start/help already in start.py)
    for cmd in spec.ui.commands or []:
        if cmd.command in ("start", "help"):
            continue
        ident = gen._safe_ident(cmd.command)
        _write(
            handlers / f"cmd_{ident}.py",
            gen.render_command_handler(cmd.command, cmd.description, cmd.admin_only, spec),
        )

    for svc in spec.services or []:
        ident = gen._safe_ident(svc)
        _write(services / f"{ident}.py", gen.render_service(svc, spec))

    logger.info(
        "Assembled from spec only: name=%s cmds=%d buttons=%d models=%d services=%d",
        spec.bot_name,
        len(spec.ui.commands or []),
        len(spec.ui.main_buttons or []),
        len(spec.data_models or []),
        len(spec.services or []),
    )
    return root
