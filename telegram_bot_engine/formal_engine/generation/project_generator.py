"""
Project generator — assembles a bot FROM FormalBotSpec structure.

Principle: understanding produces handlers/models/services/commands/buttons;
generation materializes them. No fixed "shop template" as the source of truth.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from ..schemas.formal_spec import FormalBotSpec, HandlerSpec
from . import templates

logger = logging.getLogger(__name__)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.replace("\r\n", "\n").rstrip() + "\n", encoding="utf-8")


def _handler_names(spec: FormalBotSpec) -> set[str]:
    names = {h.name for h in spec.handlers}
    names.update(c.command for c in spec.ui.commands)
    return names


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
    _write(handlers / "__init__.py", '"""Handlers — generated from understood HandlerSpec list."""\n')
    _write(services / "__init__.py", '"""Services — generated from understood service list."""\n')

    _write(app / "config.py", templates.render_config(spec))
    _write(app / "main.py", templates.render_main(spec))
    _write(app / "models.py", templates.render_models_from_spec(spec))

    # Always start/help/callbacks/messages
    _write(handlers / "start.py", templates.render_start_handler(spec))
    _write(handlers / "messages.py", templates.render_message_handler(spec))
    _write(handlers / "callbacks.py", templates.render_callback_handler(spec))

    names = _handler_names(spec)
    # Materialize domain handlers only when understanding asked for them
    if "products" in names or "product_catalog" in spec.feature_tags:
        _write(handlers / "products.py", templates.render_products_handler(spec))
    if "cart" in names or "shopping_cart" in spec.feature_tags:
        _write(handlers / "cart.py", templates.render_cart_handler(spec))
    if "orders" in names or "order_management" in spec.feature_tags:
        _write(handlers / "orders.py", templates.render_orders_handler(spec))
    if "admin" in names or spec.requires_admin_panel:
        _write(handlers / "admin.py", templates.render_admin_handler(spec))

    # Services from understood list
    if "catalog" in spec.services or "product_catalog" in spec.feature_tags:
        _write(services / "catalog.py", templates.render_catalog_service(spec))
    if "cart" in spec.services or "shopping_cart" in spec.feature_tags:
        _write(services / "cart.py", templates.render_cart_service(spec))
    if "orders" in spec.services or "order_management" in spec.feature_tags:
        _write(services / "orders.py", templates.render_orders_service(spec))

    # Generic service stubs for other understood services
    for svc in spec.services:
        if svc in ("catalog", "cart", "orders", "payments", "notifications"):
            continue
        path = services / f"{svc}.py"
        if not path.exists():
            _write(path, templates.render_generic_service(svc, spec))

    logger.info(
        "Assembled project from FormalBotSpec name=%s type=%s handlers=%d models=%d services=%s",
        spec.bot_name,
        spec.bot_type.value,
        len(spec.handlers),
        len(spec.data_models),
        spec.services,
    )
    return root
