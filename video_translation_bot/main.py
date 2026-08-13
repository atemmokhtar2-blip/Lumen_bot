from __future__ import annotations

import asyncio
import logging

from .config.settings import get_settings
from .telegram.app import TelegramVideoBot


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = get_settings()
    asyncio.run(TelegramVideoBot(settings).run())


if __name__ == "__main__":
    main()
