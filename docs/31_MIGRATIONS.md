# Database migrations

Tool: **Alembic** (official SQLAlchemy migration runner).

```bash
export DATABASE_URL=postgresql+psycopg://user:pass@host:5432/lumen
alembic upgrade head
```

Release pipeline must run migrations **before** rolling out API workers.

See `alembic/README.md`.
