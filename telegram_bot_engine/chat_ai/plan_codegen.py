"""Plan-driven code generation through Hugging Face.

The model receives an execution plan, not raw prose, and returns the complete
file tree. There are no domain templates or fallback placeholder emitters.
"""
from __future__ import annotations

import ast
import json
import os
from pathlib import Path
from typing import Any

from . import multi_provider as mp


_CODE_SYSTEM = r"""You are a senior software engineer shipping a production-ready custom Telegram bot.
The execution plan is the ONLY source of truth. Return ONE JSON object only:
{"files":[{"path":"relative/path","content":"complete file content"}],"notes":["..."]}

## Hard technical constraints (non-negotiable)
1) Framework: python-telegram-bot v21+ ONLY.
   - Use: Application.builder().token(...).post_init(...).build()
   - Use: ContextTypes.DEFAULT_TYPE
   - Use: from telegram.ext import filters  (lowercase). NEVER import Filters.
   - Handlers MUST be async: async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
   - Entry: application.run_polling(allowed_updates=Update.ALL_TYPES)
   - FORBIDDEN APIs (legacy v13): Updater, Dispatcher, CallbackContext, Filters, updater.start_polling, updater.idle
2) Always emit these files even if the plan omitted them:
   - requirements.txt with python-telegram-bot>=21.0,<22 and python-dotenv>=1.0.0 (no stdlib packages like sqlite3)
   - .env.example containing TELEGRAM_BOT_TOKEN=
   - README.md with install + run steps
3) Language: all user-facing strings MUST match the plan language (Arabic if commands/summary/buttons are Arabic).
4) No placeholders: forbid TODO, FIXME, NotImplementedError, ellipsis-only bodies, "not implemented", "coming soon", "Feature not implemented", fake success.
5) Callbacks: every InlineKeyboardButton must be handled by CallbackQueryHandler.
   Always use update.effective_message and update.effective_user (message may be None on callbacks).
6) Conversations: each multi-step command gets its own ConversationHandler and unique state constants.
   Never share one state id across unrelated flows (e.g. done vs delete).
7) Data: if plan asks for sqlite, implement real SQLite with user_id isolation, empty-list messages, and ID validation.
   Validate enums (e.g. priority high/medium/low) before save.
8) Architecture: follow planned modules (handlers/services/models/repositories). Imports must match paths.
9) Every required path from the plan must be present with complete content. Every .py file must parse.
10) Secrets only from environment variables.

Implement every command, button, flow, entity field, and service from the plan completely.
"""

def _extract_json(text: str) -> dict[str, Any] | None:
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except Exception:
        start, end = (text or "").find("{"), (text or "").rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            value = json.loads(text[start:end + 1])
            return value if isinstance(value, dict) else None
        except Exception:
            return None


def _validate_files(files: Any) -> tuple[list[dict[str, str]], list[str]]:
    errors: list[str] = []
    clean: list[dict[str, str]] = []
    forbidden = (
        "NotImplementedError",
        "TODO",
        "FIXME",
        "pass\n",
        "...\n",
        "Reserved path",
        "fake",
        "not implemented",
        "Not implemented",
        "coming soon",
        "Feature not implemented",
    )
    legacy_ptb = (
        "Updater(",
        "updater.dispatcher",
        "CallbackContext",
        "from telegram.ext import Filters",
        "Filters.text",
        "Filters.command",
        "updater.start_polling",
        "updater.idle",
    )
    paths_seen: set[str] = set()
    for item in files if isinstance(files, list) else []:
        if not isinstance(item, dict) or not item.get("path") or not isinstance(item.get("content"), str):
            errors.append("invalid_file_record")
            continue
        path = str(item["path"]).replace("\\", "/")
        if path.startswith("/") or ".." in Path(path).parts:
            errors.append(f"unsafe_path:{path}")
            continue
        content = item["content"]
        if not content.strip():
            # Package markers may arrive empty from the model — normalize instead of failing.
            if path.endswith("__init__.py"):
                content = '"""Package marker."""\n'
            else:
                errors.append(f"empty_file:{path}")
        low = content.lower()
        if any(marker in content for marker in forbidden):
            errors.append(f"placeholder_marker:{path}")
        if path.endswith(".py"):
            try:
                ast.parse(content, filename=path)
            except SyntaxError as exc:
                errors.append(f"syntax:{path}:{exc.msg}")
            if any(tok in content for tok in legacy_ptb):
                errors.append(f"legacy_ptb_v13_api:{path}")
            if "Application" not in content and ("CommandHandler" in content or "run_polling" in content):
                # entry/handlers should use Application in v21 style when registering handlers
                if path.endswith("main.py") or path.endswith("bot.py") or path == "main.py":
                    errors.append(f"missing_application_v21:{path}")
        if path.endswith("requirements.txt"):
            if "python-telegram-bot" not in content:
                errors.append("requirements_missing_ptb")
            if "sqlite3" in content.splitlines() or content.strip() == "sqlite3":
                errors.append("requirements_has_stdlib_sqlite3")
        paths_seen.add(path)
        clean.append({"path": path, "content": content})
    if not clean:
        errors.append("no_files_returned")
    # soft essentials: warn via errors only when completely missing entry-ish file
    if clean and not any(
        p.endswith("main.py") or p.endswith("bot.py") or p == "main.py" for p in paths_seen
    ):
        errors.append("missing_entry_file")
    return clean, list(dict.fromkeys(errors))



def generate_project_from_plan(plan: dict[str, Any], out_dir: str | Path, *, timeout: int = 240) -> dict[str, Any]:
    if not mp.any_enabled():
        return {"ok": False, "errors": ["No AI provider configured (OPENAI_API_KEY and/or HF_TOKEN)"], "files": []}
    # Always require runnable essentials regardless of plan gaps
    essentials = ["main.py", "requirements.txt", ".env.example", "README.md"]
    plan_files = [x for x in (plan.get("files") or []) if isinstance(x, dict) and x.get("path")]
    existing_paths = {str(x.get("path")).replace("\\", "/") for x in plan_files}
    for path in essentials:
        if path not in existing_paths:
            plan_files.append({"path": path, "purpose": "runtime essential", "required": True, "dependencies": []})
            existing_paths.add(path)
    # Force framework constraints into plan copy for the model
    plan = dict(plan)
    plan["files"] = plan_files
    arch = dict(plan.get("architecture") or {})
    arch["framework"] = "python-telegram-bot"
    arch["ptb_version"] = "21+"
    plan["architecture"] = arch
    hc = list(plan.get("hard_constraints") or [])
    for c in (
        "python-telegram-bot v21+ only (Application, ContextTypes, filters)",
        "no legacy Updater/Filters/CallbackContext",
        "user-facing language must match plan.language",
        "no TODO/NotImplemented placeholders",
    ):
        if c not in hc:
            hc.append(c)
    plan["hard_constraints"] = hc
    required = []
    for x in plan_files:
        if not x.get("required", True):
            continue
        path = str(x.get("path") or "").replace("\\", "/").strip()
        if not path or path.endswith("/"):
            continue  # directories are not files
        if "." not in Path(path).name and not path.endswith(".py"):
            # skip bare package dirs like handlers, services, models
            continue
        required.append(path)
    prompt = (
        "IMPLEMENTATION PLAN:\n" + json.dumps(plan, ensure_ascii=False, indent=2) +
        "\n\nRequired paths must be present: " + json.dumps(required, ensure_ascii=False) +
        "\n\nCRITICAL: Use python-telegram-bot v21+ async Application API only. "
        "Match user-facing language to plan.language. Implement every button callback."
    )
    try:
        content, model = mp.chat(
            [{"role": "system", "content": _CODE_SYSTEM}, {"role": "user", "content": prompt[:90000]}],
            timeout=timeout,
            max_tokens=int(
                os.environ.get(
                    "CODEGEN_MAX_TOKENS",
                    os.environ.get("HF_CODEGEN_MAX_TOKENS", "16000"),
                )
            ),
            temperature=0.0,
            json_mode=True,
        )
    except Exception as exc:
        return {"ok": False, "errors": [f"codegen_failed:{type(exc).__name__}:{exc}"[:1200]], "files": []}
    payload = _extract_json(content)
    if payload is None:
        return {"ok": False, "errors": ["hf_codegen_json_parse_failed"], "files": [], "model": model}
    files, errors = _validate_files(payload.get("files"))
    returned = {f["path"] for f in files}
    missing = [p for p in required if p not in returned]
    errors.extend(f"missing_required_file:{p}" for p in missing)
    if errors:
        return {"ok": False, "errors": list(dict.fromkeys(errors)), "files": files, "model": model, "notes": payload.get("notes") or []}
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for item in files:
        path = root / item["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(item["content"].replace("\r\n", "\n").rstrip() + "\n", encoding="utf-8")
        written.append(str(path))
    return {"ok": True, "errors": [], "files": written, "model": model, "notes": payload.get("notes") or []}


__all__ = ["generate_project_from_plan"]
