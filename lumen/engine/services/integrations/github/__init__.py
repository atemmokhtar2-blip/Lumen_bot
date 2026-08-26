"""GitHub REST API integration (Issues, PRs, comments)."""
from .client import (
    GitHubClient,
    add_issue_comment,
    create_issue,
    get_pull,
    list_issue_comments,
    list_pull_files,
    create_pull_review,
    list_repo_issues,
)

__all__ = [
    "GitHubClient",
    "add_issue_comment",
    "create_issue",
    "get_pull",
    "list_issue_comments",
    "list_pull_files",
    "create_pull_review",
    "list_repo_issues",
]
