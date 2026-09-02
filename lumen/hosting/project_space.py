"""Project Space — per-project storage layout for permanent hosting.

Layout under the project root (source stays at root for compatibility):

  <project>/
    main.py | bot.py | ...     # source
    static/                    # images, css, js (optional)
    data/                      # SQLite / JSON state
    logs/                      # local run / host logs
    .tbe_host_deps/            # pip --target (prepare_runtime)
    .lumen_secrets.sealed      # AES secrets
    .lumen_runtime.json        # runtime manifest
    .lumen_host.json           # host backend prefs
    .lumen_host_versions.json  # version index

Also registers paths under OUTPUT_DIR/hosting/spaces/{user_id}/{space_id}
when ensure_registered_space() is used (control-plane index).
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("tbe.hosting.project_space")

SUBDIRS = ("data", "logs", "static")


@dataclass
class ProjectSpace:
    root: Path
    user_id: int = 0
    space_id: str = ""
    source_dir: str = "."  # relative — project root is source
    data_dir: str = "data"
    logs_dir: str = "logs"
    static_dir: str = "static"
    created: bool = False

    @property
    def data_path(self) -> Path:
        return self.root / self.data_dir

    @property
    def logs_path(self) -> Path:
        return self.root / self.logs_dir

    @property
    def static_path(self) -> Path:
        return self.root / self.static_dir

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["root"] = str(self.root)
        return d


def ensure_project_space(project_path: Path | str, *, user_id: int = 0) -> ProjectSpace:
    """Create standard subdirs and migrate common DB files into data/."""
    root = Path(project_path).resolve()
    root.mkdir(parents=True, exist_ok=True)
    created_any = False
    for name in SUBDIRS:
        p = root / name
        if not p.exists():
            p.mkdir(parents=True, exist_ok=True)
            created_any = True
    # Move loose sqlite/json state into data/ if still at root
    for name in (
        "bot.db",
        "data.db",
        "app.db",
        "database.sqlite",
        "database.sqlite3",
        "storage.json",
        "data.json",
    ):
        src = root / name
        dest = root / "data" / name
        if src.is_file() and not dest.exists():
            try:
                shutil.move(str(src), str(dest))
                created_any = True
            except Exception:
                logger.warning("project_space migrate failed: %s", name)
    space = ProjectSpace(
        root=root,
        user_id=int(user_id or 0),
        space_id=root.name[:64],
        created=created_any,
    )
    # Write layout marker
    marker = root / ".lumen_space.json"
    try:
        marker.write_text(
            json.dumps({"layout": "v1", "dirs": list(SUBDIRS), "updated_at": time.time()}, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass
    return space


def write_runtime_manifest(
    project_path: Path | str,
    *,
    entry_point: str,
    backend: str = "firecracker",
    env_keys: list[str] | None = None,
    details: dict[str, Any] | None = None,
) -> Path:
    """Persist runtime contract for the project (read by ops / future agents)."""
    root = Path(project_path).resolve()
    path = root / ".lumen_runtime.json"
    payload = {
        "entry_point": entry_point,
        "backend": backend or "firecracker",
        "os": "linux",
        "isolation": "firecracker-microvm" if (backend or "firecracker") == "firecracker" else backend,
        "python_deps_dir": ".tbe_host_deps",
        "env_keys": list(env_keys or []),
        "ports": {
            "mode": "polling_or_webhook",
            "webhook_path_template": "/v1/hooks/telegram/{instance_id}",
        },
        "space": {"data": "data/", "logs": "logs/", "static": "static/"},
        "details": details or {},
        "updated_at": time.time(),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_runtime_manifest(project_path: Path | str) -> dict[str, Any]:
    path = Path(project_path).resolve() / ".lumen_runtime.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def spaces_index_root() -> Path:
    raw = (os.environ.get("TBE_HOST_SPACES_DIR") or "").strip()
    if raw:
        p = Path(raw)
    else:
        try:
            from lumen.bot.config import OUTPUT_DIR

            p = Path(OUTPUT_DIR) / "hosting" / "spaces"
        except Exception:
            p = Path.home() / ".lumen" / "hosting" / "spaces"
    p.mkdir(parents=True, exist_ok=True)
    return p


def register_space_index(space: ProjectSpace) -> Path:
    """Symlink or marker under control-plane spaces index."""
    base = spaces_index_root() / str(int(space.user_id or 0))
    base.mkdir(parents=True, exist_ok=True)
    marker = base / f"{space.space_id or space.root.name}.json"
    marker.write_text(json.dumps(space.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return marker


__all__ = [
    "ProjectSpace",
    "ensure_project_space",
    "write_runtime_manifest",
    "load_runtime_manifest",
    "register_space_index",
    "spaces_index_root",
    "SUBDIRS",
]
