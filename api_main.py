"""Entry: B2B API server only."""
from __future__ import annotations

import os
import sys


def _boot_secrets() -> None:
    from lumen.platform.secrets_provider import (
        assert_critical_secrets_present,
        install_secret_access_bridge,
        load_dotenv_if_dev,
        load_secrets,
    )

    load_dotenv_if_dev()
    meta = load_secrets(only_missing=True)
    install_secret_access_bridge()
    assert_critical_secrets_present()
    print(
        f"secrets_boot source={meta.get('source')} stored={meta.get('stored')} "
        f"scrubbed={meta.get('scrubbed_environ')}",
        file=sys.stderr,
    )


try:
    _boot_secrets()
except Exception as exc:
    sys.stderr.write(f"FATAL secrets: {exc}\n")
    raise SystemExit(2) from exc

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
