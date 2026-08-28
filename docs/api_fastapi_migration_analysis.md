# API Simplification — FastAPI Migration Analysis

**Status:** Medium-term strategic recommendation (analysis only)
**Date:** Auto-generated during security & dependency remediation
**Current framework:** aiohttp 3.14.3 + hand-maintained `openapi.yaml`

## 1. Current State Assessment

The B2B API surface (`lumen/api/`) is built on **aiohttp** with an application
factory (`create_app()`) and a set of explicit middlewares:

- `error_middleware` — generic exception → 500 JSON (never leaks internals)
- `body_size_guard_middleware` — Content-Length spoofing guard
- `json_body_middleware` — single root JSON parser (bytes → validated object)
- `ip_rate_limit_middleware` — Redis-only per-IP/tenant rate limit (fail-closed 503)
- `security_headers_middleware` — OWASP response headers on every response
- `cors_middleware` — strict origin allowlist (no wildcard in production)

Routes are registered imperatively via `app.router.add_get/add_post(...)` across
**12 route modules** (`tenants`, `generate`, `jobs`, `hosts`, `billing`,
`dashboard`, `audit`, `usage`, `runs_ux`, `github_webhooks`, `health`).

The OpenAPI spec lives in `lumen/api/openapi.yaml` — a **hand-maintained** 216-line
YAML file. Swagger UI and Redoc are served from pinned CDN bundles (`/docs`,
`/swagger`, `/redoc`). The CI enforces `grep -q "/v1/generate" api/openapi.yaml`,
i.e. the spec must exist and mention a key path, but it is **not** verified to
match the actual route surface.

### Identified maintenance friction points

1. **Spec drift:** `openapi.yaml` is hand-written. Any new endpoint, parameter,
   or response shape requires a parallel manual edit to the YAML. There is no
   compile-time guarantee the spec matches the implementation. This is the
   single largest source of documentation rot in the API layer.
2. **Boilerplate per route:** every handler manually re-derives the tenant from
   headers, re-parses `request["json_body"]`, re-validates shapes, and re-builds
   JSON responses. There is no shared declarative binding layer.
3. **Validation is imperative:** input validation relies on scattered manual
   checks rather than a schema-driven validator, so contract enforcement is
   uneven across endpoints.
4. **Middleware ordering is implicit:** the `_mws` list order encodes subtle
   security semantics (e.g. JSON gate must run before rate-limit key derivation
   that reads `request["tenant"]`). This is correct today but fragile to extend.

## 2. Recommendation

**Adopt FastAPI as the medium-term target for the B2B HTTP surface**, while
preserving every existing security control. FastAPI is the strongest
production-grade choice for this codebase because:

- **Native OpenAPI 3.1 generation** from Pydantic models — eliminates spec drift
  entirely (the #1 friction point above). The generated spec replaces the
  hand-maintained `openapi.yaml`.
- **Pydantic v2 is already a core dependency** (`pydantic==2.10.6`,
  `pydantic-settings==2.7.1`), used for `APISettings`. Reusing the same validation
  engine for request/response models removes a parallel validation system.
- **Dependency injection** (`Depends`) cleanly replaces the manual tenant/auth
  derivation scattered across handlers, making the security boundary explicit
  and auditable per-route.
- **ASGI + async** — FastAPI is ASGI-native and pairs with `uvicorn` (already a
  transitive dependency via `mcp`). The async rate-limit and Redis calls remain
  unchanged.
- **First-class security helpers** — `HTTPBearer`, API key dependencies, and
  CORSMiddleware map directly onto the current strict-origin CORS policy.

### Why not alternatives

- **Stay on aiohttp:** viable, but the hand-maintained OpenAPI spec remains a
  permanent maintenance tax and drift risk. No automatic documentation.
- **Litestar / Starlite:** strong and fast, but a smaller ecosystem and less
  developer familiarity than FastAPI; the Pydantic-alignment benefit is identical.
- **Flask + apispec:** synchronous by default; would fight the existing async
  Redis/rate-limit architecture.

## 3. Migration Guardrails (when executed)

This is a **non-disruptive, incremental** migration, not a rewrite. Hard rules:

1. **No security regression.** Every current middleware MUST have a direct
   FastAPI equivalent BEFORE any route moves:
   - fail-closed 503 rate limit (Redis-only, no memory fallback)
   - strict CORS allowlist (no wildcard in production)
   - OWASP security headers on every response (incl. errors)
   - single capped JSON body parser (no `request.json()`)
   - Content-Length spoofing guard
   - generic 500 that never leaks internals
2. **Preserve `create_app()` semantics** — the factory pattern, isolation
   snapshot logging, observability setup, and `require_production_data_plane()`
   gate must run at startup exactly as today.
3. **Keep the route paths and status codes identical** — the SDKs
   (`sdks/python`, `sdks/javascript`) and the web frontend depend on the
   current contract. The generated OpenAPI must be a strict superset of the
   current `openapi.yaml`.
4. **Delete the hand-maintained `openapi.yaml`** only after the FastAPI-generated
   spec is verified to cover every existing path (rule: no dead documentation
   left behind — per project cleanliness protocol).
5. **Migrate route-by-route** behind a feature flag, with the existing aiohttp
   app as fallback, until full coverage + test parity is reached.

## 4. Effort & Sequencing (indicative)

| Phase | Scope | Risk |
|-------|-------|------|
| 1 | FastAPI app shell + all middlewares ported + health/ready/plans | Low — no auth |
| 2 | Tenant auth dependency + `/v1/tenants`, `/v1/me` | Medium |
| 3 | `/v1/generate`, `/v1/jobs/*` (long-running, SSE) | Medium — streaming |
| 4 | billing, hosts, dashboard, audit, usage, webhooks | Low–Medium |
| 5 | Delete `openapi.yaml`; switch CI OpenAPI check to generated spec | Low |
| 6 | Retire aiohttp `app.py` once 100% coverage + tests pass | Low |

## 5. Decision

This document records the recommendation and rationale. **No code changes are
made now** — the user's directive was "النظر في" (consider/evaluate). Execution
should be a separate, dedicated migration with its own branch, full test
parity, and the FINAL GATE applied per the project's strict development protocol.
