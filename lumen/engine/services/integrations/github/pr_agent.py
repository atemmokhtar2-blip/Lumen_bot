"""GitHub PR agent — real consumer for webhook events.

On pull_request opened/synchronize:
  1) Fetch PR + changed files via GitHub REST API
  2) Optionally clone shallow and run hybrid_search on the tree
  3) Post a review comment on the PR (GitHub API)

Requires: GITHUB_TOKEN with repo scope.
"""
from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _token() -> str:
    return (os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN") or "").strip()


def handle_pr_event(ev: dict[str, Any]) -> dict[str, Any]:
    """Event bus handler. ``ev`` is Event.to_dict() shape."""
    payload = dict(ev.get("payload") or {})
    name = str(ev.get("name") or "")
    if not name.startswith("github.pull_request") and name != "github.pr.files":
        return {"ok": False, "skipped": True, "reason": "not_pr_event"}

    repo = str(payload.get("repo") or "")
    number = payload.get("number")
    if not repo or not number:
        return {"ok": False, "error": "missing_repo_or_number"}
    if "/" not in repo:
        return {"ok": False, "error": "bad_repo"}
    if not _token():
        return {"ok": False, "error": "GITHUB_TOKEN required"}

    owner, name_repo = repo.split("/", 1)
    number = int(number)

    from lumen.engine.services.integrations.github.client import (
        get_pull,
        list_pull_files,
        add_issue_comment,
    )

    pr = get_pull(owner, name_repo, number)
    files = list_pull_files(owner, name_repo, number)
    filenames = [str(f.get("filename") or "") for f in (files or []) if f.get("filename")]

    analysis: dict[str, Any] = {
        "title": pr.get("title"),
        "files_count": len(filenames),
        "files": filenames[:40],
        "additions": pr.get("additions"),
        "deletions": pr.get("deletions"),
    }

    # Optional: shallow clone head and run real hybrid retrieval
    clone_url = (pr.get("head") or {}).get("repo", {}).get("clone_url") or ""
    ref = (pr.get("head") or {}).get("ref") or ""
    if clone_url and (os.getenv("GITHUB_PR_CLONE_ANALYZE") or "1").strip().lower() not in {"0", "false", "no"}:
        try:
            analysis["code_intel"] = _analyze_clone(clone_url, ref, filenames[:15])
        except Exception as exc:
            logger.exception("pr clone analyze failed")
            analysis["code_intel_error"] = f"{type(exc).__name__}:{exc}"

    body = _format_comment(analysis)
    posted = None
    if (os.getenv("GITHUB_PR_POST_COMMENT") or "1").strip().lower() not in {"0", "false", "no"}:
        posted = add_issue_comment(owner, name_repo, number, body)

    # Enqueue durable job record for UX / jobs list
    job_id = None
    try:
        from lumen.platform.jobs import get_job_runner
        runner = get_job_runner()
        job = runner.enqueue(
            tenant_id=os.getenv("GITHUB_PR_TENANT_ID") or "github",
            kind="github_pr_review",
            input_data={
                "repo": repo,
                "number": number,
                "files": filenames[:40],
                "analysis": {k: analysis[k] for k in ("title", "files_count", "additions", "deletions") if k in analysis},
            },
            message=f"pr:{repo}#{number}",
        )
        job_id = getattr(job, "job_id", None) or (job.get("job_id") if isinstance(job, dict) else None)
    except Exception:
        logger.exception("enqueue github_pr_review failed")

    return {
        "ok": True,
        "repo": repo,
        "number": number,
        "files": len(filenames),
        "comment_id": (posted or {}).get("id") if isinstance(posted, dict) else None,
        "job_id": job_id,
        "code_intel": analysis.get("code_intel"),
    }


def _analyze_clone(clone_url: str, ref: str, focus_files: list[str]) -> dict[str, Any]:
    """Shallow clone + hybrid_search — uses git CLI and code_intelligence."""
    import subprocess

    token = _token()
    url = clone_url
    if token and "github.com" in url and "@" not in url:
        url = url.replace("https://", f"https://x-access-token:{token}@")

    with tempfile.TemporaryDirectory(prefix="lumen_pr_") as td:
        root = Path(td)
        cmd = ["git", "clone", "--depth", "1"]
        if ref:
            cmd += ["--branch", ref]
        cmd += [url, str(root / "repo")]
        subprocess.run(cmd, check=True, capture_output=True, timeout=180)
        repo_path = root / "repo"
        from lumen.engine.services.code_intelligence.hybrid_retrieval import hybrid_search
        from lumen.engine.services.code_intelligence.repo_context import pack_repo_context_for_goal

        q = " ".join(focus_files[:8]) or "pull request changes"
        hs = hybrid_search(repo_path, q, top_k=8)
        pack = pack_repo_context_for_goal(repo_path, q, extra_paths=focus_files[:8])
        return {
            "embed_provider": hs.get("embed_provider"),
            "hits": [
                {"path": h.get("path"), "score": h.get("score"), "name": h.get("name")}
                for h in (hs.get("hits") or [])[:8]
                if isinstance(h, dict)
            ],
            "context_files": list((pack.get("files") or {}).keys())[:12],
            "ok": bool(hs.get("hits") or pack.get("files")),
        }


def _format_comment(analysis: dict[str, Any]) -> str:
    lines = [
        "### Lumen PR analysis",
        f"- **Title:** {analysis.get('title')}",
        f"- **Files changed:** {analysis.get('files_count')}",
        f"- **+{analysis.get('additions')} / -{analysis.get('deletions')}",
        "",
        "Changed paths:",
    ]
    for f in analysis.get("files") or []:
        lines.append(f"- `{f}`")
    ci = analysis.get("code_intel") or {}
    if ci:
        lines.append("")
        lines.append(f"Code intel (`embed_provider={ci.get('embed_provider')}`):")
        for h in ci.get("hits") or []:
            lines.append(f"- `{h.get('path')}` score={h.get('score')} ({h.get('name')})")
        if ci.get("context_files"):
            lines.append("Context pack: " + ", ".join(f"`{x}`" for x in ci["context_files"][:8]))
    if analysis.get("code_intel_error"):
        lines.append(f"\n_Code intel error: {analysis['code_intel_error']}_")
    lines.append("\n_Automated by Lumen — not a substitute for human review._")
    return "\n".join(lines)


def register_event_handlers() -> None:
    """Subscribe PR handlers on the process event bus (call at API startup)."""
    from lumen.engine.services.events import subscribe

    def _handler(ev: dict[str, Any]) -> None:
        try:
            handle_pr_event(ev)
        except Exception:
            logger.exception("pr_agent handler failed")

    for name in (
        "github.pull_request.opened",
        "github.pull_request.synchronize",
        "github.pull_request.reopened",
        "github.pr.files",
    ):
        subscribe(name, _handler)
    logger.info("github pr_agent handlers registered")


__all__ = ["handle_pr_event", "register_event_handlers"]
