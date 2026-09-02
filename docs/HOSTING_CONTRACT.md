# Hosting Contract (from code)

**Machine-readable source of truth:**
- `lumen/engine/services/hosting/contract.py` (field lists / gates)
- `lumen/engine/schemas/hosting_contract.py` (`HostInstanceRecord` Pydantic door)
- `HostingService._inst_from_row` always validates through `HostInstanceRecord`  
**Human-readable companion:** this file  
**Enforcement:** `tests/test_hosting_contract_phase0.py` (must stay green)

**Scope:** product contract for permanent bot hosting. Extracted from actual modules — not aspirational design.

This document is **Phase 0** of the Hosting Path program. It freezes definitions and failure gates before any behavior change. If the Python contract and this doc disagree, **fix the doc**; if the contract and `HostInstance` disagree, **tests fail** until resolved.

---

## 1. Two planes (hard separation)

| Plane | Code | Role |
|-------|------|------|
| **TRIAL_CHAT** | `lumen/engine/services/live_runner/` | Short-lived preview: install deps, run process, capture errors. Not permanent hosting. |
| **PERMANENT_HOST** | `lumen/engine/services/hosting/` | Long-running commercial hosting. Sole product path for “استضف”. |

`HostingService` module docstring (authoritative):

> HostingService — PERMANENT_HOST plane only (long-running / commercial).  
> NOT the chat trial path. Trial is LiveRunner (TRIAL_CHAT).

**Rule:** LiveRunner must never be used as a silent substitute for permanent hosting in multi-tenant/production.

---

## 2. HostedBot / HostInstance contract

Canonical in-memory and persisted shape: `HostInstance` in  
`lumen/engine/services/hosting/service.py`.

| Field | Type | Meaning (from code) |
|-------|------|---------------------|
| `instance_id` | `str` | Unique id (`host-{uuid10}` or job-derived in scale mode) |
| `user_id` | `int` | Owner Telegram/API user id |
| `project_path` | `str` | Absolute path; **must** be under that user’s sandbox |
| `entry_point` | `str` | Entry script (may be empty until resolved) |
| `bot_username` | `str` | Optional @username |
| `status` | `str` | `starting` \| `running` \| `stopped` \| `failed` (also deploy-queue states in scale mode) |
| `deployment_id` | `str` | Sandbox/backend deployment id |
| `sandbox_backend` | `str` | `firecracker` \| `gvisor` \| `dind` \| `docker` |
| `pid` | `int \| None` | Guest/host pid when known |
| `started_at` | `float` | Unix time |
| `last_error` | `str` | Last failure message |
| `last_diagnosis` | `dict` | Error-intelligence payload |
| `token_fp` | `str` | `sha256(token)[:16]` — **never store raw token** |

### Persistence

| Environment | Store | Module |
|-------------|--------|--------|
| `dev` / `local` / `test` | SQLite `instances` table | `hosting/state_store.py` (`HostingStateStore`) |
| Production | Postgres control plane | `hosting/pg_control_plane.py` + `pg_state_store` |

Postgres tables (control plane):

- `tbe_workers` — fleet heartbeats + capacity  
- `tbe_deploy_jobs` — deploy queue  
- `tbe_host_instances` — optional mirror of running bots  

SQLite is **forbidden** outside dev (`HostingStateStore` raises if not dev).

### Related runtime types

`SandboxSpec` / `SandboxHandle` / `SandboxProbe` — `lumen/engine/services/sandbox_runtime/types.py`.

`HostResult` — operation result with `ok`, `message`, optional `instance`, `error_contract`, `details`; user text via `to_user_text()`.

---

## 3. Production isolation (fail-closed)

Authoritative modules:

- `lumen/engine/services/isolation_policy.py`
- `lumen/engine/services/sandbox_runtime/select.py`
- `lumen/engine/services/hosting/market_gate.py`

### Policy summary

| Condition | Required backend | LocalProcess |
|-----------|------------------|--------------|
| Multi-tenant **or** non-dev environment | **Firecracker only** | Forbidden |
| Dev + single-tenant + explicit dual flags | May use weaker backends | Only if dual gate allows |

- `is_production_sandbox_path()` → multi-tenant OR not dev → Firecracker-only path.  
- gVisor / DinD / Docker = **dev-only** backends (`_DEV_ONLY`).  
- Commercial track in `market_gate`: Firecracker + jailer + kernel + rootfs; gVisor/Docker **rejected** for sale.

### `IsolationDecision`

- `require_strong_isolation` (preferred)  
- `allow_local` / `may_use_local`  
- `require_docker` (legacy name; means strong sandbox, not Docker exclusively)

---

## 4. Ordered failure gates on `HostingService.start`

Extracted order from `service.py` (any failure returns `HostResult(ok=False)`):

1. **Project path exists** (directory).  
2. **User sandbox containment** (`user_sandbox.is_under_sandbox`) — IDOR root fix.  
3. **Disk quota** (`enforce_user_quota`) when available.  
4. **Isolation decision** (`decide_isolation`):
   - If `require_strong_isolation` → `strong_sandbox_available()` must succeed (Firecracker in production).  
5. **Non-dev DB**: `TBE_DATABASE_URL` / `DATABASE_URL` required when `TBE_REQUIRE_DATABASE_URL` is on (default on).  
6. **Docker network** (only if backend pref is docker/dind/gvisor — not Firecracker TAP path).  
7. **Market gate** (`evaluate_market_gate`) when enabled (default on outside dev).  
8. **Scale / queue path** (if `TBE_SCALE_MODE` or `TBE_FORCE_QUEUE`):
   - Per-user max bots (`TBE_MAX_BOTS_PER_USER`, default 50).  
   - Package artifact + enqueue deploy job (workers build/run).  
9. **Direct sandbox start** (non-queue path): backend run + health; Firecracker may refuse permanent host if `bot_healthy` is false.

### API layer additional gates (`api/routes/hosts.py`)

- Tenant auth + path validation under tenant sandbox.  
- **Balance lifecycle** (`is_hosting_allowed`).  
- **Credit reserve** (`reserve_for_hosting`) — insufficient credits → 402.  
- Token shape validation (Telegram-style checks currently in route).

### Market gate checklist (`evaluate_market_gate`)

When `market_gate_enabled()` (default: on unless `ENVIRONMENT` in dev/local/test, or `TBE_MARKET_GATE=0`):

| Requirement | Source |
|-------------|--------|
| `TBE_TOKEN_SECRET` length ≥ 32 | Sealed tokens at rest |
| `TBE_SCALE_MODE=1` | Queue + workers mandatory for commercial sale |
| `TBE_DATABASE_URL` PostgreSQL | Control plane |
| `TBE_ALLOW_LOCAL_PROCESS` must be 0 | No local process on commercial track |
| `TBE_SANDBOX_BACKEND` not in `{gvisor,dind,docker}` | Firecracker / auto only |
| Firecracker binary | `TBE_FIRECRACKER_BIN` or `firecracker` on PATH |
| Jailer (if `TBE_FC_REQUIRE_JAILER=1`, default on) | `TBE_JAILER_BIN` / `jailer` |
| Kernel file | `TBE_FC_KERNEL` exists |
| Rootfs file | `TBE_FC_ROOTFS` exists |
| Network for FC | `TBE_FC_AUTO_NET=1` or `TBE_FC_TAP` or `TBE_FC_NETNS` (unless `TBE_FC_ALLOW_NO_NET`) |
| `TBE_FC_TOKEN_IN_BOOTARGS` must be 0 in production | Token must not sit in boot args |

Worker bootstrap (`hosting/worker.py`) additionally requires Postgres + Firecracker probe success before accepting work.

---

## 5. Lifecycle operations (current surface)

| Operation | Surface |
|-----------|---------|
| start | `HostingService.start`, tool `host_start`, API `hosts` start, bot `hosting_router` |
| stop | `HostingService` stop path, tool `host_stop` |
| status | `HostingService.status`, tool `host_status` |
| diagnose | via Error Intelligence on failure logs |

Scale mode: API/host start **enqueues** (`deploy_queue` / `pg_deploy_queue`); workers claim jobs, fetch **artifacts**, build/run on node with capacity (`fleet` + `capacity`, target 20k+ bots model).

---

## 6. Platforms (generation scaffolds vs hosting)

Scaffolds exist under `lumen/engine/services/platform_generators/`:

- `telegram` (default)  
- `whatsapp` (Cloud API webhook pattern)  
- `discord`  
- `web` (minimal stub)

**Contract gap (documented, not fixed in Phase 0):**  
`HostInstance` has **no first-class `platform` field** yet. Permanent hosting lifecycle is implemented generically around project path + token; platform-specific webhook registration and egress allowlists are not fully unified in the Hosting plane. Later phases must extend the contract without breaking existing Telegram permanent host.

---

## 7. Billing / quotas (from code)

- `lumen/platform/plans.py`: plans system **removed**; credits-only shim. `hosted_bots` on default profile is effectively unlimited (`10**9`); real gating is **credits** + balance lifecycle.  
- API host start: `reserve_for_hosting` + `is_hosting_allowed`.  
- Per-user process cap in scale mode: `TBE_MAX_BOTS_PER_USER` (default 50).

---

## 8. Security invariants (must not weaken)

1. Never store raw bot tokens in state — `token_fp` only; seal with `TBE_TOKEN_SECRET`.  
2. Project path always under `user_sandbox` for that `user_id` / tenant.  
3. Production multi-tenant: no LocalProcess, no silent fallback to weak backends.  
4. SQLite hosting state forbidden outside dev.  
5. Market gate refuses “weak hosting” for commercial sale.  
6. Egress: Docker bridge network + host firewall hints (Telegram endpoints documented); FC uses TAP/netns.

---

## 9. Entry points map

| Entry | Module |
|-------|--------|
| Telegram NL “استضف” | `lumen/bot/routers/hosting_router.py` |
| Tools | `host_start` / `host_stop` / `host_status` in `tool_runtime` |
| B2B API | `lumen/api/routes/hosts.py` |
| Worker node | `python -m lumen.engine.services.hosting.worker` |
| Isolation select | `sandbox_runtime.select` + `isolation_policy` |
| Trial only | `live_runner` (not PERMANENT_HOST) |

---

## 10. Phase 0 acceptance criteria

- [x] TRIAL_CHAT vs PERMANENT_HOST documented from module docstrings and call sites.  
- [x] `HostInstance` field contract tabulated from code.  
- [x] Persistence split (SQLite dev / Postgres prod) documented.  
- [x] Ordered start gates listed from `HostingService.start` + API.  
- [x] Full market_gate and isolation production rules listed.  
- [x] Known gap: no first-class `platform` on `HostInstance` — deferred to Phase 2.  
- [x] No runtime behavior change in Phase 0.

**Next phase (1):** Wire post-generation delivery to PERMANENT_HOST only (no LiveRunner substitute), enforce credits/sandbox gates already present, tests, commit, push.

---

## 11. Non-goals for Phase 0

- No new orchestrator.  
- No replacement of Firecracker.  
- No deletion of LiveRunner (still required for trial).  
- No platform field migration yet.  
- No weak “works on my machine” hosting path.


## HostInstance extended fields (root hardening)

| Field | Purpose |
|-------|---------|
| `public_base_url` | Stable ingress URL (`{instance_id}.{TBE_HOST_BASE_DOMAIN}`) — Traefik/Caddy by name, not random ports |
| `webhook_public_url` | `https://…/v1/hooks/telegram/{instance_id}` when TBE_PUBLIC_API_BASE or domain set |
| `internal_port` | Deterministic logical port 8000–8999 for reverse-proxy backends |
| `version_ref` | Git commit of project snapshot at deploy time |
| `last_health_at` | Unix time of last successful orchestrator health probe (~30s loop) |

Production isolation remains **Firecracker only**. Docker is dev-only and still uses seccomp profiles when selected.
