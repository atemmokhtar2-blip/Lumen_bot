"""Entry: B2B API server only."""
from __future__ import annotations

import logging
import os

from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)


def main() -> None:
    from api.app import run_api

    run_api()


if __name__ == "__main__":
    main()
