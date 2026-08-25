"""
Output manager — finalises the project directory and packages the deliverable.

Responsibilities:
* Verify the generated project structure exists.
* Optionally create a zip archive.
* Return a ``PackageInfo`` dict with ``project_path`` and metadata.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any, Dict, Optional


class OutputManager:
    """Assembles and packages the final generated project."""

    def __init__(self, config=None) -> None:
        self._config = config
        self._create_zip: bool = False
        if config is not None:
            self._create_zip = bool(config.get("output", "create_zip", False))

    def package(self, context: Any) -> Dict[str, Any]:
        """Finalise and package the generated project.

        Parameters:
            context: The :class:`~lumen.engine.core.context.GenerationContext`
                containing ``work_dir`` and ``created_files``.

        Returns:
            A ``PackageInfo`` dict with at minimum a ``project_path`` key.
        """
        work_dir: Optional[Path] = getattr(context, "work_dir", None)
        if work_dir is None:
            work_dir = Path(".")

        work_dir = Path(work_dir)
        created_files = list(getattr(context, "created_files", []))

        package_info: Dict[str, Any] = {
            "project_path": str(work_dir),
            "files": created_files,
            "zip_path": None,
        }

        if self._create_zip and work_dir.exists():
            zip_path = work_dir.parent / f"{work_dir.name}.zip"
            try:
                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    # Prefer walking the work dir so relative paths are always valid.
                    for p in work_dir.rglob("*"):
                        if p.is_file() and "__pycache__" not in p.parts:
                            zf.write(p, p.relative_to(work_dir))
                package_info["zip_path"] = str(zip_path)
            except Exception:
                # Zip is optional — never fail packaging solely because of it.
                package_info["zip_path"] = None

        return package_info


__all__ = ["OutputManager"]
