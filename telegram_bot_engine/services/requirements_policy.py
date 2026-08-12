"""Sanitize requirements.txt before any pip install (host or container).

Blocks VCS/URL/path installs, pip flags, and obvious secret-exfil packages.
Does not replace --only-binary=:all:; it reduces the install surface further.
"""
from __future__ import annotations

import re
from pathlib import Path

_VCS = re.compile(r"(?i)^(git\+|hg\+|svn\+|bzr\+|http://|https://|ftp://)")
_NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._+-]*$")

# Packages that should never be auto-installed into generated bots
_BLOCKED = {
    "os", "sys", "subprocess", "ctypes", "pty", "pathlib",
    # common typos / attack probes
    "pwn", "pwntools",
}


def sanitize_requirements_text(text: str) -> tuple[str, list[str]]:
    warnings: list[str] = []
    out: list[str] = []
    for raw_line in (text or "").splitlines():
        raw = raw_line.strip()
        if not raw or raw.startswith("#"):
            continue
        # drop inline comments
        if " #" in raw:
            raw = raw.split(" #", 1)[0].strip()
        low = raw.lower()
        if _VCS.search(raw) or "://" in raw:
            warnings.append(f"skipped_url:{raw[:80]}")
            continue
        if raw.startswith("-") or raw.startswith("--"):
            warnings.append(f"skipped_flag:{raw[:80]}")
            continue
        if any(x in raw for x in (";", "$(", "`", "|", "&&", "||", "\n", "\r")):
            warnings.append(f"skipped_shellish:{raw[:80]}")
            continue
        name_part = re.split(r"[<>=!~;\[@]", raw)[0].strip()
        if (
            raw.startswith(("/", ".", "~"))
            or "\\" in name_part
            or "/" in name_part
        ):
            warnings.append(f"skipped_path:{raw[:80]}")
            continue
        if any(low.rstrip().endswith(ext) for ext in (".tar.gz", ".zip", ".tgz", ".whl", ".tar")):
            warnings.append(f"skipped_archive:{raw[:80]}")
            continue
        name = name_part.lower().replace("-", "_")
        if not name_part or not _NAME.match(name_part):
            warnings.append(f"skipped_invalid:{raw[:80]}")
            continue
        if name in _BLOCKED or name_part.lower() in _BLOCKED:
            warnings.append(f"skipped_blocked:{raw[:80]}")
            continue
        # Cap pins to simple forms
        if len(raw) > 120:
            warnings.append(f"skipped_too_long:{raw[:40]}")
            continue
        out.append(raw)
    return "\n".join(out) + ("\n" if out else ""), warnings


def sanitize_requirements_file(path: Path) -> tuple[Path, list[str]]:
    """Write sanitized requirements next to original; return path + warnings."""
    path = Path(path)
    text = path.read_text(encoding="utf-8", errors="ignore") if path.is_file() else ""
    cleaned, warnings = sanitize_requirements_text(text)
    out = path.with_name(path.stem + ".sanitized.txt")
    out.write_text(cleaned, encoding="utf-8")
    return out, warnings
