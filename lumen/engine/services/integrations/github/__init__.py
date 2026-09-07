"""GitHub REST API integration (Issues, PRs, comments)."""
from .client import (
    GitHubClient,
    get_authenticated_user,
    list_user_repos,
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
    "get_authenticated_user",
    "list_user_repos",
    "add_issue_comment",
    "create_issue",
    "get_pull",
    "list_issue_comments",
    "list_pull_files",
    "create_pull_review",
    "list_repo_issues",
]
