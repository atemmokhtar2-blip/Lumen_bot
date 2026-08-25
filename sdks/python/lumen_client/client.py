from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Optional


class LumenClient:
    """Minimal B2B client — Python stdlib only."""

    def __init__(self, base_url: str, api_key: str, *, timeout: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def _request(
        self,
        method: str,
        path: str,
        body: Optional[dict] = None,
        *,
        auth: bool = True,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        data = None
        headers = {"Accept": "application/json"}
        if auth:
            headers["X-Api-Key"] = self.api_key
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(err_body)
            except Exception:
                parsed = {"error": err_body or e.reason}
            parsed["_status"] = e.code
            return parsed

    def health(self) -> dict:
        return self._request("GET", "/health", auth=False)

    def me(self) -> dict:
        return self._request("GET", "/v1/me")

    def generate(self, description: str, *, wait: bool = False) -> dict:
        return self._request(
            "POST",
            "/v1/generate",
            {"description": description, "wait": wait},
        )

    def get_job(self, job_id: str) -> dict:
        return self._request("GET", f"/v1/jobs/{job_id}")

    def list_jobs(self) -> dict:
        return self._request("GET", "/v1/jobs")

    def host_start(self, **payload: Any) -> dict:
        return self._request("POST", "/v1/hosts/start", payload)

    def host_stop(self, **payload: Any) -> dict:
        return self._request("POST", "/v1/hosts/stop", payload)

    def dashboard(self) -> dict:
        return self._request("GET", "/v1/dashboard")
