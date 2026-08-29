"""Process helpers for Firecracker / jailer."""
from __future__ import annotations

import logging
import os
import subprocess
from typing import List, Optional

logger = logging.getLogger(__name__)

def _run(
    cmd: list[str],
    *,
    timeout: float = 30.0,
    cwd: Optional[str] = None,
) -> Tuple[int, str, str]:
    try:
        p = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            cwd=cwd,
        )
        return p.returncode, p.stdout or "", p.stderr or ""
    except Exception as exc:
        return 1, "", f"{type(exc).__name__}:{exc}"


