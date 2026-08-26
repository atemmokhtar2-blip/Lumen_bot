# Sandbox Runtime

## Backends (strongest first)

| Backend | Isolation |
|---------|-----------|
| firecracker | MicroVM + KVM — requires TAP + token path; claims VM process only |
| gvisor | **official Google runsc** — userspace kernel (Sentry) |
| dind | dedicated Docker daemon (`TBE_DIND_HOST`, not host sock) |
| docker | hardened runc + seccomp + AppArmor + egress |

Selection: `TBE_SANDBOX_BACKEND=auto|firecracker|gvisor|dind|docker`  
Default order (auto): firecracker → gvisor → dind → docker.

## gVisor (official Google runsc)

Lumen does **not** reimplement a sandbox kernel. It uses the real
[gVisor](https://gvisor.dev/) OCI runtime `runsc` published by Google.

### Host install (Docker)

```bash
# Official installer (apt repo or GCS release tarball + runsc install)
sudo bash scripts/hosting/install_gvisor.sh

# Verify (must print gVisor banner in dmesg)
docker run --rm --runtime=runsc ubuntu dmesg | head
```

Sources used by the installer (no forks, no mirrors we invent):

- https://gvisor.dev/docs/user_guide/install/
- https://gvisor.dev/docs/user_guide/quick_start/docker/
- Release bits: `https://storage.googleapis.com/gvisor/releases/release/latest/`

After install, Lumen probes `docker info` for a registered `runsc` runtime.
If present, `GVisorSandboxBackend` sets `TBE_DOCKER_RUNTIME=runsc` and starts
generated bots with `--runtime=runsc`.

```bash
# Force gVisor backend
export TBE_SANDBOX_BACKEND=gvisor
# or prefer it under auto
export TBE_PREFER_GVISOR=1
```

### Kubernetes

1. Install `runsc` + `containerd-shim-runsc-v1` on nodes (same script / official guide).
2. Configure containerd handler — see `deploy/k8s/containerd-runsc-snippet.toml`.
3. Apply RuntimeClass:

```bash
kubectl apply -f deploy/k8s/runtimeclass-gvisor.yaml
```

Pods that must run under gVisor:

```yaml
spec:
  runtimeClassName: gvisor
```

Official K8s path: https://gvisor.dev/docs/user_guide/containerd/quick_start/

## Egress (real)

`TBE_EGRESS_MODE=strict` (default):

- DROP: 10/8, 172.16/12, 192.168/16, 169.254/16, 127/8, 100.64/10
- ACCEPT: resolved `api.telegram.org:443` + DNS 53
- DROP other NEW
- **If iptables cannot apply → start fails** (no silent success)

Dev only: `TBE_EGRESS_MODE=baseline`

## Firecracker honesty

- `TBE_FC_TAP` required (or `TBE_FC_ALLOW_NO_NET=1` offline dev)
- Token: `TBE_FC_TOKEN_DRIVE` or `TBE_FC_TOKEN_IN_BOOTARGS=1`
- Message: `vm_process_started` — not Telegram health

## Single run path

```
host_start / worker
  → harden_network (strict)
  → start_sandboxed_bot
  → supervisor_tick (worker loop)
```

No LocalProcess path for generated bots.
