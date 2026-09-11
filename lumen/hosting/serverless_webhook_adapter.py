"""Serverless webhook adapter — prepare Telegram bots for Lumen serverless host.

Phase 2:
  detect framework + polling/webhook → generate api/index.py + platform config
  BOT_TOKEN only from environment (never written into generated files)
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("lumen.hosting.serverless_webhook_adapter")

FRAMEWORK_PTB = "python-telegram-bot"
FRAMEWORK_AIOGRAM = "aiogram"
FRAMEWORK_TELEBOT = "telebot"
FRAMEWORK_UNKNOWN = "unknown"
FRAMEWORK_ALREADY = "already_serverless"

MODE_POLLING = "polling"
MODE_WEBHOOK = "webhook"
MODE_UNKNOWN = "unknown"

_ADAPTER_MARKER = "LUMEN_SERVERLESS_WEBHOOK_ADAPTER_V1"
_TEMPLATE_PATH = Path(__file__).resolve().parent / "serverless_handler_template.py.txt"


@dataclass
class DetectResult:
    framework: str = FRAMEWORK_UNKNOWN
    mode: str = MODE_UNKNOWN
    entry_point: str = ""
    evidence: list[str] = field(default_factory=list)
    already_adapted: bool = False


@dataclass
class AdaptResult:
    ok: bool
    message: str = ""
    detect: DetectResult = field(default_factory=DetectResult)
    files_written: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    webhook_path: str = "/api"


def _read_py_corpus(root: Path, limit_files: int = 40) -> tuple[str, list[str]]:
    texts: list[str] = []
    names: list[str] = []
    for p in sorted(root.rglob("*.py")):
        if any(x in p.parts for x in (".git", ".venv", "venv", "__pycache__", ".tbe_host_deps")):
            continue
        try:
            chunk = p.read_text(encoding="utf-8", errors="ignore")[:20000]
        except Exception:
            continue
        texts.append(chunk)
        names.append(str(p.relative_to(root)).replace("\\", "/"))
        if len(names) >= limit_files:
            break
    return "\n".join(texts), names


def detect_project(root: Path, *, entry_hint: str = "") -> DetectResult:
    root = root.resolve()
    evidence: list[str] = []
    entry = (entry_hint or "").strip().replace("\\", "/")

    api_index = root / "api" / "index.py"
    platform_cfg = root / "vercel.json"
    if api_index.is_file():
        try:
            api_txt = api_index.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            api_txt = ""
        if _ADAPTER_MARKER in api_txt or platform_cfg.is_file():
            return DetectResult(
                framework=FRAMEWORK_ALREADY,
                mode=MODE_WEBHOOK,
                entry_point=entry,
                evidence=["api/index.py"],
                already_adapted=True,
            )

    corpus, files = _read_py_corpus(root)
    low = corpus.lower()

    framework = FRAMEWORK_UNKNOWN
    if "aiogram" in low or "from aiogram" in corpus:
        framework = FRAMEWORK_AIOGRAM
        evidence.append("aiogram_import")
    elif "telegram.ext" in corpus or "Application.builder" in corpus or "python-telegram-bot" in low:
        framework = FRAMEWORK_PTB
        evidence.append("ptb_markers")
    elif "telebot" in low or "import telebot" in corpus or "from telebot" in corpus:
        framework = FRAMEWORK_TELEBOT
        evidence.append("telebot_import")

    mode = MODE_UNKNOWN
    polling_hits = [p for p in (r"run_polling\s*\(", r"start_polling\s*\(", r"\.polling\s*\(", r"infinity_polling\s*\(") if re.search(p, corpus)]
    webhook_hits = [p for p in (r"run_webhook\s*\(", r"set_webhook\s*\(", r"setWebhook", r"process_update\s*\(", r"feed_update\s*\(") if re.search(p, corpus)]

    if polling_hits and not webhook_hits:
        mode = MODE_POLLING
        evidence.extend(polling_hits[:3])
    elif webhook_hits and not polling_hits:
        mode = MODE_WEBHOOK
        evidence.extend(webhook_hits[:3])
    elif polling_hits and webhook_hits:
        mode = MODE_POLLING
        evidence.append("mixed_polling_webhook")
    elif framework != FRAMEWORK_UNKNOWN:
        evidence.append("framework_without_mode")

    if not entry:
        for cand in ("main.py", "bot.py", "app.py", "run.py"):
            if (root / cand).is_file():
                entry = cand
                break
        if not entry:
            for rel in files:
                if not rel.startswith("api/"):
                    entry = rel
                    break

    return DetectResult(framework=framework, mode=mode, entry_point=entry, evidence=evidence)


def _module_from_entry(entry: str) -> str:
    mod = entry.replace("\\", "/").removesuffix(".py").replace("/", ".")
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_\.]*$", mod):
        return "main"
    return mod


def _adapter_source(*, entry_module: str, framework: str) -> str:
    raw = _TEMPLATE_PATH.read_text(encoding="utf-8")
    return (
        raw.replace("@@MARKER@@", _ADAPTER_MARKER)
        .replace("@@FRAMEWORK@@", framework)
        .replace("@@ENTRY@@", _module_from_entry(entry_module))
    )


def _platform_config() -> dict[str, Any]:
    return {
        "version": 2,
        "builds": [{"src": "api/index.py", "use": "@vercel/python"}],
        "routes": [
            {"src": "/api", "dest": "api/index.py"},
            {"src": "/api/(.*)", "dest": "api/index.py"},
            {"src": "/", "dest": "api/index.py"},
        ],
    }


def _ensure_requirements(root: Path, framework: str) -> str | None:
    req = root / "requirements.txt"
    if framework == FRAMEWORK_AIOGRAM:
        need = "aiogram>=2.25,<4"
        key = "aiogram"
    elif framework == FRAMEWORK_TELEBOT:
        need = "pyTelegramBotAPI>=4.14"
        key = "telebot"
    else:
        need = "python-telegram-bot>=20.0,<22"
        key = "telegram"
    if not req.is_file():
        req.write_text(need + "\n", encoding="utf-8")
        return "requirements.txt"
    text = req.read_text(encoding="utf-8", errors="ignore").lower()
    if key in text or "python-telegram-bot" in text or "aiogram" in text or "pytelegrambotapi" in text:
        return None
    with req.open("a", encoding="utf-8") as f:
        f.write("\n# lumen serverless\n" + need + "\n")
    return "requirements.txt"


def adapt_project_for_serverless(
    project_path: str | Path,
    *,
    entry_point: str = "",
    force: bool = False,
) -> AdaptResult:
    root = Path(project_path).resolve()
    if not root.is_dir():
        return AdaptResult(ok=False, message="مسار المشروع غير موجود")

    det = detect_project(root, entry_hint=entry_point)
    if det.already_adapted and not force:
        return AdaptResult(
            ok=True,
            message="المشروع جاهز لاستضافة Lumen (Webhook)",
            detect=det,
            details={"skipped": "already_adapted"},
            webhook_path="/api",
        )

    entry = (entry_point or det.entry_point or "").strip()
    if not entry:
        return AdaptResult(ok=False, message="لا توجد نقطة دخول للبوت داخل المشروع", detect=det)

    framework = det.framework
    if framework in {FRAMEWORK_UNKNOWN, FRAMEWORK_ALREADY}:
        framework = FRAMEWORK_PTB
        det.evidence.append("defaulted_ptb")

    api_dir = root / "api"
    api_dir.mkdir(parents=True, exist_ok=True)
    (api_dir / "index.py").write_text(_adapter_source(entry_module=entry, framework=framework), encoding="utf-8")
    written = ["api/index.py"]

    (root / "vercel.json").write_text(json.dumps(_platform_config(), indent=2) + "\n", encoding="utf-8")
    written.append("vercel.json")

    req_touched = _ensure_requirements(root, framework)
    if req_touched:
        written.append(req_touched)

    meta = {
        "adapter": _ADAPTER_MARKER,
        "framework": framework,
        "mode_detected": det.mode,
        "entry_point": entry,
        "webhook_path": "/api",
        "evidence": det.evidence[:12],
    }
    (root / ".lumen_serverless.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    written.append(".lumen_serverless.json")

    return AdaptResult(
        ok=True,
        message="تم تجهيز المشروع لاستضافة Lumen عبر Webhook",
        detect=det,
        files_written=written,
        details=meta,
        webhook_path="/api",
    )


__all__ = [
    "DetectResult",
    "AdaptResult",
    "detect_project",
    "adapt_project_for_serverless",
    "FRAMEWORK_PTB",
    "FRAMEWORK_AIOGRAM",
    "FRAMEWORK_TELEBOT",
    "MODE_POLLING",
    "MODE_WEBHOOK",
]
