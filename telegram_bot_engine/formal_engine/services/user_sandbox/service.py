
"""Per-user isolated workspace for generate → test → host.

Layout (under OUTPUT_DIR):
  users/<telegram_user_id>/
    projects/<project_id>/     # generated bot source
    venvs/<project_id>/       # optional shared pointer (actual venv lives in project .tbe_venv)
    runtime/                  # logs, pid markers

Rules:
  - Never reuse the host bot token / process.
  - Child processes get a clean env (not os.environ.copy of the generator bot).
  - Paths are scoped by telegram user id only.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _safe_segment(value: str, fallback: str = "x") -> str:
    s = re.sub(r"[^a-zA-Z0-9_-]+", "_", (value or "").strip())[:48]
    return s or fallback


@dataclass
class UserSandbox:
    user_id: int
    root: Path

    @property
    def projects_dir(self) -> Path:
        return self.root / "projects"

    @property
    def runtime_dir(self) -> Path:
        return self.root / "runtime"

    def ensure(self) -> "UserSandbox":
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        return self

    def new_project_dir(self, label: str = "bot") -> Path:
        self.ensure()
        stamp = time.strftime("%Y%m%d_%H%M%S")
        name = f"{_safe_segment(label, 'bot')}_{stamp}"
        path = self.projects_dir / name
        path.mkdir(parents=True, exist_ok=False)
        return path

    def project_path(self, project_id: str) -> Path:
        return self.projects_dir / _safe_segment(project_id)

    def is_under_sandbox(self, path: str | Path) -> bool:
        try:
            Path(path).resolve().relative_to(self.root.resolve())
            return True
        except Exception:
            return False


def get_user_sandbox(user_id: int, base_dir: str | Path | None = None) -> UserSandbox:
    base = Path(base_dir or os.getenv("OUTPUT_DIR", "/tmp/generated")).resolve()
    uid = int(user_id or 0)
    root = base / "users" / str(uid)
    return UserSandbox(user_id=uid, root=root).ensure()


def clean_child_env(bot_token: str, extra: dict[str, str] | None = None) -> dict[str, str]:
    """Environment for a generated bot process — isolated from the generator bot.

    Keeps minimal system PATH/HOME/LANG. Does NOT inherit the host TELEGRAM_BOT_TOKEN
    or AI provider keys unless explicitly passed in extra.
    """
    token = (bot_token or "").strip()
    keep = (
        "PATH", "HOME", "USER", "LANG", "LC_ALL", "LC_CTYPE",
        "TMPDIR", "TMP", "TEMP", "PYTHONIOENCODING", "SSL_CERT_FILE",
        "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "SYSTEMROOT", "COMSPEC",
    )
    env: dict[str, str] = {}
    for k in keep:
        v = os.environ.get(k)
        if v:
            env[k] = v
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    # Mark isolation boundary
    env["TBE_SANDBOX"] = "1"
    env["TBE_ISOLATED"] = "1"
    if token:
        for key in (
            "BOT_TOKEN", "TELEGRAM_BOT_TOKEN", "TOKEN", "TG_TOKEN",
            "API_TOKEN", "TELEGRAM_TOKEN",
        ):
            env[key] = token
    if extra:
        for k, v in extra.items():
            if v is not None:
                env[str(k)] = str(v)
    return env


__all__ = ["UserSandbox", "get_user_sandbox", "clean_child_env"]
