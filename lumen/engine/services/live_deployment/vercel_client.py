"""Internal platform-host HTTP client (Lumen-owned account).

Real Vercel REST flows only (no theatre):
  1) POST /v2/files          — raw body + x-vercel-digest (sha1 of content)
  2) POST /v13/deployments   — files: [{file, sha, size}] OR inline {file, data, encoding}
  3) GET  /v13/deployments/{id}
  4) DELETE /v13/deployments/{id}
  5) POST /v10/projects + POST /v10/projects/{id}/env

End users never see vendor names. Tokens never logged.
Docs: https://vercel.com/docs/rest-api
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger("lumen.live_deployment.platform_host_client")

_API = "https://api.vercel.com"
_SAFE_NAME = re.compile(r"[^a-z0-9-]+")
# Prefer upload+sha for anything above this (API allows small inlines)
_INLINE_MAX = 8_000


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
    while "--" in raw:
        raw = raw.replace("--", "-")
    return raw[:max_len]


def sha1_bytes(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


@dataclass
class ApiResult:
    ok: bool
    status: int = 0
    data: dict[str, Any] | list[Any] | None = None
    error: str = ""

    @property
    def mapping(self) -> dict[str, Any]:
        return self.data if isinstance(self.data, dict) else {}


@dataclass
class LocalFile:
    rel: str
    content: bytes

    @property
    def sha(self) -> str:
        return sha1_bytes(self.content)

    @property
    def size(self) -> int:
        return len(self.content)


def collect_local_files(
    project_path: str | Path,
    *,
    max_files: int = 250,
    max_total_bytes: int = 4_000_000,
) -> list[LocalFile]:
    root = Path(project_path).resolve()
    if not root.is_dir():
        raise ValueError("project_path_not_dir")
    skip = {".git", "__pycache__", ".venv", "venv", "node_modules", ".lumen", ".mypy_cache"}
    out: list[LocalFile] = []
    total = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        parts = path.relative_to(root).parts
        if any(p in skip for p in parts):
            continue
        if path.suffix.lower() in {".pyc", ".pyo", ".so", ".dll", ".exe", ".zip", ".tar", ".gz", ".whl"}:
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if len(data) > 1_500_000:
            continue
        total += len(data)
        if total > max_total_bytes or len(out) >= max_files:
            break
        out.append(LocalFile(rel=path.relative_to(root).as_posix(), content=data))
    if not out:
        raise ValueError("project_has_no_deployable_files")
    return out


class PlatformHostClient:
    def __init__(
        self,
        *,
        token: str | None = None,
        team_id: str | None = None,
        timeout: float = 90.0,
    ) -> None:
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

    def request_json(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        query: dict[str, str] | None = None,
    ) -> ApiResult:
        if not self._token:
            return ApiResult(ok=False, error="platform_host_token_missing")
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
            "User-Agent": "LumenHost/1.1",
        }
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        return self._send(method, path, headers=headers, data=data, query=query)

    def request_raw(
        self,
        method: str,
        path: str,
        *,
        raw: bytes,
        headers: dict[str, str],
        query: dict[str, str] | None = None,
    ) -> ApiResult:
        if not self._token:
            return ApiResult(ok=False, error="platform_host_token_missing")
        h = {
            "Authorization": f"Bearer {self._token}",
            "User-Agent": "LumenHost/1.1",
            **headers,
        }
        return self._send(method, path, headers=h, data=raw, query=query)

    def _send(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str],
        data: bytes | None,
        query: dict[str, str] | None,
    ) -> ApiResult:
        url = self._url(path, query)
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
                        parsed = {"raw": raw[:400]}
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
                    # Never echo secrets; strip common token fields
                    err_obj = j.get("error")
                    if isinstance(err_obj, dict):
                        detail = str(err_obj.get("message") or err_obj.get("code") or err_obj)[:400]
                    else:
                        detail = str(err_obj or j.get("message") or err_body)[:400]
            except Exception:
                pass
            logger.warning("platform_host_http status=%s path=%s", exc.code, path)
            return ApiResult(ok=False, status=int(exc.code or 0), error=f"http_{exc.code}:{detail}"[:500])
        except Exception as exc:
            logger.warning("platform_host_error %s path=%s", type(exc).__name__, path)
            return ApiResult(ok=False, error=f"network:{type(exc).__name__}")

    # ── Projects ──────────────────────────────────────────────────────────

    def create_project(self, name: str) -> ApiResult:
        return self.request_json("POST", "/v10/projects", body={"name": sanitize_project_name(name)})

    def get_project(self, name_or_id: str) -> ApiResult:
        pid = urllib.parse.quote(str(name_or_id), safe="")
        return self.request_json("GET", f"/v9/projects/{pid}")

    def ensure_project(self, name: str) -> ApiResult:
        name = sanitize_project_name(name)
        created = self.create_project(name)
        if created.ok:
            return created
        existing = self.get_project(name)
        if existing.ok:
            return existing
        return created

    def upsert_env(
        self,
        project_id_or_name: str,
        key: str,
        value: str,
        *,
        targets: list[str] | None = None,
        encrypted: bool = True,
    ) -> ApiResult:
        if not key:
            return ApiResult(ok=False, error="env_key_missing")
        body = {
            "key": str(key),
            "value": str(value),
            "type": "encrypted" if encrypted else "plain",
            "target": targets or ["production", "preview"],
            "upsert": True,
        }
        pid = urllib.parse.quote(str(project_id_or_name), safe="")
        # Primary: v10 upsert-style
        r = self.request_json("POST", f"/v10/projects/{pid}/env", body=body)
        if r.ok:
            return r
        # Fallback without upsert flag (older)
        body2 = {k: v for k, v in body.items() if k != "upsert"}
        return self.request_json("POST", f"/v10/projects/{pid}/env", body=body2)

    # ── Files + Deployments (real protocol) ───────────────────────────────

    def upload_file(self, content: bytes, *, digest: str | None = None) -> ApiResult:
        """POST /v2/files — body is raw octets; x-vercel-digest = sha1(content)."""
        dig = digest or sha1_bytes(content)
        return self.request_raw(
            "POST",
            "/v2/files",
            raw=content,
            headers={
                "Content-Type": "application/octet-stream",
                "Content-Length": str(len(content)),
                "x-vercel-digest": dig,
                "x-vercel-size": str(len(content)),
            },
        )

    def upload_local_files(self, files: Iterable[LocalFile]) -> ApiResult:
        """Upload every file; fail closed on first hard error (except already-exists)."""
        for f in files:
            r = self.upload_file(f.content, digest=f.sha)
            if r.ok:
                continue
            # 409 / already uploaded is fine
            if r.status in {200, 409}:
                continue
            if r.status == 400 and "already" in (r.error or "").lower():
                continue
            # Some accounts return 200 empty ok=True; if not ok and status 0 network
            if not r.ok and r.status not in {409}:
                return ApiResult(ok=False, status=r.status, error=f"upload_failed:{f.rel}:{r.error}"[:500])
        return ApiResult(ok=True, status=200, data={"uploaded": True})

    def create_deployment_from_files(
        self,
        *,
        project_name: str,
        files: list[LocalFile],
        target: str = "production",
        project_id: str = "",
    ) -> ApiResult:
        """Create deployment using UploadedFile refs (sha+size) after upload_file.

        Also attaches small files as inline base64+encoding when upload skipped.
        """
        name = sanitize_project_name(project_name)
        # Ensure blobs exist on platform
        up = self.upload_local_files(files)
        if not up.ok:
            return up

        file_refs: list[dict[str, Any]] = []
        for f in files:
            # Official UploadedFile shape
            file_refs.append({"file": f.rel, "sha": f.sha, "size": f.size})

        body: dict[str, Any] = {
            "name": name,
            "project": name,
            "files": file_refs,
            "target": target,
            "projectSettings": {
                "framework": None,
            },
        }
        if project_id:
            body["project"] = project_id
        return self.request_json("POST", "/v13/deployments", body=body)

    def create_inline_deployment(
        self,
        *,
        project_name: str,
        files: list[LocalFile],
        target: str = "production",
    ) -> ApiResult:
        """Fallback: inline files with encoding=base64 (official InlinedFile shape)."""
        import base64

        name = sanitize_project_name(project_name)
        inlined: list[dict[str, Any]] = []
        for f in files:
            if f.size > 400_000:
                return ApiResult(ok=False, error=f"file_too_large_for_inline:{f.rel}")
            inlined.append(
                {
                    "file": f.rel,
                    "data": base64.b64encode(f.content).decode("ascii"),
                    "encoding": "base64",
                }
            )
        body = {
            "name": name,
            "project": name,
            "files": inlined,
            "target": target,
            "projectSettings": {"framework": None},
        }
        return self.request_json("POST", "/v13/deployments", body=body)

    def get_deployment(self, deployment_id: str) -> ApiResult:
        did = urllib.parse.quote(str(deployment_id), safe="")
        return self.request_json("GET", f"/v13/deployments/{did}")

    def delete_deployment(self, deployment_id: str) -> ApiResult:
        did = urllib.parse.quote(str(deployment_id), safe="")
        return self.request_json("DELETE", f"/v13/deployments/{did}")

    def cancel_deployment(self, deployment_id: str) -> ApiResult:
        did = urllib.parse.quote(str(deployment_id), safe="")
        return self.request_json("PATCH", f"/v12/deployments/{did}/cancel")

    def list_deployment_events(self, deployment_id: str, *, limit: int = 50) -> ApiResult:
        """Best-effort deployment events (platform log stream)."""
        did = urllib.parse.quote(str(deployment_id), safe="")
        lim = max(1, min(100, int(limit)))
        # Try v3 then v2
        r = self.request_json("GET", f"/v3/deployments/{did}/events", query={"limit": str(lim)})
        if r.ok:
            return r
        return self.request_json("GET", f"/v2/deployments/{did}/events", query={"limit": str(lim)})

    def wait_ready(
        self,
        deployment_id: str,
        *,
        timeout_sec: float = 180.0,
        poll_sec: float = 2.5,
    ) -> ApiResult:
        """Poll until READY / ERROR / timeout."""
        deadline = time.time() + max(5.0, timeout_sec)
        last = ApiResult(ok=False, error="not_started")
        while time.time() < deadline:
            last = self.get_deployment(deployment_id)
            if not last.ok:
                time.sleep(poll_sec)
                continue
            state = str(last.mapping.get("readyState") or last.mapping.get("status") or "").upper()
            if state == "READY":
                return last
            if state in {"ERROR", "CANCELED", "FAILED"}:
                return ApiResult(
                    ok=False,
                    status=last.status,
                    data=last.data,
                    error=f"deploy_{state.lower()}",
                )
            time.sleep(poll_sec)
        return ApiResult(ok=False, status=last.status, data=last.data, error="deploy_timeout")


# Back-compat alias used by earlier tests
def collect_project_files(project_path: str | Path, **kwargs: Any) -> list[dict[str, str]]:
    import base64

    locals_ = collect_local_files(project_path, **kwargs)
    return [
        {"file": f.rel, "data": base64.b64encode(f.content).decode("ascii"), "sha": f.sha, "size": str(f.size)}
        for f in locals_
    ]


__all__ = [
    "PlatformHostClient",
    "ApiResult",
    "LocalFile",
    "token_configured",
    "sanitize_project_name",
    "collect_local_files",
    "collect_project_files",
    "sha1_bytes",
]
