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

## Domain entities

Tenant, Job, Invoice, **Balance**

## Wired paths (live)

| Entry | Flow |
|-------|------|
| `POST /v1/tenants` | `handle_create_tenant` |
| `require_tenant` | `handle_authenticate_tenant` + **`handle_enforce_api`** (no TenantStore) |
| SSE tenant gate | `handle_get_tenant` + **`handle_enforce_api`** (no TenantStore) |
| white-label / rotate key | application handlers |
| jobs get/list/cancel/pause/resume | application handlers |
| balance read | `handle_get_balance` → `BillingGateway` |
| generation gate | `handle_enforce_generation` |

## Composition

`lumen.bootstrap`: `get_tenant_repository`, `get_job_repository`, `get_billing_gateway`.


## Phase 3 — AI boundary

Telegram NL turns enter via:

```
lumen.interfaces.telegram / lumen.bot
  → lumen.infrastructure.ai.handle_user_turn
      → lumen.engine.services.multi_agent.engine_turn (implementation)
```

Presentation must not import `lumen.engine.services.multi_agent.engine_turn` directly.
