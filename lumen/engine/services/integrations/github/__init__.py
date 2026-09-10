"""GitHub REST API integration (Issues, PRs, comments) + App auth."""
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
from .app_auth import (
    github_app_configured,
    get_installation_token,
    build_app_jwt,
    clear_installation_token_cache,
    create_installation_access_token,
    get_installation,
    install_url,
    list_installation_repos,
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
    "github_app_configured",
    "get_installation_token",
    "build_app_jwt",
    "clear_installation_token_cache",
    "create_installation_access_token",
    "get_installation",
    "install_url",
    "list_installation_repos",
]
