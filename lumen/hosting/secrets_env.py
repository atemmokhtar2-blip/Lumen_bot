"""Sealed project secrets — never leave bot tokens as plaintext .env on disk.

Uses existing AES-256-GCM sealing (crypto_tokens.seal_token / unseal_token).
Writes ``.lumen_secrets.sealed`` next to the project; runtime injects env from
memory after unseal (prepare_runtime / host start), not from world-readable .env.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger("tbe.hosting.secrets_env")

SEALED_NAME = ".lumen_secrets.sealed"


def seal_project_secrets(project_path: Path | str, secrets: dict[str, str]) -> Path:
    """Encrypt secret map into project_path/.lumen_secrets.sealed."""
    root = Path(project_path).resolve()
    root.mkdir(parents=True, exist_ok=True)
    from lumen.engine.services.crypto_tokens import seal_token

    payload = {str(k): str(v) for k, v in (secrets or {}).items() if k and v}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    sealed = seal_token(raw, aad=b"project_secrets")
    out = root / SEALED_NAME
    out.write_text(sealed, encoding="utf-8")
    try:
        os.chmod(out, 0o600)
    except Exception:
        pass
    # Scrub plaintext BOT_TOKEN from any existing .env
    env_path = root / ".env"
    if env_path.is_file():
        try:
            lines = []
            for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                key = line.split("=", 1)[0].strip().upper() if "=" in line else ""
                if key in {"BOT_TOKEN", "TELEGRAM_BOT_TOKEN", "DISCORD_TOKEN", "TOKEN"}:
                    lines.append(f"{key}=__SEALED__")
                else:
                    lines.append(line)
            env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            os.chmod(env_path, 0o600)
        except Exception:
            logger.warning("failed to scrub .env secrets in %s", root)
    return out


def load_project_secrets(project_path: Path | str) -> dict[str, str]:
    """Unseal project secrets; empty dict if missing."""
    path = Path(project_path).resolve() / SEALED_NAME
    if not path.is_file():
        return {}
    try:
        from lumen.engine.services.crypto_tokens import unseal_token

        raw = unseal_token(path.read_text(encoding="utf-8").strip(), aad=b"project_secrets")
        if not raw:
            return {}
        data = json.loads(raw)
        return {str(k): str(v) for k, v in data.items() if k and v}
    except Exception as exc:
        logger.warning("unseal project secrets failed: %s", type(exc).__name__)
        return {}


def inject_secrets_env(project_path: Path | str, base: dict[str, str] | None = None) -> dict[str, str]:
    """Merge sealed secrets into env dict for sandbox start."""
    env = dict(base or {})
    sealed = load_project_secrets(project_path)
    for k, v in sealed.items():
        env.setdefault(k, v)
    return env


__all__ = [
    "SEALED_NAME",
    "seal_project_secrets",
    "load_project_secrets",
    "inject_secrets_env",
]
