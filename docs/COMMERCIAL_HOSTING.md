# Commercial hosting — workers + managed Postgres + registry + network

## Architecture
User → API bot → Postgres queue → Worker fleet → Registry images → Egress network → Telegram

## Managed Postgres
```bash
export TBE_DATABASE_URL='postgresql://user:pass@host:5432/tbe?sslmode=require'
python scripts/hosting/bootstrap_control_plane.py
```

## Registry
```bash
export TBE_DOCKER_REGISTRY=ghcr.io/your-org
export TBE_REGISTRY_USER=...
export TBE_REGISTRY_PASSWORD=...
export TBE_DOCKER_PUSH=1
```

## Network
```bash
export TBE_DOCKER_NETWORK=tbe-egress
# Firewall: allow DNS + api.telegram.org:443 only
```

## Workers
```bash
export TBE_NODE_ID=node-1
export TBE_NODE_MAX_BOTS=250
export TBE_SCALE_MODE=1
export TBE_MARKET_GATE=1
python -m telegram_bot_engine.services.hosting.worker
```

20k bots ≈ 80 nodes × 250 bots/node.

## Local compose
```bash
docker compose -f deploy/commercial/docker-compose.yml up -d
```


## Artifacts (required for multi-node)
At enqueue the API packages source (no secrets) into an artifact.
Workers download it — they do **not** need the API disk.

```bash
# Shared NFS/EFS across API + workers (simple)
export TBE_ARTIFACT_ROOT=/mnt/tbe-artifacts

# Or S3/R2
export TBE_S3_BUCKET=...
export TBE_S3_ENDPOINT=...
export TBE_S3_ACCESS_KEY=...
export TBE_S3_SECRET_KEY=...
```
