# Database migrations (Alembic)

Official tool: [Alembic](https://alembic.sqlalchemy.org/)

```bash
export DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/lumen
alembic upgrade head
alembic current
alembic history
```

New change:

```bash
alembic revision -m "add_column_x"
# edit alembic/versions/*.py
alembic upgrade head
```

Production: run `alembic upgrade head` in the release job **before** starting API workers.
