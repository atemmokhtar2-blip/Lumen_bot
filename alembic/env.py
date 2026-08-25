"""Alembic environment — reads DATABASE_URL / POSTGRES_URL (psycopg v3)."""
from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, text

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None  # SQL migrations only (no ORM models required)


def _database_url() -> str:
    url = (
        (os.getenv("DATABASE_URL") or "")
        or (os.getenv("POSTGRES_URL") or "")
        or (os.getenv("POSTGRESQL_URL") or "")
        or (config.get_main_option("sqlalchemy.url") or "")
    ).strip()
    if not url or url.startswith("driver://"):
        raise RuntimeError(
            "Set DATABASE_URL (or POSTGRES_URL) before running alembic. "
            "Example: postgresql+psycopg://user:pass@localhost:5432/lumen"
        )
    # Normalize plain postgresql:// to SQLAlchemy psycopg3 driver
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://") and "+psycopg" not in url:
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def run_migrations_offline() -> None:
    url = _database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    cfg = config.get_section(config.config_ini_section) or {}
    cfg["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
