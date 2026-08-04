"""
General-purpose Deterministic Project Generator.
Produces clean, typed Telegram bot projects for ANY description.
"""

from __future__ import annotations

import logging
from pathlib import Path

from ..schemas.formal_spec import FormalBotSpec
from . import templates

logger = logging.getLogger(__name__)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = content.replace("\r\n", "\n").rstrip() + "\n"
    path.write_text(text, encoding="utf-8")


def generate_project(spec: FormalBotSpec, output_dir: str | Path) -> Path:
    root = Path(output_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)

    app = root / "app"
    handlers = app / "handlers"
    services = app / "services"

    _write(root / "requirements.txt", templates.render_requirements(spec))
    _write(root / ".env.example", templates.render_env_example(spec))
    _write(root / "README.md", templates.render_readme(spec))
    _write(root / "pyproject.toml", templates.render_pyproject(spec))

    _write(app / "__init__.py", '"""Application package."""\n')
    _write(handlers / "__init__.py", '"""Handlers package."""\n')
    _write(services / "__init__.py", '"""Services package."""\n')

    _write(app / "config.py", templates.render_config(spec))
    _write(app / "main.py", templates.render_main(spec))
    _write(app / "models.py", templates.render_models(spec))

    _write(handlers / "start.py", templates.render_start_handler(spec))
    _write(handlers / "messages.py", templates.render_message_handler(spec))
    _write(handlers / "callbacks.py", templates.render_callback_handler(spec))

    logger.info("Generated general bot project '%s' → %s", spec.bot_name, root)
    return root
