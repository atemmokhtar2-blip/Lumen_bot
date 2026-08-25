# Sandbox Runtime

## Backends (strongest first)

| Backend | Isolation |
|---------|-----------|
| firecracker | MicroVM + KVM — requires TAP + token path; claims VM process only |
| gvisor | runsc userspace kernel |
| dind | dedicated Docker daemon (`TBE_DIND_HOST`, not host sock) |
| docker | hardened runc + seccomp + AppArmor + egress |

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
