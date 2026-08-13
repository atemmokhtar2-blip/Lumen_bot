"""Runtime-generated project identity and capability manifest.

The manifest contains observations from the running checkout and live plan registry;
it does not store plan quotas or project facts as training text.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import os
import pkgutil
from pathlib import Path
from typing import Any

from b2b_platform.plans import PLANS, public_plan_dict

_ROOT = Path(__file__).resolve().parents[2]


def _source_fingerprint() -> str:
    files: list[Path] = []
    for directory in (_ROOT / "b2b_platform", _ROOT / "dialogue", _ROOT / "bot_interface"):
        if directory.is_dir():
            files.extend(p for p in directory.rglob("*.py") if p.is_file())
    files.extend(p for p in (_ROOT / "dialogue" / "models").glob("*.tar.gz") if p.is_file())
    digest = hashlib.sha256()
    for path in sorted(files):
        stat = path.stat()
        digest.update(str(path.relative_to(_ROOT)).encode())
        digest.update(str(stat.st_mtime_ns).encode())
        digest.update(str(stat.st_size).encode())
    digest.update((os.getenv("DIALOGUE_ENABLED") or "").encode())
    digest.update(json.dumps(
        [public_plan_dict(plan) for plan in PLANS.values()],
        sort_keys=True,
        ensure_ascii=False,
    ).encode())
    return digest.hexdigest()


def _module_catalog(package_name: str) -> list[dict[str, Any]]:
    package_path = _ROOT / package_name.replace(".", "/")
    if not package_path.is_dir():
        return []
    result: list[dict[str, Any]] = []
    for info in sorted(pkgutil.iter_modules([str(package_path)]), key=lambda item: item.name):
        if info.name.startswith("_"):
            continue
        item: dict[str, Any] = {"module": info.name}
        try:
            module = importlib.import_module(f"{package_name}.{info.name}")
            item["classes"] = sorted(
                name for name, value in vars(module).items()
                if isinstance(value, type) and getattr(value, "__module__", "") == module.__name__
            )
            item["functions"] = sorted(
                name for name, value in vars(module).items()
                if callable(value) and getattr(value, "__module__", "") == module.__name__
                and not name.startswith("_")
            )
        except Exception as exc:
            item["load_error"] = type(exc).__name__
        result.append(item)
    return result


def build_project_manifest() -> dict[str, Any]:
    """Build a fresh, observable description of the current project state."""
    models = sorted(
        [
            {
                "file": str(path.relative_to(_ROOT)),
                "bytes": path.stat().st_size,
                "mtime_ns": path.stat().st_mtime_ns,
            }
            for path in (_ROOT / "dialogue" / "models").glob("*.tar.gz")
            if path.is_file()
        ],
        key=lambda item: item["file"],
    )
    plans = [public_plan_dict(plan) for plan in PLANS.values()]
    return {
        "fingerprint": _source_fingerprint(),
        "root": _ROOT.name,
        "python": os.getenv("PYTHON_VERSION") or "runtime",
        "dialogue_enabled": (os.getenv("DIALOGUE_ENABLED") or "0").lower() in {"1", "true", "yes", "on"},
        "models": models,
        "packages": {
            "b2b_platform": _module_catalog("b2b_platform"),
            "dialogue": _module_catalog("dialogue"),
            "bot_interface": _module_catalog("bot_interface"),
        },
        "plans": plans,
        "plan_ids": sorted(PLANS),
    }


class ProjectManifest:
    """Small change-aware cache; rebuilds when source files or live config change."""

    def __init__(self) -> None:
        self._fingerprint = ""
        self._value: dict[str, Any] | None = None

    def get(self) -> dict[str, Any]:
        current = _source_fingerprint()
        if self._value is None or current != self._fingerprint:
            self._value = build_project_manifest()
            self._fingerprint = self._value["fingerprint"]
        return self._value


PROJECT_MANIFEST = ProjectManifest()


def project_manifest() -> dict[str, Any]:
    return PROJECT_MANIFEST.get()
