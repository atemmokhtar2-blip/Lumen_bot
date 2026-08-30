# Clean Architecture Layers

```
interfaces/  →  application/  →  domain/
     ↓                ↓
infrastructure/  (adapters implement domain ports)
```

| Layer | Package | Rule |
|-------|---------|------|
| Domain | `lumen.domain` | Pure Python. Entities, value objects, repository *interfaces*. No I/O. |
| Application | `lumen.application` | Use cases: commands, queries, handlers. Depends on domain only. |
| Interfaces | `lumen.interfaces` | Telegram / API façades. Translate transport → commands/queries. |
| Infrastructure | `lumen.infrastructure` | Implements ports (Postgres, Redis, Docker, LLM…). |

## Composition

`lumen.bootstrap` wires `PlatformTenantRepository` / `PlatformJobRepository` to handlers.

## Migration note

`lumen.bot`, `lumen.api`, `lumen.platform`, `lumen.engine` remain importable.
New code should call application handlers + domain ports instead of reaching into stores directly.
