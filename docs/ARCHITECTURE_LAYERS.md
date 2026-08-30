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
| `POST /v1/tenants` | `handle_create_tenant` |
| `require_tenant` | `handle_authenticate_tenant` |
| white-label update | `handle_update_white_label` |
| rotate API key | `handle_rotate_api_key` |
| `GET /v1/jobs/{id}` | `handle_get_job` (ownership in application) |
| `GET /v1/jobs` | `JobRepository.list_for_tenant` |
| cancel / pause / resume job | `handle_cancel_job` / `handle_pause_job` / `handle_resume_job` |

## Composition

`lumen.bootstrap` wires `PlatformTenantRepository` / `PlatformJobRepository`.

SSE stream + steer still use infrastructure job runner directly (long-lived transport concerns).
