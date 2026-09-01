"""Prepare a generated project for PERMANENT_HOST execution on a real server.

Host-side (API/worker has network):
  1) Resolve entry_point
  2) Sanitize + install requirements into project/.tbe_host_deps (pip --target)
  3) Return env for the sandbox (PYTHONPATH, LUMEN_BOT_ENTRY)

Guest-side cannot reliably pip install when egress is Telegram-only.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("tbe.hosting.prepare_runtime")

HOST_DEPS_DIRNAME = ".tbe_host_deps"


@dataclass
class PrepareResult:
    ok: bool
    entry_point: str = ""
    message: str = ""
    env_vars: dict[str, str] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)


def _find_requirements(root: Path) -> Path | None:
    for name in ("requirements.txt", "requirements-bot.txt", "reqs.txt"):
        p = root / name
        if p.is_file():
            return p
    return None


def resolve_entry_point(root: Path, hint: str = "") -> str:
    """Return path relative to root, or absolute under root."""
    root = root.resolve()
    hint = (hint or "").strip().replace("\\", "/")
    if hint:
        p = Path(hint)
        if not p.is_absolute():
            p = root / hint
        try:
            p = p.resolve()
            p.relative_to(root)
        except Exception:
            pass
        else:
            if p.is_file() and p.suffix == ".py":
                return str(p.relative_to(root)).replace("\\", "/")
    for rel in ("main.py", "bot.py", "app.py", "run.py", "src/main.py"):
        p = root / rel
        if p.is_file():
            return rel
    for p in sorted(root.glob("*.py")):
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")[:12000]
        except Exception:
            continue
        if any(
            x in text
            for x in (
                "run_polling",
                "start_polling",
                "Application.builder",
                "telebot",
                "aiogram",
            )
        ):
            return p.name
    return ""


def _install_requirements_target(root: Path, req: Path) -> tuple[bool, str]:
    """Install sanitized requirements into root/.tbe_host_deps."""
    target = root / HOST_DEPS_DIRNAME
    target.mkdir(parents=True, exist_ok=True)

    cleaned = req
    try:
        from lumen.engine.services.requirements_policy import sanitize_requirements_text

        raw = req.read_text(encoding="utf-8", errors="ignore")
        text, warns = sanitize_requirements_text(raw)
        for w in warns[:8]:
            logger.info("requirements_policy warn: %s", w)
        cleaned = root / ".tbe_host_requirements.sanitized.txt"
        cleaned.write_text(text, encoding="utf-8")
        if not text.strip():
            return True, "requirements_empty_after_sanitize"
    except Exception as exc:
        logger.warning("sanitize_requirements failed: %s", type(exc).__name__)

    py = sys.executable
    cmd = [
        py,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-input",
        "--target",
        str(target),
        "-r",
        str(cleaned),
    ]
    timeout = int((os.environ.get("TBE_HOST_PIP_TIMEOUT") or "300").strip() or "300")
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(root),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, f"pip_timeout_{timeout}s"
    except Exception as exc:
        return False, f"pip_exc:{type(exc).__name__}"

    if proc.returncode != 0:
        err = ((proc.stderr or "") + "\n" + (proc.stdout or "")).strip()
        # Surface last meaningful lines
        lines = [ln for ln in err.splitlines() if ln.strip()][-12:]
        return False, "pip_failed:" + " | ".join(lines)[:500]
    return True, f"installed_to:{HOST_DEPS_DIRNAME}"



def snapshot_project_version(root: Path) -> str:
    """Git commit of current tree for deploy versioning (empty if git unavailable)."""
    import subprocess
    try:
        if not (root / ".git").exists():
            subprocess.run(
                ["git", "init"],
                cwd=str(root),
                capture_output=True,
                timeout=30,
                check=False,
            )
        subprocess.run(
            ["git", "add", "-A"],
            cwd=str(root),
            capture_output=True,
            timeout=60,
            check=False,
        )
        subprocess.run(
            [
                "git",
                "-c",
                "user.email=hosting@lumen.local",
                "-c",
                "user.name=Lumen Hosting",
                "commit",
                "-m",
                "lumen-host-deploy",
                "--allow-empty",
            ],
            cwd=str(root),
            capture_output=True,
            timeout=60,
            check=False,
        )
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if r.returncode == 0:
            return (r.stdout or "").strip()[:40]
    except Exception as exc:
        logger.info("git snapshot skipped: %s", type(exc).__name__)
    return ""


def prepare_project_for_host(
    project_path: str | Path,
    *,
    entry_point: str = "",
    install_deps: bool = True,
) -> PrepareResult:
    root = Path(project_path).resolve()
    if not root.is_dir():
        return PrepareResult(ok=False, message="مسار المشروع غير موجود")

    entry = resolve_entry_point(root, entry_point)
    if not entry:
        return PrepareResult(
            ok=False,
            message="لا توجد نقطة دخول (main.py / bot.py) داخل المشروع",
        )
    entry_file = root / entry
    if not entry_file.is_file():
        return PrepareResult(ok=False, message=f"ملف الدخول غير موجود: {entry}")

    env: dict[str, str] = {
        "LUMEN_BOT_ENTRY": entry,
        "LUMEN_PROJECT_ROOT": "/project",
    }

    details: dict[str, Any] = {"entry_point": entry}
    req = _find_requirements(root)
    if install_deps and req is not None:
        ok_pip, pip_msg = _install_requirements_target(root, req)
        details["requirements"] = str(req.name)
        details["pip"] = pip_msg
        if not ok_pip:
            return PrepareResult(
                ok=False,
                entry_point=entry,
                message=f"فشل تثبيت الاعتماديات على السيرفر: {pip_msg[:400]}",
                details=details,
            )
        # Guest + host interpreters: put target first on PYTHONPATH
        deps = str((root / HOST_DEPS_DIRNAME).resolve())
        existing = (os.environ.get("PYTHONPATH") or "").strip()
        env["PYTHONPATH"] = deps if not existing else f"{deps}{os.pathsep}{existing}"
        # Also signal guest common layout
        env["LUMEN_HOST_DEPS"] = f"/project/{HOST_DEPS_DIRNAME}"
    elif req is None:
        details["requirements"] = "none"
    else:
        details["pip"] = "skipped"

    version_ref = snapshot_project_version(root)
    details["version_ref"] = version_ref
    return PrepareResult(
        ok=True,
        entry_point=entry,
        message="جاهز للتشغيل على السيرفر",
        env_vars=env,
        details=details,
    )


__all__ = [
    "PrepareResult",
    "prepare_project_for_host",
    "resolve_entry_point",
    "HOST_DEPS_DIRNAME",
    "snapshot_project_version",
]
