# Lumen guest agent (permanent hosting)

Required inside the Firecracker rootfs for **PERMANENT_HOST**:

1. Mount project drive at `/project`
2. Mount token drive at `/token` (files `BOT_TOKEN`, `TELEGRAM_BOT_TOKEN`)
3. Run `lumen-guest-boot` or `python3 /project/.lumen_guest/supervisor.py`

The host injects `.lumen_guest/supervisor.py` into every project drive at start time.

## Serial markers (host waits on these)

| Marker | Meaning |
|--------|---------|
| `lumen-guest-ready` | Token + project OK |
| `lumen-bot-started` | Bot process spawned |
| `lumen-bot-fatal` | Unrecoverable |

Production `FirecrackerSandboxBackend.start` fails closed if bot markers do not appear within `TBE_FC_BOT_HEALTH_TIMEOUT` (default 90s).

## Build note

Ship a rootfs where systemd (or busybox init) always starts `lumen-guest-boot` after network is up.
