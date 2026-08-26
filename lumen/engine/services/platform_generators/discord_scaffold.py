"""Discord bot scaffold — discord.py (official library patterns)."""
from __future__ import annotations

from pathlib import Path

HANDLERS = '''"""Discord event handlers."""
from __future__ import annotations

import discord
from discord.ext import commands


class Core(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        print(f"logged in as {self.bot.user}")

    @commands.command(name="ping")
    async def ping(self, ctx: commands.Context) -> None:
        await ctx.send("pong")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        # Default echo for demos — replace with product logic
        if message.content and not message.content.startswith("!"):
            await message.channel.send(message.content)
'''

MAIN = '''#!/usr/bin/env python3
"""Discord bot entry (discord.py)."""
from __future__ import annotations

import asyncio
import logging
import os

import discord
from discord.ext import commands

from app.handlers import Core

logging.basicConfig(level=logging.INFO)
TOKEN = os.environ.get("DISCORD_BOT_TOKEN") or os.environ.get("BOT_TOKEN") or ""


async def _amain() -> None:
    if not TOKEN:
        raise SystemExit("Set DISCORD_BOT_TOKEN")
    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix="!", intents=intents)
    await bot.add_cog(Core(bot))
    await bot.start(TOKEN)


def main() -> None:
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
'''


def write_discord(root: Path) -> list[str]:
    written: list[str] = []
    (root / "app").mkdir(parents=True, exist_ok=True)
    files = {
        "main.py": MAIN,
        "app/__init__.py": '"""App package."""\n',
        "app/handlers.py": HANDLERS,
        "requirements.txt": "discord.py>=2.3.0\n",
        ".env.example": "DISCORD_BOT_TOKEN=\nBOT_TOKEN=\n",
        "README.md": "# Discord bot\n\n```bash\nexport DISCORD_BOT_TOKEN=...\npython main.py\n```\n\nEnable Message Content Intent in the Discord developer portal.\n",
    }
    for rel, content in files.items():
        path = root / rel
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            written.append(rel)
    (root / "PLATFORM.md").write_text(
        "platform: discord\nruntime: discord.py\n", encoding="utf-8"
    )
    written.append("PLATFORM.md")
    return written
