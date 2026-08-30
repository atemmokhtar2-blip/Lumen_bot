# Clean Architecture Layers

```
interfaces/  →  application/  →  domain/
     ↓                ↓
infrastructure/  (adapters implement domain ports)
```

| Layer | Package | Rule |
|-------|---------|------|
| Domain | `lumen.domain` | Pure Python. Entities, value objects, repository *ports*. No I/O. |
| Application | `lumen.application` | Use cases: commands, queries, handlers. Depends on domain only. |
| Interfaces | `lumen.interfaces` | Telegram / API / Web façades. Translate transport → commands/queries. |
| Infrastructure | `lumen.infrastructure` | Implements ports (Postgres, Redis, Docker, LLM…). |

## Wired paths (live)

| Entry | Flow |
|-------|------|
| `POST /v1/tenants` | route → `handle_create_tenant` → `TenantRepository` |
| `require_tenant` (API auth) | `handle_authenticate_tenant` → `TenantRepository` |
| `GET /v1/jobs/{id}` | `handle_get_job` (ownership in application) |
| `GET /v1/jobs` | `JobRepository.list_for_tenant` |

## Composition

`lumen.bootstrap` wires `PlatformTenantRepository` / `PlatformJobRepository`.

## Migration

`lumen.bot`, `lumen.api`, `lumen.platform`, `lumen.engine` remain importable.
Mutating job controls (cancel/pause/steer) and white-label update still touch
platform services until dedicated commands are added.
