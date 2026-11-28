# Tenant isolation rollout and legacy-state migration

This change introduces namespaced principals and tenant-specific storage. It must not be treated as a production-ready migration until the legacy-state rollout gates below are completed.

## Identity model

- Telegram principal: `telegram:<telegram_user_id>`
- B2B principal: `tenant:<tenant_id>`
- `AgentState.user_id` remains a compatibility/numeric field. It is not an ownership boundary.
- New Telegram AgentState objects default to the Telegram namespace. Deserialized records without a principal are assigned `legacy:user:<id>` and remain quarantined.
- HITL confirmation HMACs and one-time execution grants bind the full principal ID in addition to the numeric user ID, action, state, tool, expiry, and parameters.

## New storage boundaries

- PostgreSQL blackboard queries use `principal_id`; state ownership is immutable across user and principal.
- Tenant sandbox paths use the full SHA-256 digest of the tenant ID. Numeric tenant surrogates are not filesystem keys.
- Host Redis instance records and user indexes use separate, digest-based tenant namespaces. Tenant-bound records are not written to flat Telegram keys.
- Public host slugs include a tenant digest suffix so identical project names cannot claim the same path/subdomain URL across tenants.
- Firecracker state is stored under tenant/user-specific directories. Lifecycle operations require owner context and do not fall back to a shared root.

## Legacy data treatment

### PostgreSQL AgentState

The schema migration moves records with an empty principal into `legacy:user:<id>`. Telegram lookups do not fall back to this namespace. Do not bulk-relabel legacy rows as Telegram or B2B based only on numeric user ID. Relabel only when an authoritative record proves the original provider and owner.

### File blackboard

Old index entries without principal metadata remain addressable only through the explicit legacy namespace. Do not automatically expose them to Telegram.

### Host Redis records

Old tenant records may exist in flat keys or keys built from the previous lossy tenant slug. New code intentionally does not read those keys. Rebuild the new digest-based tenant indexes from the authoritative HostingStateStore/PostgreSQL records, checking exact tenant ownership before writing. Never copy a flat record into a tenant namespace based only on numeric user ID.

### Tenant sandboxes

Old B2B directories may exist under numeric user paths. The new tenant sandbox path is keyed by the full tenant digest. Copy project data only after verifying the exact tenant ID against the authoritative project/tenant registry. Do not automatically adopt a numeric directory: collisions cannot be ruled out.

### Public host routes

New public URLs and reverse-proxy routes include a tenant digest suffix in the slug. Existing unscoped slugs may collide across tenants; inventory them before rollout and resolve collisions before remapping ingress routes.

### Firecracker VMs

Older VM metadata may be in the shared Firecracker state root and may not contain `tenant_id`. The new per-tenant state path intentionally does not guess ownership for such metadata. Before production rollout, either stop/drain these VMs and recreate them under the new namespace, or implement and test a migration that maps each deployment ID to an authoritative HostInstance tenant record. Never assign an untagged VM to a tenant based only on its numeric user ID.

## Required rollout gates

1. Back up PostgreSQL, Redis, sandbox storage, and Firecracker state.
2. Produce a dry-run report mapping every legacy host/deployment/project to an exact tenant ID from authoritative records.
3. Resolve ambiguous or orphaned records manually; do not guess.
4. Migrate Redis indexes and sandbox directories with checksums and a rollback snapshot.
5. Drain or safely migrate Firecracker VMs, verifying owner metadata and stop/status/log access after migration.
6. Run the tenant isolation, cross-principal HITL, Redis namespace, filesystem containment, Firecracker lifecycle, PostgreSQL durability, DAST, and supply-chain suites.
7. Verify tenant A cannot list, read, stop, restart, diagnose, or delete tenant B's resources even when their numeric surrogate IDs match.

Until these gates are satisfied, keep the pull request in Draft and do not merge it into `Lumen`.
