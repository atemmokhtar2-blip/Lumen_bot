"""
LiveRunner — real dependency install + bot process execution + error capture.

Install strategy (robust):
  1) try venv + ensure pip works
  2) if venv/pip broken → pip install --target .tbe_deps (isolated)
  3) surface real pip ERROR lines to the user (no opaque "pip install failed")
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import ast


from .requirements_pip import _extract_missing_modules, _module_to_package, _ensure_packages_in_requirements, _extract_errors

def _write_project_env(root: Path, bot_token: str, token_envs: list[str] | None = None) -> str:
    """Persist token into project .env for dotenv-based bots."""
    token_envs = list(token_envs or [])
    keys = sorted(set(token_envs + [
        "TELEGRAM_BOT_TOKEN", "BOT_TOKEN", "TOKEN", "TG_TOKEN",
        "API_TOKEN", "TELEGRAM_TOKEN",
    ]))
    env_path = root / ".env"
    kept: list[str] = []
    if env_path.exists():
        for ln in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            key = ln.split("=", 1)[0].strip() if "=" in ln else ""
            if key in set(keys) or key == "BOTTOKEN":
                continue
            kept.append(ln)
    for key in keys:
        kept.append(f"{key}={bot_token}")
    env_path.write_text(chr(10).join(kept).strip() + chr(10), encoding="utf-8")
    return f"wrote_env:{env_path.name}:{len(keys)}_keys"



def _inject_entry_bootstrap(entry: Path, bot_token: str) -> str:
    """Force token into os.environ at the top of the entry script."""
    try:
        src = entry.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return f"bootstrap_read_fail:{type(e).__name__}"

    mark_start = "# === TBE_LIVE_BOOTSTRAP"
    mark_end = "# === END TBE_LIVE_BOOTSTRAP ==="
    nl = chr(10)
    block_lines = [
        f"{mark_start} (auto-injected by LiveRunner) ===",
        "import os as _tbe_os",
        f"_tbe_tok = {bot_token!r}",
        "for _tbe_k in ("
        '"TELEGRAM_BOT_TOKEN","BOT_TOKEN","TOKEN","TG_TOKEN",'
        '"API_TOKEN","TELEGRAM_TOKEN","BOTTOKEN"):',
        "    _tbe_os.environ[_tbe_k] = _tbe_tok",
        mark_end,
        "",
    ]
    block = nl.join(block_lines)

    # Remove previous bootstrap if present
    if "TBE_LIVE_BOOTSTRAP" in src:
        src = re.sub(
            r"# === TBE_LIVE_BOOTSTRAP[\s\S]*?# === END TBE_LIVE_BOOTSTRAP ===\n?",
            "",
            src,
            count=1,
        )

    # Keep encoding / future imports first
    lines = src.splitlines(keepends=True)
    insert_at = 0
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if i == 0 and stripped.startswith("#!"):
            insert_at = i + 1
            i += 1
            continue
        if stripped.startswith("coding:") or stripped.startswith("#") and "coding" in stripped:
            insert_at = i + 1
            i += 1
            continue
        if stripped.startswith("from __future__"):
            insert_at = i + 1
            i += 1
            continue
        if stripped == "" or stripped.startswith("#"):
            # skip leading comments/blank after future
            if insert_at > 0:
                i += 1
                continue
        break
        i += 1

    new_src = "".join(lines[:insert_at]) + block + "".join(lines[insert_at:])
    try:
        # syntax check bootstrap injection
        compile(new_src, str(entry), "exec")
        entry.write_text(new_src, encoding="utf-8")
        return f"bootstrap_injected:{entry.name}"
    except SyntaxError as e:
        return f"bootstrap_syntax_fail:{e.lineno}"
    except Exception as e:
        return f"bootstrap_write_fail:{type(e).__name__}"


def _patch_getenv_token_defaults(root: Path, bot_token: str) -> list[str]:
    """Replace os.getenv/environ.get default token strings with the live token."""
    notes: list[str] = []
    # os.getenv("TOKEN", "123:AA...") or os.environ.get('BOT_TOKEN', '...')
    pat = re.compile(
        r"""(?P<prefix>(?:os\.getenv|os\.environ\.get|getenv)\s*\(\s*"""
        r"""(?P<q1>['"])(?:TELEGRAM_BOT_TOKEN|BOT_TOKEN|TOKEN|TG_TOKEN|API_TOKEN|TELEGRAM_TOKEN|BOTTOKEN)(?P=q1)"""
        r"""\s*,\s*)(?P<q2>['"])(?P<val>\d{6,12}:[A-Za-z0-9_-]{20,})(?P=q2)""",
        re.M,
    )
    for path in root.rglob("*.py"):
        if any(x in path.parts for x in (".git", ".venv", ".tbe_venv", ".tbe_deps", "__pycache__")):
            continue
        try:
            src = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if not pat.search(src):
            continue
        src2 = pat.sub(lambda m: f"{m.group('prefix')}{m.group('q2')}{bot_token}{m.group('q2')}", src)
        if src2 != src:
            try:
                path.write_text(src2, encoding="utf-8")
                notes.append(f"patched_getenv_default:{path.relative_to(root)}")
            except Exception:
                pass
    return notes



def _patch_hardcoded_tokens(root: Path, bot_token: str) -> list[str]:
    """Replace obvious hardcoded bot tokens in common config files with the user token."""
    notes: list[str] = []
    token_re = re.compile(r"\d{6,12}:[A-Za-z0-9_-]{30,}")
    assign_re = re.compile(
        r"(?P<prefix>^\s*(?:API_TOKEN|BOT_TOKEN|TELEGRAM_BOT_TOKEN|TOKEN|TG_TOKEN|BOTTOKEN)"
        r"\s*=\s*)(?P<q>['\"])(?P<val>[^'\"]{20,})(?P=q)",
        re.M,
    )
    targets: list[Path] = []
    for name in ("config.py", "settings.py", "bot.py", "main.py", "app.py", "constants.py"):
        p = root / name
        if p.exists():
            targets.append(p)
    for p in root.rglob("*.py"):
        if any(x in p.parts for x in (".git", ".venv", ".tbe_venv", ".tbe_deps", "__pycache__")):
            continue
        if p in targets:
            continue
        if p.name in ("config.py", "settings.py", "constants.py"):
            targets.append(p)
        if len(targets) >= 25:
            break

    for path in targets:
        try:
            src = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        original = src

        def _sub(m: re.Match) -> str:
            return f"{m.group('prefix')}{m.group('q')}{bot_token}{m.group('q')}"

        src2 = assign_re.sub(_sub, src)
        try:
            if path.stat().st_size < 80_000 and token_re.search(src2):
                src2 = token_re.sub(bot_token, src2)
        except Exception:
            pass
        if src2 != original:
            try:
                path.write_text(src2, encoding="utf-8")
                notes.append(f"patched_token:{path.relative_to(root)}")
            except Exception as e:
                notes.append(f"patch_fail:{path.name}:{type(e).__name__}")
    notes.extend(_patch_getenv_token_defaults(root, bot_token)[:8])
    return notes


def _smart_auto_heal(
    root: Path,
    bot_token: str,
    combined_log: str,
    action: str,
) -> list[str]:
    """Apply safe automatic fixes; return heal notes (user is not bothered for fixable issues)."""
    notes: list[str] = []
    log = combined_log or ""
    log_l = log.lower()

    # 1) Webhook / getUpdates conflict → always clear webhook
    if (
        action in ("delete_webhook",)
        or "Conflict" in log
        or "terminated by other getUpdates" in log
        or "can't use getupdates" in log_l
    ):
        ok, msg = _delete_telegram_webhook(bot_token)
        notes.append(f"delete_webhook:{'ok' if ok else 'fail'}:{msg}")

    # 2) Token / Unauthorized → inject env + patch hardcoded + revalidate
    if (
        action in ("check_token", "set_env")
        or "Unauthorized" in log
        or "InvalidToken" in log
        or "TelegramUnauthorizedError" in log
    ):
        try:
            from .source_fix import discover_token_env_names
            notes.append(_write_project_env(root, bot_token, discover_token_env_names(root)))
        except Exception as e:
            notes.append(f"write_env_fail:{type(e).__name__}")
        notes.extend(_patch_hardcoded_tokens(root, bot_token)[:12])
        # Inject bootstrap into entry so config imports cannot override token
        entry = _find_entry(root)
        if entry is not None:
            notes.append(_inject_entry_bootstrap(entry, bot_token))
        ok_wh, msg_wh = _delete_telegram_webhook(bot_token)
        notes.append(f"delete_webhook_after_token:{'ok' if ok_wh else 'fail'}:{msg_wh}")
        ok, _me, err = validate_telegram_token(bot_token)
        if not ok:
            notes.append(f"token_still_invalid:{err}")
            notes.append("user_action_required:new_token_from_BotFather")
        else:
            notes.append("token_revalidated_ok")
            notes.append("will_retry_with_injected_token")

    # 3) Syntax
    if action == "fix_syntax" or "SyntaxError" in log or "IndentationError" in log:
        try:
            from .source_fix import repair_project_sources
            for n in (repair_project_sources(root) or [])[:10]:
                notes.append(f"syntax_repair:{n}")
        except Exception as e:
            notes.append(f"syntax_repair_fail:{type(e).__name__}")

    # 4) Missing requirements.txt + telegram framework detected in sources
    req = root / "requirements.txt"
    if not req.exists() or req.stat().st_size < 3:
        blobs = []
        for name in ("main.py", "bot.py", "app.py"):
            p = root / name
            if p.exists():
                try:
                    blobs.append(p.read_text(encoding="utf-8", errors="ignore")[:8000])
                except Exception:
                    pass
        blob = chr(10).join(blobs)
        pkgs: list[str] = ["python-dotenv"]
        if "aiogram" in blob:
            pkgs.append("aiogram")
        if "telegram" in blob or "python-telegram-bot" in blob:
            pkgs.append("python-telegram-bot")
        if "telebot" in blob or "pyTelegramBotAPI" in blob:
            pkgs.append("pyTelegramBotAPI")
        if "pyrogram" in blob:
            pkgs.append("pyrogram")
        try:
            req.write_text(chr(10).join(pkgs) + chr(10), encoding="utf-8")
            notes.append(f"created_requirements:{','.join(pkgs)}")
        except Exception as e:
            notes.append(f"create_requirements_fail:{type(e).__name__}")

    # 5) Network / DNS soft retry signal
    if action == "check_network" or any(k in log for k in ("ConnectionError", "NameResolutionError", "SSLError")):
        notes.append("network_soft_retry")

    return notes


