#!/usr/bin/env python3
"""Remove obsolete bundled setuptools metadata from the final runtime image."""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

from packaging.version import InvalidVersion, Version


ROOTS = (Path("/usr/lib/python3.12"), Path("/opt/venv"))
MINIMUM = Version("84.1.0")


def main() -> None:
    stale: list[Path] = []
    for root in ROOTS:
        if not root.exists():
            continue
        for item in root.rglob("*"):
            name = item.name.lower()
            version_text = None
            if item.is_dir() and name.startswith("setuptools-") and name.endswith(
                (".dist-info", ".egg-info")
            ):
                suffix = ".dist-info" if name.endswith(".dist-info") else ".egg-info"
                version_text = item.name[len("setuptools-") : -len(suffix)]
            elif item.is_file() and name.startswith("setuptools-") and name.endswith(".whl"):
                parts = item.name.split("-", 2)
                version_text = parts[1] if len(parts) > 1 else None

            if version_text:
                try:
                    if Version(version_text) < MINIMUM:
                        stale.append(item)
                except InvalidVersion:
                    continue

    for item in stale:
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()
        print(f"Removed stale setuptools artifact: {item}")

    for root in ROOTS:
        if not root.exists():
            continue
        for item in root.rglob("*"):
            name = item.name.lower()
            if item.is_dir() and name.startswith("setuptools-") and name.endswith(
                (".dist-info", ".egg-info")
            ):
                suffix = ".dist-info" if name.endswith(".dist-info") else ".egg-info"
                version_text = item.name[len("setuptools-") : -len(suffix)]
                try:
                    assert Version(version_text) >= MINIMUM, str(item)
                except InvalidVersion:
                    continue

    checks = (
        (
            "/usr/bin/python3.12",
            "import setuptools; assert tuple(map(int, setuptools.__version__.split('.')[:2])) >= (84, 1), setuptools.__version__; print('system setuptools', setuptools.__version__)",
        ),
        (
            "/opt/venv/bin/python",
            "import setuptools; assert tuple(map(int, setuptools.__version__.split('.')[:2])) >= (84, 1), setuptools.__version__; print('app setuptools', setuptools.__version__)",
        ),
    )
    for command, code in checks:
        subprocess.run([command, "-c", code], check=True)


if __name__ == "__main__":
    main()
