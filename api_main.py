"""Entry: B2B API server only."""
from __future__ import annotations

import os
import sys


def _boot_secrets() -> None:
    """Dev: optional .env. Production: managed secrets only (no .env file)."""
    from lumen.platform.secrets_provider import (
        assert_critical_secrets_present,
        load_dotenv_if_dev,
        load_secrets_into_environ,
    )

    load_dotenv_if_dev()
    meta = load_secrets_into_environ(only_missing=True)
    assert_critical_secrets_present()
    # meta keys only — never values
    print(
        f"secrets_boot source={meta.get('source')} injected={meta.get('injected')}",
        file=sys.stderr,
    )


try:
    _boot_secrets()
except Exception as exc:
    sys.stderr.write(f"FATAL secrets: {exc}\n")
    raise SystemExit(2) from exc

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
