"""Safe generation work directories — never fall back to host OUTPUT_DIR roots."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path


def allocate_fallback_workdir(user_id: int = 0) -> Path:
    """Create a restricted fallback under /tmp/lumen_fallback (mode 0o700).

    Rejects host filesystem roots. Used only when get_user_sandbox fails.
    """
    base = Path(os.getenv("LUMEN_FALLBACK_WORKDIR") or "/tmp/lumen_fallback").resolve()
    # Refuse dangerous roots
    forbidden = {Path("/"), Path("/tmp"), Path("/var"), Path("/home"), Path("/root")}
    if base in forbidden or len(base.parts) < 2:
        base = Path("/tmp/lumen_fallback")
    base.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(base, 0o700)
    except OSError:
        pass
    user_root = base / f"u{int(user_id)}"
    user_root.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(user_root, 0o700)
    except OSError:
        pass
    path = Path(tempfile.mkdtemp(prefix="botgen_", dir=str(user_root)))
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass
    return path
