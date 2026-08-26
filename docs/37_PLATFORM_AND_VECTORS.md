# Platforms + production vectors (global path)

## Platforms

| Platform | Scaffold | Runtime |
|----------|----------|---------|
| Telegram | `platform_generators/telegram_scaffold.py` | python-telegram-bot |
| Discord | `discord_scaffold.py` | discord.py |
| WhatsApp | `whatsapp_scaffold.py` | Meta Cloud API (Graph) |
| Web | minimal HTTP app | stdlib → expand FastAPI later |

```python
from lumen.engine.services.platform_generators import apply_platform_scaffold, detect_platform
apply_platform_scaffold("/path", user_text="discord moderation bot")
```

Env override: `LUMEN_TARGET_PLATFORM=discord|whatsapp|telegram|web`

## Voyage + Qdrant (production)

```bash
# Embeddings
export CODE_EMBEDDING_PROVIDER=auto   # uses Voyage when VOYAGE_API_KEY set
export VOYAGE_API_KEY=...
export CODE_EMBEDDING_MODEL=voyage-code-3

# Vectors
export CODE_VECTOR_BACKEND=qdrant
export QDRANT_URL=http://localhost:6333
export QDRANT_COLLECTION=lumen_code
# optional: QDRANT_API_KEY=...
```

Docker Qdrant:

```bash
docker run -p 6333:6333 qdrant/qdrant
```

Without Qdrant/Voyage keys the system falls back to numpy store + local/fastembed embeddings (still functional).
