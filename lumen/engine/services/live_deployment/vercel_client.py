"""Internal platform host API client (Vercel REST).

Operator-only module. End users never see provider names or tokens.
Auth: VERCEL_TOKEN via secrets_provider / env (never logged).

API reference: https://vercel.com/docs/rest-api
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("lumen.live_deployment.platform_host_client")

_API = "https://api.vercel.com"
_SAFE_NAME = re.compile(r"[^a-z0-9-]+")


def _token() -> str:
    try:
        from lumen.platform.secrets_provider import get_secret
        v = (get_secret("VERCEL_TOKEN", "") or "").strip()
        if v:
            return v
    except Exception:
        pass
    return (os.getenv("VERCEL_TOKEN") or "").strip()


def _team_id() -> str:
    try:
        from lumen.platform.secrets_provider import get_secret
        v = (get_secret("VERCEL_TEAM_ID", "") or "").strip()
        if v:
            return v
    except Exception:
        pass
    return (os.getenv("VERCEL_TEAM_ID") or "").strip()


def token_configured() -> bool:
    return bool(_token())


def sanitize_project_name(name: str, *, max_len: int = 48) -> str:
    raw = (name or "lumen-bot").strip().lower()
    raw = _SAFE_NAME.sub("-", raw).strip("-") or "lumen-bot"
    return raw[:max_len]


@dataclass
class ApiResult:
    ok: bool
    status: int = 0
    data: dict[str, Any] | list[Any] | None = None
    error: str = ""

    @property
    def mapping(self) -> dict[str, Any]:
        return self.data if isinstance(self.data, dict) else {}


class PlatformHostClient:
    """Thin HTTPS client for platform project/deployment operations."""

    def __init__(self, *, token: str | None = None, team_id: str | None = None, timeout: float = 60.0) -> None:
        self._token = (token if token is not None else _token()).strip()
        self._team = (team_id if team_id is not None else _team_id()).strip()
        self._timeout = float(timeout)

    @property
    def configured(self) -> bool:
        return bool(self._token)

    def _url(self, path: str, query: dict[str, str] | None = None) -> str:
        q = dict(query or {})
        if self._team:
            q.setdefault("teamId", self._team)
        base = f"{_API}{path}"
        if not q:
            return base
        return base + "?" + urllib.parse.urlencode(q)

    def request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        query: dict[str, str] | None = None,
    ) -> ApiResult:
        if not self._token:
            return ApiResult(ok=False, error="platform_host_token_missing")
        url = self._url(path, query)
        data = None
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
            "User-Agent": "LumenHost/1.0",
        }
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                status = int(getattr(resp, "status", 200) or 200)
                parsed: Any = {}
                if raw.strip():
                    try:
                        parsed = json.loads(raw)
                    except Exception:
                        parsed = {"raw": raw[:500]}
                return ApiResult(ok=200 <= status < 300, status=status, data=parsed)
        except urllib.error.HTTPError as exc:
            err_body = ""
            try:
                err_body = exc.read().decode("utf-8", errors="replace")[:800]
            except Exception:
                pass
            detail = err_body
            try:
                j = json.loads(err_body)
                if isinstance(j, dict):
                    detail = str(j.get("error") or j.get("message") or err_body)[:400]
            except Exception:
                pass
            logger.warning("platform_host_http status=%s path=%s", exc.code, path)
            return ApiResult(ok=False, status=int(exc.code or 0), error=f"http_{exc.code}:{detail}"[:500])
        except Exception as exc:
            logger.warning("platform_host_error %s", type(exc).__name__)
            return ApiResult(ok=False, error=f"network:{type(exc).__name__}")

    def create_project(self, name: str, *, framework: str | None = None) -> ApiResult:
        body: dict[str, Any] = {"name": sanitize_project_name(name)}
        if framework:
            body["framework"] = framework
        return self.request("POST", "/v10/projects", body=body)

    def get_project(self, name_or_id: str) -> ApiResult:
        pid = urllib.parse.quote(str(name_or_id), safe="")
        return self.request("GET", f"/v9/projects/{pid}")

    def ensure_project(self, name: str) -> ApiResult:
        """Create project or return existing by name."""
        created = self.create_project(name)
        if created.ok:
            return created
        # 409 / already exists → fetch
        err = (created.error or "").lower()
        if created.status in {409, 400} or "already" in err or "conflict" in err:
            existing = self.get_project(sanitize_project_name(name))
            if existing.ok:
                return existing
        return created

    def upsert_env(
        self,
        project_id: str,
        key: str,
        value: str,
        *,
        targets: list[str] | None = None,
        sensitive: bool = True,
    ) -> ApiResult:
        """Set environment variable (BOT_TOKEN etc.). Never log value."""
        if not key or value is None:
            return ApiResult(ok=False, error="env_key_or_value_missing")
        body: dict[str, Any] = {
            "key": str(key),
            "value": str(value),
            "type": "sensitive" if sensitive else "plain",
            "target": targets or ["production", "preview", "development"],
        }
        pid = urllib.parse.quote(str(project_id), safe="")
        return self.request("POST", f"/v10/projects/{pid}/env", body=body)

    def create_file_deployment(
        self,
        *,
        project_name: str,
        files: list[dict[str, str]],
        env: dict[str, str] | None = None,
        target: str = "production",
    ) -> ApiResult:
        """Deploy from inlined files: [{file, data}] data is base64 or plain per API.

        Uses Vercel deployments API with `files` entries.
        """
        body: dict[str, Any] = {
            "name": sanitize_project_name(project_name),
            "project": sanitize_project_name(project_name),
            "files": files,
            "projectSettings": {
                "framework": None,
            },
            "target": target,
        }
        if env:
            # Deployment-time env (also prefer project env for secrets)
            body["env"] = {str(k): str(v) for k, v in env.items()}
        return self.request("POST", "/v13/deployments", body=body)

    def get_deployment(self, deployment_id: str) -> ApiResult:
        did = urllib.parse.quote(str(deployment_id), safe="")
        return self.request("GET", f"/v13/deployments/{did}")

    def cancel_deployment(self, deployment_id: str) -> ApiResult:
        did = urllib.parse.quote(str(deployment_id), safe="")
        return self.request("PATCH", f"/v12/deployments/{did}/cancel")

    def delete_project(self, project_id: str) -> ApiResult:
        pid = urllib.parse.quote(str(project_id), safe="")
        return self.request("DELETE", f"/v9/projects/{pid}")


def collect_project_files(project_path: str | Path, *, max_files: int = 200, max_bytes: int = 2_000_000) -> list[dict[str, str]]:
    """Walk project dir into deployment file list (relative paths).

    Skips .git, __pycache__, venv, large binaries. Content base64-encoded.
    """
    root = Path(project_path).resolve()
    if not root.is_dir():
        raise ValueError("project_path_not_dir")
    skip_parts = {".git", "__pycache__", ".venv", "venv", "node_modules", ".lumen"}
    out: list[dict[str, str]] = []
    total = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(root).parts
        if any(p in skip_parts for p in rel_parts):
            continue
        if path.suffix.lower() in {".pyc", ".pyo", ".so", ".dll", ".exe", ".zip", ".tar", ".gz"}:
            continue
        try:
            data = path.read_bytes()
        except Exception:
            continue
        if len(data) > 400_000:
            continue
        total += len(data)
        if total > max_bytes or len(out) >= max_files:
            break
        rel = path.relative_to(root).as_posix()
        out.append({"file": rel, "data": base64.b64encode(data).decode("ascii")})
    if not out:
        raise ValueError("project_has_no_deployable_files")
    return out


__all__ = [
    "PlatformHostClient",
    "ApiResult",
    "token_configured",
    "sanitize_project_name",
    "collect_project_files",
]
