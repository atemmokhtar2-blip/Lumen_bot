"""Entry: B2B API server only."""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

# Dynamic secrets (Doppler/Vault) after dotenv, before app config
try:
    from lumen.platform.secrets_provider import load_secrets_into_environ

    load_secrets_into_environ(only_missing=True)
except Exception:
    pass

# Observability before any lumen imports that log
try:
    from lumen.platform.observability import setup_observability

    setup_observability(service_name=os.getenv("OTEL_SERVICE_NAME") or "lumen-api")
except Exception:
    import logging

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )


def main() -> None:
    from lumen.api.app import run_api

    run_api()


if __name__ == "__main__":
    main()
