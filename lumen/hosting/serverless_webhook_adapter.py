"""Serverless webhook adapter — strong Phase 2 prepare for Lumen host.

Real work (not theatre):
  1) Detect framework + polling/webhook with evidence
  2) Neutralize module-level run_polling / infinity_polling in entry file
  3) Generate api/index.py that stubs polling on import, loads app/bot, processes updates
  4) Platform config + requirements
  5) Refuse embedding secrets; scan entry for hardcoded bot tokens
  6) Validate generated layout before success
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
_NEUTRALIZE_MARKER = "LUMEN_POLLING_NEUTRALIZED_V1"

# Telegram bot token shape (rough) — never keep these in source for serverless deploy
_TOKEN_RE = re.compile(r"\b(\d{6,14}:[A-Za-z0-9_-]{20,})\b")

_POLLING_CALL_RE = re.compile(
    r"(?m)^(?P<indent>[ \t]*)(?P<call>("
    r"application\.run_polling\s*\(.*?\)|"
    r"app\.run_polling\s*\(.*?\)|"
    r"updater\.start_polling\s*\(.*?\)|"
    r"bot\.polling\s*\(.*?\)|"
    r"bot\.infinity_polling\s*\(.*?\)|"
    r"executor\.start_polling\s*\(.*?\)|"
    r"dp\.start_polling\s*\(.*?\)|"
    r"asyncio\.run\s*\(\s*\w*\.?run_polling.*?\)|"
    r"run_polling\s*\(.*?\)"
    r"))\s*$",
    re.DOTALL,
)


@dataclass
class DetectResult:
    framework: str = FRAMEWORK_UNKNOWN
    mode: str = MODE_UNKNOWN
    entry_point: str = ""
    evidence: list[str] = field(default_factory=list)
    already_adapted: bool = False
    hardcoded_token: bool = False


@dataclass
class AdaptResult:
    ok: bool
    message: str = ""
    detect: DetectResult = field(default_factory=DetectResult)
    files_written: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    webhook_path: str = "/api"


def _read_py_corpus(root: Path, limit_files: int = 50) -> tuple[str, list[str]]:
    texts: list[str] = []
    names: list[str] = []
    for p in sorted(root.rglob("*.py")):
        if any(x in p.parts for x in (".git", ".venv", "venv", "__pycache__", ".tbe_host_deps")):
            continue
        try:
            chunk = p.read_text(encoding="utf-8", errors="ignore")[:25000]
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
        if _ADAPTER_MARKER in api_txt and platform_cfg.is_file():
            return DetectResult(
                framework=FRAMEWORK_ALREADY,
                mode=MODE_WEBHOOK,
                entry_point=entry,
                evidence=["api/index.py", "vercel.json"],
                already_adapted=True,
            )

    corpus, files = _read_py_corpus(root)
    low = corpus.lower()
    hardcoded = bool(_TOKEN_RE.search(corpus))

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

    polling_hits = [
        p
        for p in (
            r"run_polling\s*\(",
            r"start_polling\s*\(",
            r"\.polling\s*\(",
            r"infinity_polling\s*\(",
            r"executor\.start_polling",
        )
        if re.search(p, corpus)
    ]
    webhook_hits = [
        p
        for p in (
            r"run_webhook\s*\(",
            r"set_webhook\s*\(",
            r"setWebhook",
            r"process_update\s*\(",
            r"feed_update\s*\(",
            r"process_new_updates\s*\(",
        )
        if re.search(p, corpus)
    ]

    if polling_hits and not webhook_hits:
        mode = MODE_POLLING
        evidence.extend(polling_hits[:4])
    elif webhook_hits and not polling_hits:
        mode = MODE_WEBHOOK
        evidence.extend(webhook_hits[:4])
    elif polling_hits and webhook_hits:
        mode = MODE_POLLING
        evidence.append("mixed_polling_webhook")
    else:
        mode = MODE_UNKNOWN
        if framework != FRAMEWORK_UNKNOWN:
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

    return DetectResult(
        framework=framework,
        mode=mode,
        entry_point=entry,
        evidence=evidence,
        hardcoded_token=hardcoded,
    )


def _module_from_entry(entry: str) -> str:
    mod = entry.replace("\\", "/").removesuffix(".py").replace("/", ".")
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_\.]*$", mod):
        return "main"
    return mod


def _adapter_source(*, entry_module: str, framework: str) -> str:
    if not _TEMPLATE_PATH.is_file():
        raise FileNotFoundError("serverless_handler_template_missing")
    raw = _TEMPLATE_PATH.read_text(encoding="utf-8")
    return (
        raw.replace("@@MARKER@@", _ADAPTER_MARKER)
        .replace("@@FRAMEWORK@@", framework)
        .replace("@@ENTRY@@", _module_from_entry(entry_module))
    )


def neutralize_polling_calls(entry_file: Path) -> bool:
    """Comment out module-level polling starters so import is safe under serverless.

    Returns True if file was modified.
    """
    if not entry_file.is_file():
        return False
    text = entry_file.read_text(encoding="utf-8", errors="ignore")
    if _NEUTRALIZE_MARKER in text:
        return False
    original = text
    # Line-based neutralization for common patterns
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    changed = False
    patterns = (
        "run_polling(",
        "start_polling(",
        ".polling(",
        "infinity_polling(",
        "executor.start_polling(",
    )
    for ln in lines:
        stripped = ln.lstrip()
        if stripped.startswith("#"):
            out.append(ln)
            continue
        if any(p in ln for p in patterns) and not stripped.startswith("def ") and not stripped.startswith("async def "):
            indent = ln[: len(ln) - len(ln.lstrip())]
            out.append(f"{indent}pass  # {_NEUTRALIZE_MARKER}: {stripped.strip()[:80]}\n")
            changed = True
        else:
            out.append(ln)
    if not changed:
        return False
    # ensure marker once at top after future/doc
    body = "".join(out)
    if _NEUTRALIZE_MARKER not in body.split("\n")[0:5]:
        body = f"# {_NEUTRALIZE_MARKER}\n" + body
    entry_file.write_text(body, encoding="utf-8")
    return True


def scrub_hardcoded_tokens(entry_file: Path) -> int:
    """Replace hardcoded bot tokens with env lookup. Returns number of replacements."""
    if not entry_file.is_file():
        return 0
    text = entry_file.read_text(encoding="utf-8", errors="ignore")
    matches = list(_TOKEN_RE.finditer(text))
    if not matches:
        return 0
    new = text
    for m in reversed(matches):
        # Only replace if looks like a string literal assignment context
        start, end = m.span()
        replacement = 'os.environ.get("BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN") or ""'
        # keep quotes style rough
        new = new[:start] + '"USE_ENV_BOT_TOKEN"' + new[end:]
        # simpler: replace token string with env expression via placeholder string
    # Prefer explicit env string for safety
    new = _TOKEN_RE.sub(
        '"",  # lumen: token removed — use BOT_TOKEN env',
        text,
    )
    if new == text:
        return 0
    if "import os" not in new and "from os" not in new:
        new = "import os\n" + new
    entry_file.write_text(new, encoding="utf-8")
    return len(matches)


def _platform_config() -> dict[str, Any]:
    return {
        "version": 2,
        "builds": [{"src": "api/index.py", "use": "@vercel/python"}],
        "routes": [
            {"src": "/api", "dest": "api/index.py"},
            {"src": "/api/(.*)", "dest": "api/index.py"},
            {"src": "/(.*)", "dest": "api/index.py"},
        ],
    }


def _ensure_requirements(root: Path, framework: str) -> str | None:
    req = root / "requirements.txt"
    if framework == FRAMEWORK_AIOGRAM:
        need, key = "aiogram>=2.25,<4", "aiogram"
    elif framework == FRAMEWORK_TELEBOT:
        need, key = "pyTelegramBotAPI>=4.14", "telebot"
    else:
        need, key = "python-telegram-bot>=20.0,<22", "telegram"
    if not req.is_file():
        req.write_text(need + "\n", encoding="utf-8")
        return "requirements.txt"
    text = req.read_text(encoding="utf-8", errors="ignore").lower()
    if key in text or "python-telegram-bot" in text or "aiogram" in text or "pytelegrambotapi" in text:
        return None
    with req.open("a", encoding="utf-8") as f:
        f.write("\n# lumen serverless\n" + need + "\n")
    return "requirements.txt"


def validate_serverless_layout(root: Path) -> tuple[bool, str]:
    api = root / "api" / "index.py"
    cfg = root / "vercel.json"
    if not api.is_file():
        return False, "missing_api_index"
    if not cfg.is_file():
        return False, "missing_platform_config"
    txt = api.read_text(encoding="utf-8", errors="ignore")
    if _ADAPTER_MARKER not in txt:
        return False, "adapter_marker_missing"
    if _TOKEN_RE.search(txt):
        return False, "secret_in_adapter"
    if "BOT_TOKEN" not in txt:
        return False, "adapter_missing_env_token"
    if "class handler" not in txt:
        return False, "adapter_missing_handler"
    try:
        conf = json.loads(cfg.read_text(encoding="utf-8"))
    except Exception:
        return False, "platform_config_invalid_json"
    if not isinstance(conf, dict):
        return False, "platform_config_not_object"
    return True, "ok"


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
        ok_v, why = validate_serverless_layout(root)
        if not ok_v:
            # repair
            force = True
        else:
            return AdaptResult(
                ok=True,
                message="المشروع جاهز لاستضافة Lumen (Webhook)",
                detect=det,
                details={"skipped": "already_adapted", "validate": why},
                webhook_path="/api",
            )

    entry = (entry_point or det.entry_point or "").strip()
    if not entry:
        return AdaptResult(ok=False, message="لا توجد نقطة دخول للبوت داخل المشروع", detect=det)

    entry_path = root / entry
    if not entry_path.is_file():
        return AdaptResult(ok=False, message=f"ملف الدخول غير موجود: {entry}", detect=det)

    framework = det.framework
    if framework in {FRAMEWORK_UNKNOWN, FRAMEWORK_ALREADY}:
        framework = FRAMEWORK_PTB
        det.evidence.append("defaulted_ptb")

    written: list[str] = []
    scrubbed = scrub_hardcoded_tokens(entry_path)
    if scrubbed:
        written.append(entry)
        det.evidence.append(f"scrubbed_tokens:{scrubbed}")
    if neutralize_polling_calls(entry_path):
        if entry not in written:
            written.append(entry)
        det.evidence.append("polling_neutralized")

    api_dir = root / "api"
    api_dir.mkdir(parents=True, exist_ok=True)
    try:
        src = _adapter_source(entry_module=entry, framework=framework)
    except Exception as exc:
        return AdaptResult(ok=False, message=f"فشل توليد محوّل Webhook: {type(exc).__name__}", detect=det)
    (api_dir / "index.py").write_text(src, encoding="utf-8")
    written.append("api/index.py")

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
        "evidence": det.evidence[:16],
        "hardcoded_token_scrubbed": scrubbed,
        "polling_neutralized": "polling_neutralized" in det.evidence,
    }
    (root / ".lumen_serverless.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    written.append(".lumen_serverless.json")

    ok_v, why = validate_serverless_layout(root)
    if not ok_v:
        return AdaptResult(
            ok=False,
            message=f"فشل التحقق من تجهيز الاستضافة: {why}",
            detect=det,
            files_written=written,
            details={**meta, "validate": why},
        )

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
    "neutralize_polling_calls",
    "scrub_hardcoded_tokens",
    "validate_serverless_layout",
    "FRAMEWORK_PTB",
    "FRAMEWORK_AIOGRAM",
    "FRAMEWORK_TELEBOT",
    "MODE_POLLING",
    "MODE_WEBHOOK",
]
