"""GitHub REST API v3 client using requests (official API, not a mock).

Auth: explicit token, per-user credentials (App/PAT), or platform GITHUB_TOKEN.
API base: https://api.github.com
Prefer client_for_user(user_id) for Telegram-user operations.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import requests

logger = logging.getLogger(__name__)

_API = (os.getenv("GITHUB_API_BASE") or "https://api.github.com").rstrip("/")


class GitHubClient:
    def __init__(self, token: str | None = None) -> None:
        self.token = (token or os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN") or "").strip()
        if not self.token:
            raise ValueError("GITHUB_TOKEN required")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Lumen-Bot-Integration",
        }

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = path if path.startswith("http") else f"{_API}{path}"
        resp = requests.request(
            method.upper(),
            url,
            headers=self._headers(),
            timeout=float(os.getenv("GITHUB_HTTP_TIMEOUT") or "30"),
            **kwargs,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"github_api_{resp.status_code}:{resp.text[:500]}")
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    def list_issues(self, owner: str, repo: str, *, state: str = "open", per_page: int = 30) -> list[dict]:
        data = self.request(
            "GET",
            f"/repos/{owner}/{repo}/issues",
            params={"state": state, "per_page": per_page},
        )
        return list(data or [])

    def create_issue(self, owner: str, repo: str, title: str, body: str = "") -> dict:
        return self.request(
            "POST",
            f"/repos/{owner}/{repo}/issues",
            json={"title": title, "body": body or ""},
        )

    def add_comment(self, owner: str, repo: str, issue_number: int, body: str) -> dict:
        return self.request(
            "POST",
            f"/repos/{owner}/{repo}/issues/{int(issue_number)}/comments",
            json={"body": body},
        )

    def list_comments(self, owner: str, repo: str, issue_number: int) -> list[dict]:
        data = self.request(
            "GET",
            f"/repos/{owner}/{repo}/issues/{int(issue_number)}/comments",
        )
        return list(data or [])

    def get_pull(self, owner: str, repo: str, number: int) -> dict:
        return self.request("GET", f"/repos/{owner}/{repo}/pulls/{int(number)}")

    def list_pull_files(self, owner: str, repo: str, number: int) -> list[dict]:
        """Paginate PR files (GitHub max 100 per page)."""
        out: list[dict] = []
        page = 1
        while page <= 20:
            data = self.request(
                "GET",
                f"/repos/{owner}/{repo}/pulls/{int(number)}/files",
                params={"per_page": 100, "page": page},
            )
            batch = list(data or [])
            out.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return out

    def get_user(self) -> dict:
        """GET /user — authenticated user (official GitHub REST)."""
        data = self.request("GET", "/user")
        return dict(data or {})

    def list_user_repos(
        self,
        *,
        page: int = 1,
        per_page: int = 30,
        max_pages: int = 1,
        sort: str = "updated",
        affiliation: str = "owner,collaborator,organization_member",
    ) -> list[dict]:
        """GET /user/repos — official list of repos visible to the token.

        ``page`` is the GitHub API page (1-based). ``max_pages`` is how many
        consecutive API pages to fetch starting from ``page`` (UI usually uses 1).
        """
        out: list[dict] = []
        start = max(1, int(page))
        per_page = max(1, min(100, int(per_page)))
        max_pages = max(1, min(20, int(max_pages)))
        for offset in range(max_pages):
            pg = start + offset
            data = self.request(
                "GET",
                "/user/repos",
                params={
                    "per_page": per_page,
                    "page": pg,
                    "sort": sort,
                    "affiliation": affiliation,
                },
            )
            batch = list(data or [])
            for row in batch:
                if not isinstance(row, dict):
                    continue
                out.append(
                    {
                        "id": row.get("id"),
                        "full_name": row.get("full_name") or "",
                        "name": row.get("name") or "",
                        "private": bool(row.get("private")),
                        "html_url": row.get("html_url") or "",
                        "description": (row.get("description") or "")[:200],
                        "default_branch": row.get("default_branch") or "main",
                        "language": row.get("language") or "",
                        "updated_at": row.get("updated_at") or "",
                    }
                )
            if len(batch) < per_page:
                break
        return out

    def create_pull_review(
        self,
        owner: str,
        repo: str,
        number: int,
        body: str,
        *,
        event: str = "COMMENT",
        commit_id: str | None = None,
        comments: list[dict] | None = None,
    ) -> dict:
        """POST /repos/{owner}/{repo}/pulls/{number}/reviews (GitHub REST).

        REQUEST_CHANGES / APPROVE require commit_id (head SHA) per GitHub API.
        """
        payload: dict = {"body": body or "", "event": event}
        if commit_id:
            payload["commit_id"] = commit_id
        if comments:
            payload["comments"] = comments
        if event in {"REQUEST_CHANGES", "APPROVE"} and not commit_id:
            raise ValueError("commit_id required for REQUEST_CHANGES/APPROVE")
        return self.request(
            "POST",
            f"/repos/{owner}/{repo}/pulls/{int(number)}/reviews",
            json=payload,
        )


def resolve_access_token(
    *,
    token: str | None = None,
    user_id: int | None = None,
    owner: str | None = None,
    repo: str | None = None,
    allow_platform: bool = True,
) -> str:
    """Resolve a Bearer token for GitHub API/git.

    Priority:
      1) explicit token
      2) per-user credentials (GitHub App install or PAT)
      3) App installation token for owner/repo (platform App)
      4) platform GITHUB_TOKEN / GH_TOKEN (if allow_platform)
    """
    if token and str(token).strip():
        return str(token).strip()
    if user_id and int(user_id) > 0:
        try:
            from lumen.engine.services.integrations.connections.credentials import (
                resolve_github_token,
            )

            t = resolve_github_token(int(user_id))
            if t:
                return t
        except Exception:
            pass
    if owner and repo:
        try:
            from lumen.engine.services.integrations.github.app_auth import (
                get_token_for_repo,
                github_app_configured,
            )

            if github_app_configured():
                return get_token_for_repo(str(owner), str(repo))
        except Exception:
            pass
    if allow_platform:
        plat = (os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN") or "").strip()
        if plat:
            return plat
    raise ValueError("github_token_unavailable")


def _client(token: str | None = None, **kw: Any) -> GitHubClient:
    if token and str(token).strip():
        return GitHubClient(token=str(token).strip())
    resolved = resolve_access_token(
        user_id=kw.get("user_id"),
        owner=kw.get("owner"),
        repo=kw.get("repo"),
        allow_platform=bool(kw.get("allow_platform", True)),
    )
    return GitHubClient(token=resolved)


def client_for_user(user_id: int) -> GitHubClient:
    """GitHubClient authenticated as this Telegram user's connection."""
    return GitHubClient(token=resolve_access_token(user_id=int(user_id), allow_platform=False))


def client_for_repo(owner: str, repo: str) -> GitHubClient:
    """GitHubClient with App installation rights on owner/repo (or platform token)."""
    return GitHubClient(
        token=resolve_access_token(owner=str(owner), repo=str(repo), allow_platform=True)
    )


def _kw_client(owner: str | None = None, repo: str | None = None, **kw: Any) -> GitHubClient:
    """Build client from explicit token or resolve via user/repo/platform."""
    return _client(
        kw.get("token"),
        user_id=kw.get("user_id"),
        owner=owner or kw.get("owner"),
        repo=repo or kw.get("repo"),
        allow_platform=kw.get("allow_platform", True),
    )


def list_repo_issues(owner: str, repo: str, **kw: Any) -> list[dict]:
    client = _kw_client(owner, repo, **kw)
    kw.pop("token", None)
    kw.pop("user_id", None)
    kw.pop("allow_platform", None)
    return client.list_issues(owner, repo, **kw)


def create_issue(owner: str, repo: str, title: str, body: str = "", **kw: Any) -> dict:
    return _kw_client(owner, repo, **kw).create_issue(owner, repo, title, body)


def add_issue_comment(owner: str, repo: str, issue_number: int, body: str, **kw: Any) -> dict:
    return _kw_client(owner, repo, **kw).add_comment(owner, repo, issue_number, body)


def list_issue_comments(owner: str, repo: str, issue_number: int, **kw: Any) -> list[dict]:
    return _kw_client(owner, repo, **kw).list_comments(owner, repo, issue_number)


def get_pull(owner: str, repo: str, number: int, **kw: Any) -> dict:
    return _kw_client(owner, repo, **kw).get_pull(owner, repo, number)


def list_pull_files(owner: str, repo: str, number: int, **kw: Any) -> list[dict]:
    return _kw_client(owner, repo, **kw).list_pull_files(owner, repo, number)


def get_authenticated_user(**kw: Any) -> dict:
    return _kw_client(**kw).get_user()


def list_user_repos(**kw: Any) -> list[dict]:
    token = kw.pop("token", None)
    user_id = kw.pop("user_id", None)
    allow_platform = kw.pop("allow_platform", True)
    client = _client(token, user_id=user_id, allow_platform=allow_platform)
    return client.list_user_repos(**kw)


def create_pull_review(
    owner: str, repo: str, number: int, body: str, **kw: Any
) -> dict:
    client = _kw_client(owner, repo, **kw)
    return client.create_pull_review(
        owner,
        repo,
        number,
        body,
        event=str(kw.get("event") or "COMMENT"),
        commit_id=kw.get("commit_id"),
        comments=kw.get("comments"),
    )


__all__ = [
    "GitHubClient",
    "resolve_access_token",
    "client_for_user",
    "client_for_repo",
    "get_authenticated_user",
    "list_user_repos",
    "list_repo_issues",
    "create_issue",
    "add_issue_comment",
    "list_issue_comments",
    "get_pull",
    "list_pull_files",
    "create_pull_review",
]
