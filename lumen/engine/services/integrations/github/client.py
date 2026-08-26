"""GitHub REST API v3 client using requests (official API, not a mock).

Auth: GITHUB_TOKEN or token argument (PAT with repo scope).
API base: https://api.github.com
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
        data = self.request("GET", f"/repos/{owner}/{repo}/pulls/{int(number)}/files")
        return list(data or [])

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


def _client(token: str | None = None) -> GitHubClient:
    return GitHubClient(token=token)


def list_repo_issues(owner: str, repo: str, **kw: Any) -> list[dict]:
    return _client(kw.pop("token", None)).list_issues(owner, repo, **kw)


def create_issue(owner: str, repo: str, title: str, body: str = "", **kw: Any) -> dict:
    return _client(kw.get("token")).create_issue(owner, repo, title, body)


def add_issue_comment(owner: str, repo: str, issue_number: int, body: str, **kw: Any) -> dict:
    return _client(kw.get("token")).add_comment(owner, repo, issue_number, body)


def list_issue_comments(owner: str, repo: str, issue_number: int, **kw: Any) -> list[dict]:
    return _client(kw.get("token")).list_comments(owner, repo, issue_number)


def get_pull(owner: str, repo: str, number: int, **kw: Any) -> dict:
    return _client(kw.get("token")).get_pull(owner, repo, number)


def list_pull_files(owner: str, repo: str, number: int, **kw: Any) -> list[dict]:
    return _client(kw.get("token")).list_pull_files(owner, repo, number)


def create_pull_review(
    owner: str, repo: str, number: int, body: str, **kw: Any
) -> dict:
    return _client(kw.get("token")).create_pull_review(
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
    "list_repo_issues",
    "create_issue",
    "add_issue_comment",
    "list_issue_comments",
    "get_pull",
    "list_pull_files",
    "create_pull_review",
]
