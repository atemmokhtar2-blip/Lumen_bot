"""Deterministic Project Generator – complete bots from FormalBotSpec."""
from __future__ import annotations
import logging
from pathlib import Path
from ..schemas.formal_spec import FormalBotSpec, BotType
from . import templates

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

    # Domain handlers based on type / commands
    is_shop = spec.bot_type == BotType.ECOMMERCE or any(
        c.command in ("products", "cart", "orders") for c in spec.ui.commands
    )
    if is_shop:
        _write(handlers / "products.py", templates.render_products_handler(spec))
        _write(handlers / "cart.py", templates.render_cart_handler(spec))
        _write(handlers / "orders.py", templates.render_orders_handler(spec))
        _write(services / "catalog.py", templates.render_catalog_service(spec))
        _write(services / "cart.py", templates.render_cart_service(spec))
        _write(services / "orders.py", templates.render_orders_service(spec))

    if spec.requires_admin_panel or any(c.command == "admin" for c in spec.ui.commands):
        _write(handlers / "admin.py", templates.render_admin_handler(spec))

    logger.info("Generated complete project for '%s' → %s", spec.bot_name, root)
    return root
