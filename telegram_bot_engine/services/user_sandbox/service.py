"""Per-user isolated workspace for generate → test → host → memory.

Layout (under OUTPUT_DIR):
  users/<telegram_user_id>/
    projects/<project_id>/     # generated bot source
    clones/<clone_id>/         # user-specific git clones
    runtime/                   # logs, pid markers
    index.json                 # lightweight registry of this user's artefacts

Rules:
  - Never reuse the host bot token / process.
  - Child processes get a clean env (not os.environ.copy of the generator bot).
  - Paths are scoped by telegram user id only.
  - No fixed templates or canned bot packs — only what the user produced.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
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
    def clones_dir(self) -> Path:
        return self.root / "clones"

    @property
    def runtime_dir(self) -> Path:
        return self.root / "runtime"

    @property
    def index_path(self) -> Path:
        return self.root / "index.json"

    def ensure(self) -> "UserSandbox":
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        self.clones_dir.mkdir(parents=True, exist_ok=True)
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        if not self.index_path.exists():
            self._write_index({"user_id": self.user_id, "projects": [], "clones": [], "updated_at": ""})
        return self

    def new_project_dir(self, label: str = "bot") -> Path:
        self.ensure()
        stamp = time.strftime("%Y%m%d_%H%M%S")
        name = f"{_safe_segment(label, 'bot')}_{stamp}"
        path = self.projects_dir / name
        path.mkdir(parents=True, exist_ok=False)
        return path

    def new_clone_dir(self, label: str = "clone") -> Path:
        self.ensure()
        stamp = time.strftime("%Y%m%d_%H%M%S")
        name = f"{_safe_segment(label, 'clone')}_{stamp}"
        path = self.clones_dir / name
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

    # ── Lightweight per-user registry (no templates) ──────────────────────

    def _read_index(self) -> dict[str, Any]:
        try:
            if self.index_path.exists():
                return json.loads(self.index_path.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {"user_id": self.user_id, "projects": [], "clones": [], "updated_at": ""}

    def _write_index(self, data: dict[str, Any]) -> None:
        data = dict(data)
        data["user_id"] = self.user_id
        data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.index_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def register_project(
        self,
        path: str | Path,
        *,
        label: str = "",
        source_request: str = "",
        kind: str = "generated",
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Record a project that belongs to this user. Dynamic only — no templates."""
        self.ensure()
        p = Path(path).resolve()
        entry: dict[str, Any] = {
            "id": p.name,
            "path": str(p),
            "label": (label or p.name)[:80],
            "kind": kind,
            "source_request_preview": (source_request or "")[:200],
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        if extra:
            for k, v in extra.items():
                if k not in entry and v is not None:
                    entry[k] = v

        idx = self._read_index()
        projects = [x for x in (idx.get("projects") or []) if x.get("path") != entry["path"]]
        projects.insert(0, entry)
        # Hard cap per user — drop oldest from index (files left for offline GC)
        idx["projects"] = projects[: max_projects_per_user()]
        self._write_index(idx)
        return entry

    def register_clone(
        self,
        path: str | Path,
        *,
        url: str = "",
        label: str = "",
    ) -> dict[str, Any]:
        self.ensure()
        p = Path(path).resolve()
        entry = {
            "id": p.name,
            "path": str(p),
            "url": (url or "")[:300],
            "label": (label or p.name)[:80],
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        idx = self._read_index()
        clones = [x for x in (idx.get("clones") or []) if x.get("path") != entry["path"]]
        clones.insert(0, entry)
        idx["clones"] = clones[:50]
        self._write_index(idx)
        return entry

    def list_projects(self) -> list[dict[str, Any]]:
        self.ensure()
        return list(self._read_index().get("projects") or [])

    def list_clones(self) -> list[dict[str, Any]]:
        self.ensure()
        return list(self._read_index().get("clones") or [])

    def get_index(self) -> dict[str, Any]:
        self.ensure()
        return self._read_index()


def shard_for_user(user_id: int) -> str:
    """Two-level shard so millions of users do not sit in one directory.

    Layout: users/<xx>/<yy>/<user_id>/
    where xx,yy are zero-padded fragments from user_id.
    """
    uid = abs(int(user_id or 0))
    # Use last 4 digits split into 2+2 for even fan-out under any id scheme
    s = f"{uid:0>8d}"[-4:]
    return f"{s[:2]}/{s[2:]}"


def max_projects_per_user() -> int:
    try:
        return max(1, int(os.getenv("MAX_PROJECTS_PER_USER", "50")))
    except Exception:
        return 50


def get_user_sandbox(user_id: int, base_dir: str | Path | None = None) -> UserSandbox:
    base = Path(base_dir or os.getenv("OUTPUT_DIR", "/tmp/generated")).resolve()
    uid = int(user_id or 0)
    # Prefer sharded layout; still readable and isolatable per user.
    root = base / "users" / shard_for_user(uid) / str(uid)
    return UserSandbox(user_id=uid, root=root).ensure()



def _platform_secret() -> bytes:
    """Derive a stable key material from platform secrets (never commit raw keys)."""
    import hashlib
    raw = (
        (os.getenv("TBE_TOKEN_SECRET") or "").strip()
        or (os.getenv("PLATFORM_ADMIN_TOKEN") or "").strip()
        or (os.getenv("SECRET_KEY") or "").strip()
        or (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
        or "tbe-dev-insecure-token-key"
    )
    return hashlib.sha256(raw.encode("utf-8")).digest()


def _seal_token(token: str) -> str:
    """Encrypt token for at-rest storage. Falls back to plaintext prefix if crypto unavailable."""
    token = (token or "").strip()
    if not token:
        return ""
    try:
        # Pure-stdlib seal: XOR stream from SHA256(key||counter) + hmac tag
        import hashlib
        import hmac
        import base64
        key = _platform_secret()
        out = bytearray()
        data = token.encode("utf-8")
        for i, b in enumerate(data):
            block = hashlib.sha256(key + i.to_bytes(4, "big")).digest()
            out.append(b ^ block[i % 32])
        tag = hmac.new(key, bytes(out), hashlib.sha256).digest()[:16]
        return "enc1:" + base64.urlsafe_b64encode(tag + bytes(out)).decode("ascii")
    except Exception:
        return token


def _unseal_token(blob: str) -> str:
    blob = (blob or "").strip()
    if not blob.startswith("enc1:"):
        return blob
    try:
        import hashlib
        import hmac
        import base64
        key = _platform_secret()
        raw = base64.urlsafe_b64decode(blob[5:].encode("ascii"))
        tag, data = raw[:16], raw[16:]
        expect = hmac.new(key, data, hashlib.sha256).digest()[:16]
        if not hmac.compare_digest(tag, expect):
            return ""
        out = bytearray()
        for i, b in enumerate(data):
            block = hashlib.sha256(key + i.to_bytes(4, "big")).digest()
            out.append(b ^ block[i % 32])
        return out.decode("utf-8")
    except Exception:
        return ""


def write_token_file(project_dir: str | Path, bot_token: str) -> Path | None:
    """Write bot token to a 0600 file inside the project; return path or None.

    Reduces ambient exposure vs putting the token only in process environ
    (still visible via /proc on same-uid hosts — prefer Docker multi-tenant).
    """
    token = (bot_token or "").strip()
    if not token:
        return None
    root = Path(project_dir).resolve()
    path = root / ".tbe_bot_token"
    # Prefer not writing tokens to disk at all in multi-tenant prod
    if (os.getenv("TBE_DISABLE_TOKEN_FILE") or "").strip().lower() in {"1", "true", "yes", "on"}:
        return None
    try:
        sealed = _seal_token(token)
        path.write_text(sealed, encoding="utf-8")
        try:
            os.chmod(path, 0o600)
        except Exception:
            pass
        return path
    except Exception:
        return None


def read_token_file(project_dir: str | Path) -> str:
    """Read and unseal a token previously written by write_token_file."""
    path = Path(project_dir).resolve() / ".tbe_bot_token"
    try:
        if not path.is_file():
            return ""
        return _unseal_token(path.read_text(encoding="utf-8"))
    except Exception:
        return ""


def clean_child_env(
    bot_token: str,
    extra: dict[str, str] | None = None,
    *,
    token_file: str | Path | None = None,
) -> dict[str, str]:
    """Environment for a generated bot process — isolated from the generator bot.

    Keeps minimal system PATH/HOME/LANG. Does NOT inherit host secrets.
    Prefer token_file (0600) when available; still sets BOT_TOKEN for compatibility
    with generated bots that read os.environ. Multi-tenant hosts should use Docker.
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
    env["TBE_SANDBOX"] = "1"
    env["TBE_ISOLATED"] = "1"
    # Minimal token surface: only the two keys generated bots commonly read
    if token:
        env["BOT_TOKEN"] = token
        env["TELEGRAM_BOT_TOKEN"] = token
    if token_file:
        env["BOT_TOKEN_FILE"] = str(token_file)
        env["TELEGRAM_BOT_TOKEN_FILE"] = str(token_file)
    if extra:
        # Never allow extra to inject platform secrets back in
        blocked = {
            "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "STRIPE_SECRET_KEY",
            "DATABASE_URL", "AWS_SECRET_ACCESS_KEY", "GITHUB_TOKEN",
            "CAPABILITY_OPS_ADMINS",
        }
        for k, v in extra.items():
            if v is None:
                continue
            key = str(k)
            if key.upper() in blocked or key in blocked:
                continue
            env[key] = str(v)
    return env


__all__ = [
    "UserSandbox",
    "get_user_sandbox",
    "clean_child_env",
    "write_token_file",
    "shard_for_user",
    "max_projects_per_user",
]
