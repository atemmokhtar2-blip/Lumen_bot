"""Security gates: secret scan, path traversal, dynamic .gitignore. Fail-closed."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

# High-signal secret patterns (fail-closed if matched in staged content)
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{30,}\b"),  # Telegram bot token
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bsk_(?:live|test)_[A-Za-z0-9]{20,}\b"),  # Stripe
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),  # AWS access key id
    re.compile(r"\b(?:api[_-]?key|secret[_-]?key|password|passwd)\s*[:=]\s*['\"][^'\"]{8,}['\"]", re.I),
    re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"),
)

_STRICT_GITIGNORE = """\
# Managed by Power Git Engine — do not track secrets or local junk
.env
.env.*
!.env.example
__pycache__/
*.py[cod]
*$py.class
.venv/
venv/
env/
*.log
.logs/
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
htmlcov/
.DS_Store
node_modules/
dist/
build/
*.egg-info/
.idea/
.vscode/
*.sqlite3
*.db
.lumen/
clones/
"""


def redact_text(text: str, extra_secrets: Iterable[str] = ()) -> str:
    s = text or ""
    for pat in _SECRET_PATTERNS:
        s = pat.sub("[REDACTED]", s)
    for secret in extra_secrets:
        if secret and len(secret) >= 8:
            s = s.replace(secret, "[REDACTED]")
    # Host absolute paths
    s = re.sub(r"(/home|/var|/tmp|/root)/[^\s:]+", "[PATH]", s)
    return s


def scan_text_for_secrets(text: str) -> list[str]:
    hits: list[str] = []
    for pat in _SECRET_PATTERNS:
        if pat.search(text or ""):
            hits.append(pat.pattern[:40])
    return hits


def scan_files_for_secrets(paths: Iterable[Path], *, root: Path) -> list[str]:
    """Return human findings; empty means clean."""
    findings: list[str] = []
    root = root.resolve()
    for p in paths:
        try:
            rp = p.resolve()
            if not str(rp).startswith(str(root)):
                findings.append(f"path_outside_sandbox:{p.name}")
                continue
            if not rp.is_file() or rp.stat().st_size > 1_500_000:
                continue
            if rp.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".zip", ".gz", ".pyc"}:
                continue
            data = rp.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if scan_text_for_secrets(data):
            findings.append(f"secret_pattern:{rp.relative_to(root)}")
    return findings


def assert_inside_sandbox(path: Path, sandbox_root: Path) -> Path:
    """Resolve path and ensure it stays under sandbox_root. Raises ValueError."""
    root = sandbox_root.expanduser().resolve()
    raw = Path(path)
    # Reject explicit traversal tokens before resolve
    parts = raw.parts
    if ".." in parts:
        raise ValueError("path_traversal_rejected")
    target = (root / raw).resolve() if not raw.is_absolute() else raw.resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError("path_outside_sandbox") from exc
    return target


def ensure_strict_gitignore(repo_root: Path) -> bool:
    """Inject strict .gitignore if missing or incomplete. Returns True if written/updated."""
    gi = repo_root / ".gitignore"
    required = [".env", "__pycache__/", "venv/", ".venv/", "*.log"]
    if not gi.exists():
        gi.write_text(_STRICT_GITIGNORE, encoding="utf-8")
        return True
    existing = gi.read_text(encoding="utf-8", errors="ignore")
    missing = [r for r in required if r not in existing]
    if not missing:
        return False
    gi.write_text(existing.rstrip() + "\n\n# Power Git Engine additions\n" + "\n".join(missing) + "\n", encoding="utf-8")
    return True
