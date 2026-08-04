"""
LiveRunner — real dependency install + bot process execution + error capture.

Uses strongest practical stdlib tooling:
  - urllib for Telegram getMe
  - venv when available, else pip --target isolation
  - subprocess process supervision + traceback extraction
No fake success paths.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class LiveRunReport:
    ok: bool
    phase: str
    message: str
    bot_username: str = ""
    bot_id: int | None = None
    install_log: str = ""
    run_log: str = ""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    pid: int | None = None
    entry_point: str = ""
    venv_path: str = ""
    duration_ms: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)

    def to_user_text(self) -> str:
        icon = "✅" if self.ok else "❌"
        lines = [f"{icon} *تشغيل حي — {self.phase}*", f"• {self.message}"]
        if self.bot_username:
            lines.append(f"• البوت: @{self.bot_username}")
        if self.entry_point:
            lines.append(f"• نقطة الدخول: `{self.entry_point}`")
        if self.details.get("install_mode"):
            lines.append(f"• وضع التثبيت: `{self.details['install_mode']}`")
        if self.errors:
            lines.append("• أخطاء:")
            for e in self.errors[:6]:
                lines.append(f"  - `{e[:180]}`")
        if self.warnings:
            lines.append("• تحذيرات:")
            for w in self.warnings[:4]:
                lines.append(f"  - {w[:160]}")
        if self.run_log and not self.ok:
            tail = self.run_log.strip()[-500:]
            if tail:
                lines.append(f"• لوج:\n```\n{tail}\n```")
        if self.duration_ms:
            lines.append(f"• الزمن: {self.duration_ms:.0f}ms")
        return "\n".join(lines)


def validate_telegram_token(token: str, timeout: float = 12.0) -> tuple[bool, dict[str, Any], str]:
    token = (token or "").strip()
    if not re.match(r"^\d{6,12}:[A-Za-z0-9_-]{30,}$", token):
        return False, {}, "شكل التوكن غير صالح"
    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")[:300]
        return False, {}, f"Telegram HTTP {e.code}: {body}"
    except Exception as e:
        return False, {}, f"فشل الاتصال بـ Telegram: {type(e).__name__}: {e}"
    if not data.get("ok"):
        return False, data, f"getMe failed: {data}"
    return True, data.get("result") or {}, "ok"


def _find_requirements(root: Path) -> Path | None:
    for name in ("requirements.txt", "requirements-bot.txt", "reqs.txt"):
        p = root / name
        if p.exists():
            return p
    return None


def _find_entry(root: Path, hints: list[str] | None = None) -> Path | None:
    for h in hints or []:
        p = root / h
        if p.exists() and p.suffix == ".py":
            return p
    for name in ("main.py", "bot.py", "app.py", "run.py"):
        p = root / name
        if p.exists():
            return p
    for p in root.glob("*.py"):
        text = p.read_text(encoding="utf-8", errors="ignore")[:8000]
        if any(x in text for x in ("run_polling", "start_polling", "infinity_polling", "Application.builder")):
            return p
    return None


def _venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _deps_dir(root: Path) -> Path:
    d = root / ".tbe_deps"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _ensure_runtime(root: Path) -> tuple[str, str, Path]:
    """Returns (python_exe, mode, isolation_path)."""
    venv = root / ".tbe_venv"
    py = _venv_python(venv)
    if py.exists():
        return str(py), "venv-reused", venv
    try:
        r = subprocess.run(
            [sys.executable, "-m", "venv", str(venv)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if r.returncode == 0 and _venv_python(venv).exists():
            return str(_venv_python(venv)), "venv-created", venv
    except Exception:
        pass
    return sys.executable, "target", _deps_dir(root)


def _pip_install(py: str, req: Path | None, root: Path, mode: str, isolation: Path) -> tuple[bool, str]:
    if not req or not req.exists():
        return True, "no requirements.txt — skipped install"
    if mode.startswith("venv"):
        cmd = [py, "-m", "pip", "install", "-r", str(req)]
    else:
        cmd = [py, "-m", "pip", "install", "--target", str(isolation), "-r", str(req)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300, cwd=str(root))
    log = ((r.stdout or "") + "\n" + (r.stderr or ""))[-5000:]
    return r.returncode == 0, log


_ERROR_PATTERNS = (
    "Traceback (most recent call last):",
    "ModuleNotFoundError",
    "ImportError",
    "SyntaxError",
    "InvalidToken",
    "Unauthorized",
    "Conflict: terminated by other getUpdates",
)


def _extract_errors(log: str) -> list[str]:
    if not log:
        return []
    errors: list[str] = []
    parts = re.split(r"(?=Traceback \(most recent call last\):)", log)
    for p in parts:
        p = p.strip()
        if p and ("Traceback" in p or "Error" in p or "Exception" in p):
            errors.append(p[-400:])
    if not errors:
        for line in log.splitlines():
            if any(k in line for k in _ERROR_PATTERNS):
                errors.append(line.strip()[:240])
    seen, out = set(), []
    for e in errors:
        if e not in seen:
            seen.add(e)
            out.append(e)
    return out[:8]


class LiveRunnerService:
    def run(
        self,
        project_path: str | Path,
        bot_token: str,
        entry_hint: str | None = None,
        run_seconds: float = 8.0,
        install: bool = True,
    ) -> LiveRunReport:
        t0 = time.perf_counter()
        root = Path(project_path).resolve()
        if not root.exists():
            return LiveRunReport(ok=False, phase="validate", message="مسار المشروع غير موجود")

        ok, me, err = validate_telegram_token(bot_token)
        if not ok:
            return LiveRunReport(
                ok=False, phase="validate", message=err, errors=[err],
                duration_ms=(time.perf_counter() - t0) * 1000,
            )
        username = me.get("username") or ""
        bot_id = me.get("id")

        entry = _find_entry(root, [entry_hint] if entry_hint else None)
        if entry is None:
            return LiveRunReport(
                ok=False, phase="validate",
                message="لم أجد نقطة دخول قابلة للتشغيل (main.py/bot.py/…)",
                bot_username=username, bot_id=bot_id, errors=["no_entry_point"],
                duration_ms=(time.perf_counter() - t0) * 1000,
            )

        install_log = ""
        try:
            py, mode, isolation = _ensure_runtime(root)
            if install:
                req = _find_requirements(root)
                ok_i, install_log = _pip_install(py, req, root, mode, isolation)
                if not ok_i:
                    return LiveRunReport(
                        ok=False, phase="install", message="فشل تثبيت التبعيات",
                        bot_username=username, bot_id=bot_id,
                        install_log=install_log[-4000:],
                        errors=_extract_errors(install_log) or ["pip install failed"],
                        entry_point=str(entry.relative_to(root)),
                        venv_path=str(isolation),
                        duration_ms=(time.perf_counter() - t0) * 1000,
                        details={"install_mode": mode},
                    )
        except subprocess.TimeoutExpired:
            return LiveRunReport(
                ok=False, phase="install", message="انتهت مهلة تثبيت التبعيات",
                bot_username=username, bot_id=bot_id, errors=["install_timeout"],
                duration_ms=(time.perf_counter() - t0) * 1000,
            )
        except Exception as e:
            return LiveRunReport(
                ok=False, phase="install", message=f"install error: {type(e).__name__}: {e}",
                bot_username=username, bot_id=bot_id, errors=[str(e)],
                duration_ms=(time.perf_counter() - t0) * 1000,
            )

        env = os.environ.copy()
        env["TELEGRAM_BOT_TOKEN"] = bot_token
        env["BOT_TOKEN"] = bot_token
        env["TOKEN"] = bot_token
        env["PYTHONUNBUFFERED"] = "1"
        if mode.startswith("target"):
            # isolated deps on PYTHONPATH
            pp = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = str(isolation) + (os.pathsep + pp if pp else "")

        run_log = ""
        pid = None
        try:
            proc = subprocess.Popen(
                [py, str(entry)],
                cwd=str(root),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            pid = proc.pid
            try:
                out, _ = proc.communicate(timeout=run_seconds)
                run_log = out or ""
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    out, _ = proc.communicate(timeout=3)
                    run_log = out or ""
                except Exception:
                    pass
                errors = _extract_errors(run_log)
                if not errors:
                    return LiveRunReport(
                        ok=True, phase="run",
                        message=f"البوت اشتغل {run_seconds:.0f}ث بدون خطأ ظاهر ثم أوقفناه للفحص.",
                        bot_username=username, bot_id=bot_id,
                        install_log=install_log[-2000:], run_log=run_log[-3000:],
                        warnings=["process_stopped_after_probe_window"],
                        pid=pid, entry_point=str(entry.relative_to(root)),
                        venv_path=str(isolation),
                        duration_ms=(time.perf_counter() - t0) * 1000,
                        details={"install_mode": mode, "probe_seconds": run_seconds},
                    )
                return LiveRunReport(
                    ok=False, phase="run", message="أخطاء أثناء التشغيل",
                    bot_username=username, bot_id=bot_id,
                    install_log=install_log[-2000:], run_log=run_log[-4000:],
                    errors=errors, pid=pid, entry_point=str(entry.relative_to(root)),
                    venv_path=str(isolation),
                    duration_ms=(time.perf_counter() - t0) * 1000,
                    details={"install_mode": mode},
                )

            errors = _extract_errors(run_log)
            if proc.returncode == 0 and not errors:
                return LiveRunReport(
                    ok=True, phase="run",
                    message="انتهى بكود 0 (سكربت قصير أو إقلاع ناجح).",
                    bot_username=username, bot_id=bot_id,
                    install_log=install_log[-2000:], run_log=run_log[-3000:],
                    pid=pid, entry_point=str(entry.relative_to(root)),
                    venv_path=str(isolation),
                    duration_ms=(time.perf_counter() - t0) * 1000,
                    details={"install_mode": mode},
                )
            if not errors:
                errors = [f"process exited with code {proc.returncode}"]
            return LiveRunReport(
                ok=False, phase="run",
                message=f"توقف مبكراً (code={proc.returncode})",
                bot_username=username, bot_id=bot_id,
                install_log=install_log[-2000:], run_log=run_log[-4000:],
                errors=errors, pid=pid, entry_point=str(entry.relative_to(root)),
                venv_path=str(isolation),
                duration_ms=(time.perf_counter() - t0) * 1000,
                details={"install_mode": mode},
            )
        except Exception as e:
            return LiveRunReport(
                ok=False, phase="run", message=f"فشل التشغيل: {type(e).__name__}: {e}",
                bot_username=username, bot_id=bot_id,
                install_log=install_log[-2000:], run_log=run_log[-2000:],
                errors=[str(e)], entry_point=str(entry.relative_to(root)),
                duration_ms=(time.perf_counter() - t0) * 1000,
            )


def run_bot_project(
    project_path: str | Path,
    bot_token: str,
    entry_hint: str | None = None,
    run_seconds: float = 8.0,
) -> LiveRunReport:
    return LiveRunnerService().run(
        project_path=project_path,
        bot_token=bot_token,
        entry_hint=entry_hint,
        run_seconds=run_seconds,
    )
