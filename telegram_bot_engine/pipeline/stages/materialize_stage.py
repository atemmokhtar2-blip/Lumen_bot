"""
Materialize stage — writes planned folders and files to disk.

Upstream engines (structure generator, file planner, class generation, …)
produce *plans and reports*.  This stage is the bridge that turns those
artefacts into a real project tree under ``context.work_dir`` using the
shared :class:`DirectoryBuilder` and :class:`FileBuilder`.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple

from ...builders.directory_builder import DirectoryBuilder
from ...builders.file_builder import FileBuilder
from ...core.context import GenerationContext
from ...core.result import StageResult
from ..base_stage import BaseStage
from .feature_codegen import (
    build_feature_module,
    build_ptb_main,
    collect_features,
    resolve_start_reply,
)


def _detect_framework(request: str, blueprint: Any) -> str:
    """Pick telegram framework from request text or blueprint identity."""
    text = (request or "").lower()
    if "aiogram" in text:
        return "aiogram"
    if "pyrogram" in text:
        return "pyrogram"
    if "telethon" in text:
        return "telethon"
    # Blueprint may carry identity.framework or meta.framework
    for attr in ("identity", "meta"):
        obj = getattr(blueprint, attr, None) if blueprint is not None else None
        if obj is not None:
            fw = str(getattr(obj, "framework", "") or "").lower()
            if fw:
                if "aiogram" in fw:
                    return "aiogram"
                if "pyrogram" in fw:
                    return "pyrogram"
                if "telethon" in fw:
                    return "telethon"
                if "python-telegram" in fw or fw == "ptb":
                    return "python-telegram-bot"
    return "python-telegram-bot"


def _extract_start_reply(request: str) -> str:
    """Best-effort extract of the /start reply text from the user request."""
    if not request:
        return "Hello World"
    # Quoted string after /start
    m = re.search(
        r"""/start[^\"'\n]{0,80}[\"']([^\"']+)[\"']""",
        request,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        return m.group(1).strip() or "Hello World"
    # Line after يرسل / sends / replies
    m = re.search(
        r"""(?:يرسل|send|replies?|reply)\s*[:：]?\s*[\"']?([^\n\"']+)[\"']?""",
        request,
        re.IGNORECASE,
    )
    if m:
        candidate = m.group(1).strip().strip("-•* ")
        if candidate and len(candidate) < 120 and "/start" not in candidate.lower():
            return candidate
    if re.search(r"hello\s*world", request, re.IGNORECASE):
        return "Hello World"
    if "هاي" in request:
        return "هاي"
    return "Hello World"


def _project_name(request: str, blueprint: Any) -> str:
    for attr in ("identity", "meta"):
        obj = getattr(blueprint, attr, None) if blueprint is not None else None
        if obj is not None:
            name = str(getattr(obj, "name", "") or "").strip()
            if name:
                return re.sub(r"[^a-zA-Z0-9_]+", "_", name).strip("_") or "telegram_bot"
    return "telegram_bot"


def _content_for_file(
    path: str,
    *,
    request: str,
    framework: str,
    project_name: str,
    start_reply: str,
    class_sources: Dict[str, str],
    features: Optional[List[str]] = None,
) -> str:
    """Produce file content for a planned path."""
    norm = path.replace("\\", "/").lstrip("./")
    base = norm.split("/")[-1].lower()
    features = features or []

    # Prefer generated class skeletons when path matches.
    if norm in class_sources and class_sources[norm].strip():
        return class_sources[norm]
    for key, src in class_sources.items():
        if key.endswith(base) and src.strip():
            return src

    if base in ("requirements.txt", "requirements-dev.txt"):
        if framework == "aiogram":
            return "aiogram>=3.4,<4.0\npython-dotenv>=1.0,<2.0\n"
        if framework == "pyrogram":
            return "pyrogram>=2.0,<3.0\ntgcrypto>=1.2,<2.0\npython-dotenv>=1.0,<2.0\n"
        if framework == "telethon":
            return "telethon>=1.34,<2.0\npython-dotenv>=1.0,<2.0\n"
        return "python-telegram-bot>=21.0,<22.0\npython-dotenv>=1.0,<2.0\n"

    if base in (".env.example", ".env.sample"):
        return "BOT_TOKEN=your_telegram_bot_token_here\n"

    if base in ("readme.md", "readme.rst", "readme.txt"):
        return (
            f"# {project_name}\n\n"
            f"Generated Telegram bot ({framework}).\n\n"
            f"## Setup\n\n"
            f"1. Copy `.env.example` to `.env` and set `BOT_TOKEN`.\n"
            f"2. `pip install -r requirements.txt`\n"
            f"3. `python main.py`\n\n"
            f"## Behaviour\n\n"
            f"- `/start` → `{start_reply}`\n"
        )

    if base in ("config.py", "settings.py"):
        return (
            '"""Runtime configuration loaded from environment."""\n'
            "from __future__ import annotations\n\n"
            "import os\n"
            "from dotenv import load_dotenv\n\n"
            "load_dotenv()\n\n"
            "BOT_TOKEN = os.getenv(\"BOT_TOKEN\", \"\").strip()\n"
            "\n"
            "if not BOT_TOKEN:\n"
            "    raise RuntimeError(\n"
            "        \"BOT_TOKEN is missing. Set it in the environment or .env file.\"\n"
            "    )\n"
        )

    if base in ("main.py", "bot.py", "app.py", "__main__.py"):
        # Feature-aware entry point (uses analysis/blueprint features)
        if framework in ("python-telegram-bot", "ptb") or framework not in (
            "aiogram",
            "pyrogram",
            "telethon",
        ):
            return build_ptb_main(start_reply, features)
        return _main_module(framework, start_reply)

    if base == "__init__.py":
        return '"""Package init."""\n'

    if base.endswith(".py"):
        stem = base[:-3]
        rich = build_feature_module(stem)
        if rich:
            return rich
        class_name = "".join(p.capitalize() for p in re.split(r"[_\-]+", stem) if p)
        return (
            f'"""{stem} module."""\n'
            f"from __future__ import annotations\n\n\n"
            f"class {class_name or 'Module'}:\n"
            f"    \"\"\"Auto-generated placeholder.\"\"\"\n\n"
            f"    def run(self) -> None:\n"
            f"        pass\n"
        )

    if base.endswith((".yml", ".yaml")):
        return f"# {norm}\n"
    if base.endswith(".json"):
        return "{}\n"
    if base.endswith(".toml"):
        return f"# {norm}\n"
    return f"# {norm}\n"


def _main_module(framework: str, start_reply: str) -> str:
    reply_lit = repr(start_reply)
    if framework == "aiogram":
        return f'''"""Telegram bot entry point (aiogram)."""
from __future__ import annotations

import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing. Set it in the environment or .env file.")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


@dp.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer({reply_lit})


async def main() -> None:
    logger.info("Starting bot (aiogram polling)...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
'''
    if framework == "pyrogram":
        return f'''"""Telegram bot entry point (pyrogram)."""
from __future__ import annotations

import os

from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.types import Message

load_dotenv()

API_ID = int(os.getenv("API_ID", "0") or "0")
API_HASH = os.getenv("API_HASH", "").strip()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing.")

app = Client("bot", api_id=API_ID or None, api_hash=API_HASH or None, bot_token=BOT_TOKEN)


@app.on_message(filters.command("start"))
async def start(_, message: Message) -> None:
    await message.reply({reply_lit})


if __name__ == "__main__":
    app.run()
'''
    # Default: python-telegram-bot
    return f'''"""Telegram bot entry point (python-telegram-bot)."""
from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing. Set it in the environment or .env file.")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text({reply_lit})


def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    logger.info("Starting bot (polling)...")
    app.run_polling()


if __name__ == "__main__":
    main()
'''


def _collect_paths(context: GenerationContext) -> Tuple[List[str], List[str]]:
    """Return (folder_paths, file_paths) from structure map / file plan."""
    folders: List[str] = []
    files: List[str] = []

    smap = context.get("project_structure_map")
    if smap is not None:
        for folder in getattr(smap, "folders", []) or []:
            p = getattr(folder, "path", None) or (folder.get("path") if isinstance(folder, dict) else None)
            if p:
                folders.append(str(p).replace("\\", "/").strip("/"))
        for fe in getattr(smap, "files", []) or []:
            p = getattr(fe, "path", None) or (fe.get("path") if isinstance(fe, dict) else None)
            if p:
                files.append(str(p).replace("\\", "/").lstrip("/"))

    plan = context.get("file_generation_plan")
    if plan is not None:
        for fe in getattr(plan, "files", []) or []:
            p = getattr(fe, "path", None) or (fe.get("path") if isinstance(fe, dict) else None)
            if p:
                files.append(str(p).replace("\\", "/").lstrip("/"))

    # Always ensure root entrypoints exist (output validators check the root).
    for required in ("main.py", "config.py", "requirements.txt", "README.md", ".env.example"):
        if required not in files:
            files.append(required)

    # Unique preserve order
    def _uniq(items: List[str]) -> List[str]:
        seen: Set[str] = set()
        out: List[str] = []
        for x in items:
            x = x.strip().strip("/")
            if not x or x in seen:
                continue
            seen.add(x)
            out.append(x)
        return out

    folders = _uniq(folders)
    files = _uniq(files)

    # Folders implied by file paths
    for f in files:
        parent = "/".join(f.split("/")[:-1])
        if parent and parent not in folders:
            folders.append(parent)
    folders = _uniq(folders)
    return folders, files


def _class_source_index(context: GenerationContext) -> Dict[str, str]:
    """Map relative paths → generated source from class generation report."""
    index: Dict[str, str] = {}
    report = context.get("class_generation_report")
    if report is None:
        return index
    classes = getattr(report, "classes", None) or getattr(report, "skeletons", None) or []
    if isinstance(report, dict):
        classes = report.get("classes") or report.get("skeletons") or []
    for cls in classes:
        src = getattr(cls, "source_code", None) or (cls.get("source_code") if isinstance(cls, dict) else "") or ""
        path = (
            getattr(cls, "path", None)
            or getattr(cls, "file_path", None)
            or getattr(cls, "location", None)
            or (cls.get("path") if isinstance(cls, dict) else None)
            or (cls.get("file_path") if isinstance(cls, dict) else None)
            or ""
        )
        name = getattr(cls, "name", None) or (cls.get("name") if isinstance(cls, dict) else None) or ""
        if path and src:
            index[str(path).replace("\\", "/").lstrip("/")] = str(src)
        elif name and src:
            index[f"{name}.py"] = str(src)
    return index


class MaterializeStage(BaseStage):
    """Write planned structure and files to ``context.work_dir``."""

    stage_name = "materialize"
    requires: List[str] = []
    provides: List[str] = ["generated_files"]

    def __init__(self) -> None:
        super().__init__()
        self._dirs = DirectoryBuilder()
        self._files = FileBuilder()

    def execute(self, context: GenerationContext) -> StageResult:
        folders, file_paths = _collect_paths(context)
        blueprint = context.get("project_blueprint") or context.blueprint
        framework = _detect_framework(context.request, blueprint)
        project_name = _project_name(context.request, blueprint)
        features = collect_features(context)
        start_reply = resolve_start_reply(
            context.request, features, fallback=_extract_start_reply(context.request)
        )
        class_sources = _class_source_index(context)

        errors: List[str] = []
        warnings: List[str] = []
        created_dirs: List[str] = []
        created_files: List[str] = []

        # 1) Folders
        if folders:
            result = self._dirs.build(context, {"paths": folders})
            if not result.success:
                errors.extend(result.errors or [])
            else:
                created_dirs = list((result.metadata or {}).get("created") or folders)
            warnings.extend(result.warnings or [])

        # 2) Files
        for path in file_paths:
            content = _content_for_file(
                path,
                request=context.request,
                framework=framework,
                project_name=project_name,
                start_reply=start_reply,
                class_sources=class_sources,
                features=features,
            )
            result = self._files.build(
                context,
                {"path": path, "content": content, "overwrite": True},
            )
            if not result.success:
                # Non-fatal for individual files — collect and continue
                warnings.extend(result.errors or [f"Failed to write {path}"])
            else:
                created_files.append(path)

        context.set("generated_files", list(context.created_files))
        context.set(
            "materialize_report",
            {
                "framework": framework,
                "project_name": project_name,
                "folders": created_dirs,
                "files": created_files,
                "start_reply": start_reply,
                "features": features,
            },
        )

        if not created_files:
            return StageResult.failed(
                self.name,
                errors=errors or ["No files were materialized."],
                warnings=warnings,
            )

        return StageResult.ok(
            self.name,
            outputs={
                "files": created_files,
                "folders": created_dirs,
                "framework": framework,
            },
            warnings=warnings,
            metadata={
                "file_count": len(created_files),
                "folder_count": len(created_dirs),
                "framework": framework,
            },
        )


__all__ = ["MaterializeStage"]
