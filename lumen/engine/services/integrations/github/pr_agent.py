"""GitHub PR agent — review + line comments + optional repair push.

Wired path (no fake stubs):
  webhook → clone head → execution_feedback → hybrid/preflight
  → line-level review comments from patches + failures
  → optional Cline repair → git commit + push to PR head branch
  → GitHub Pull Request Reviews API (with commit_id)

Env:
  GITHUB_TOKEN (required)
  GITHUB_PR_POST_REVIEW=1
  GITHUB_PR_AUTO_REPAIR=1
  GITHUB_PR_PUSH_REPAIR=1   # push commit to head branch after repair
  GITHUB_PR_REPAIR_STEPS=16
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _token() -> str:
    return (os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN") or "").strip()


def handle_pr_event(ev: dict[str, Any]) -> dict[str, Any]:
    payload = dict(ev.get("payload") or {})
    name = str(ev.get("name") or "")
    if not name.startswith("github.pull_request") and name != "github.pr.files":
        return {"ok": False, "skipped": True, "reason": "not_pr_event"}

    repo = str(payload.get("repo") or "")
    number = payload.get("number")
    if not repo or not number or "/" not in repo:
        return {"ok": False, "error": "missing_repo_or_number"}
    if not _token():
        return {"ok": False, "error": "GITHUB_TOKEN required"}

    owner, name_repo = repo.split("/", 1)
    number = int(number)

    from lumen.engine.services.integrations.github.client import (
        get_pull,
        list_pull_files,
        create_pull_review,
        add_issue_comment,
    )

    pr = get_pull(owner, name_repo, number)
    files_meta = list_pull_files(owner, name_repo, number) or []
    filenames = [str(f.get("filename") or "") for f in files_meta if f.get("filename")]

    head = pr.get("head") or {}
    clone_url = (head.get("repo") or {}).get("clone_url") or ""
    # Prefer SSH-less HTTPS with token rewrite
    ref = str(head.get("ref") or "")
    sha = str(head.get("sha") or "")
    head_owner = ((head.get("repo") or {}).get("owner") or {}).get("login") or owner
    head_name = (head.get("repo") or {}).get("name") or name_repo

    review: dict[str, Any] = {
        "title": pr.get("title"),
        "files_count": len(filenames),
        "files": filenames[:50],
        "additions": pr.get("additions"),
        "deletions": pr.get("deletions"),
        "sha": sha,
        "ref": ref,
    }

    if not clone_url:
        return {"ok": False, "error": "no_clone_url", "repo": repo, "number": number}

    try:
        review["pipeline"] = _run_clone_review_repair(
            clone_url=clone_url,
            ref=ref,
            focus_files=filenames,
            files_meta=files_meta,
            head_owner=head_owner,
            head_name=head_name,
        )
    except Exception as exc:
        logger.exception("pr pipeline failed")
        review["pipeline"] = {"ok": False, "error": f"{type(exc).__name__}:{exc}"}

    pipe = review.get("pipeline") or {}
    # Prefer new head SHA after push
    post_sha = str(pipe.get("pushed_sha") or sha or "")
    line_comments = list(pipe.get("line_comments") or [])[:20]

    body = _format_review_body(review)
    event = "COMMENT"
    if pipe.get("ok") is False and (pipe.get("execution") or {}).get("ok") is False:
        event = (os.getenv("GITHUB_PR_REVIEW_EVENT") or "REQUEST_CHANGES").strip() or "REQUEST_CHANGES"
    if event in {"REQUEST_CHANGES", "APPROVE"} and not post_sha:
        event = "COMMENT"

    review_resp = None
    comment_resp = None
    if (os.getenv("GITHUB_PR_POST_REVIEW") or "1").strip().lower() not in {"0", "false", "no"}:
        try:
            review_resp = create_pull_review(
                owner,
                name_repo,
                number,
                body,
                event=event if event in {"COMMENT", "REQUEST_CHANGES", "APPROVE"} else "COMMENT",
                commit_id=post_sha or None,
                comments=line_comments or None,
            )
        except Exception:
            logger.exception("create_pull_review failed; issue comment fallback")
            try:
                comment_resp = add_issue_comment(owner, name_repo, number, body)
            except Exception:
                logger.exception("issue comment also failed")

    job_id = _enqueue_job(repo, number, review)

    return {
        "ok": True,
        "repo": repo,
        "number": number,
        "files": len(filenames),
        "review_id": (review_resp or {}).get("id") if isinstance(review_resp, dict) else None,
        "comment_id": (comment_resp or {}).get("id") if isinstance(comment_resp, dict) else None,
        "review_event": event,
        "line_comments": len(line_comments),
        "pipeline_ok": bool(pipe.get("ok")),
        "execution_ok": (pipe.get("execution") or {}).get("ok"),
        "repaired": bool(pipe.get("repaired")),
        "pushed": bool(pipe.get("pushed")),
        "pushed_sha": pipe.get("pushed_sha"),
        "job_id": job_id,
    }


def _first_right_line_from_patch(patch: str) -> int | None:
    """Parse unified diff patch; return first added/context line number on RIGHT side."""
    if not patch:
        return None
    # @@ -a,b +c,d @@
    m = re.search(r"@@\s+-\d+(?:,\d+)?\s+\+(\d+)(?:,\d+)?\s+@@", patch)
    if not m:
        return None
    try:
        return max(1, int(m.group(1)))
    except ValueError:
        return None


def _build_line_comments(
    files_meta: list[dict[str, Any]],
    execution: dict[str, Any],
    preflights: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """GitHub review comments: path + line + side RIGHT (head)."""
    comments: list[dict[str, Any]] = []
    fail_text = []
    for ch in execution.get("checks") or []:
        if not ch.get("ok"):
            fail_text.append(
                f"**{ch.get('name')} failed**\n```\n{(ch.get('stderr') or ch.get('error') or ch.get('stdout') or '')[:600]}\n```"
            )

    # Map failures onto changed Python files via patch line
    py_files = [f for f in files_meta if str(f.get("filename") or "").endswith(".py")]
    for i, f in enumerate(py_files[:12]):
        path = str(f.get("filename") or "")
        line = _first_right_line_from_patch(str(f.get("patch") or ""))
        if line is None:
            line = 1
        body_parts = []
        if fail_text and i == 0:
            body_parts.append("Execution feedback for this PR:\n" + "\n".join(fail_text[:3]))
        elif fail_text:
            body_parts.append(f"See execution failures (related to changed path `{path}`).")
        pf = next((p for p in preflights if p.get("path") == path), None)
        if pf and not pf.get("error"):
            body_parts.append(
                f"Preflight: risk={pf.get('risk')} impact_score={pf.get('impact_score')} "
                f"impacted_files≈{pf.get('impacted')}"
            )
        if not body_parts:
            body_parts.append(f"Changed in this PR (`{path}`). Lumen reviewed this path.")
        comments.append({
            "path": path,
            "body": "\n\n".join(body_parts)[:65535],
            "line": int(line),
            "side": "RIGHT",
        })
    return comments


def _run_clone_review_repair(
    *,
    clone_url: str,
    ref: str,
    focus_files: list[str],
    files_meta: list[dict[str, Any]],
    head_owner: str,
    head_name: str,
) -> dict[str, Any]:
    token = _token()
    url = clone_url
    if token and "github.com" in url and "@" not in url:
        url = url.replace("https://", f"https://x-access-token:{token}@")

    with tempfile.TemporaryDirectory(prefix="lumen_pr_") as td:
        root = Path(td) / "repo"
        cmd = ["git", "clone", "--depth", "1"]
        if ref:
            cmd += ["--branch", ref]
        cmd += [url, str(root)]
        subprocess.run(cmd, check=True, capture_output=True, timeout=240)

        from lumen.engine.services.multi_agent.execution_feedback import run_execution_feedback
        from lumen.engine.services.code_intelligence.hybrid_retrieval import hybrid_search
        from lumen.engine.services.code_intelligence.repo_context import pack_repo_context_for_goal
        from lumen.engine.services.code_intelligence.preflight import analyze_edit_preflight

        execution = run_execution_feedback(root)
        q = " ".join(focus_files[:10]) or "pull request changes"
        hs = hybrid_search(root, q, top_k=10)
        pack = pack_repo_context_for_goal(root, q, extra_paths=focus_files[:12])

        preflights: list[dict[str, Any]] = []
        for rel in focus_files[:8]:
            if not rel.endswith(".py") or not (root / rel).is_file():
                continue
            try:
                pf = analyze_edit_preflight(root, rel, old_string="", new_string="")
                preflights.append({
                    "path": rel,
                    "impact_score": pf.get("impact_score"),
                    "impacted": len(pf.get("impacted_files_union") or []),
                    "risk": pf.get("risk"),
                })
            except Exception as exc:
                preflights.append({"path": rel, "error": type(exc).__name__})

        line_comments = _build_line_comments(files_meta, execution, preflights)

        repaired = False
        pushed = False
        pushed_sha = None
        repair_result: dict[str, Any] = {}
        do_repair = (os.getenv("GITHUB_PR_AUTO_REPAIR") or "0").strip().lower() in {"1", "true", "yes"}
        do_push = (os.getenv("GITHUB_PR_PUSH_REPAIR") or "0").strip().lower() in {"1", "true", "yes"}

        if do_repair and not execution.get("ok", True):
            try:
                from lumen.engine.services.cline_runtime.agent_loop import run_agent

                errors = []
                for ch in execution.get("checks") or []:
                    if not ch.get("ok"):
                        errors.append(
                            f"{ch.get('name')}: {(ch.get('stderr') or ch.get('error') or '')[:400]}"
                        )
                goal = (
                    "MODE=INCREMENTAL_REPAIR\n"
                    "Fix execution failures. Prefer edit_file. Do not wipe the project.\n"
                    + "\n".join(f"- {e}" for e in errors[:12])
                )
                state = run_agent(
                    work_dir=str(root),
                    goal=goal,
                    ir_dict={
                        "metadata": {
                            "mode": "incremental_repair",
                            "pre_read_files": focus_files[:16],
                            "findings": [{"message": e} for e in errors[:10]],
                        },
                        "project_context": {"file_list": focus_files[:16]},
                    },
                    max_steps=int(os.getenv("GITHUB_PR_REPAIR_STEPS") or "16"),
                )
                repaired = bool(getattr(state, "ok", False))
                repair_result = {
                    "ok": repaired,
                    "stop_reason": getattr(state, "stop_reason", ""),
                    "errors": list(getattr(state, "errors", None) or [])[:5],
                }
                if repaired:
                    execution = run_execution_feedback(root)
                    # Refresh line comments after repair
                    line_comments = _build_line_comments(files_meta, execution, preflights)

                if repaired and do_push and ref:
                    pushed, pushed_sha = _git_commit_and_push(root, ref, token)
            except Exception as exc:
                logger.exception("pr auto-repair failed")
                repair_result = {"ok": False, "error": f"{type(exc).__name__}:{exc}"}

        ok = bool(execution.get("ok", True))
        return {
            "ok": ok,
            "execution": execution,
            "embed_provider": hs.get("embed_provider"),
            "hybrid_hits": [
                {"path": h.get("path"), "score": h.get("score"), "name": h.get("name")}
                for h in (hs.get("hits") or [])[:10]
                if isinstance(h, dict)
            ],
            "context_files": list((pack.get("files") or {}).keys())[:12],
            "preflights": preflights,
            "line_comments": line_comments,
            "repaired": repaired,
            "repair": repair_result,
            "pushed": pushed,
            "pushed_sha": pushed_sha,
        }


def _git_commit_and_push(root: Path, ref: str, token: str) -> tuple[bool, str | None]:
    """Commit local repairs and push to the PR head branch (real git + GitHub)."""
    env = os.environ.copy()
    # Ensure remote uses token
    try:
        subprocess.run(
            ["git", "config", "user.email", os.getenv("LUMEN_GIT_EMAIL") or "lumen-bot@users.noreply.github.com"],
            cwd=str(root),
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", os.getenv("LUMEN_GIT_NAME") or "Lumen Bot"],
            cwd=str(root),
            check=True,
            capture_output=True,
        )
        st = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=True,
        )
        if not (st.stdout or "").strip():
            # no file changes
            sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(root),
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            return False, sha or None

        subprocess.run(["git", "add", "-A"], cwd=str(root), check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "fix: Lumen auto-repair (execution feedback)"],
            cwd=str(root),
            check=True,
            capture_output=True,
        )
        # push HEAD to branch ref
        push = subprocess.run(
            ["git", "push", "origin", f"HEAD:{ref}"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if push.returncode != 0:
            logger.error("git push failed: %s", (push.stderr or push.stdout or "")[:500])
            return False, None
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        return True, sha or None
    except Exception:
        logger.exception("git commit/push failed")
        return False, None


def _format_review_body(review: dict[str, Any]) -> str:
    pipe = review.get("pipeline") or {}
    exec_fb = pipe.get("execution") or {}
    lines = [
        "### Lumen PR review (execution + code intel + line comments)",
        f"- **Title:** {review.get('title')}",
        f"- **Files:** {review.get('files_count')}  (+{review.get('additions')} / -{review.get('deletions')})",
        f"- **SHA:** `{review.get('sha') or 'n/a'}`",
        f"- **repaired:** {pipe.get('repaired')}  **pushed:** {pipe.get('pushed')}  **new_sha:** `{pipe.get('pushed_sha') or 'n/a'}`",
        "",
        "#### Execution feedback",
        f"- ok: **{exec_fb.get('ok')}**",
    ]
    for ch in exec_fb.get("checks") or []:
        mark = "PASS" if ch.get("ok") else "FAIL"
        detail = (ch.get("stderr") or ch.get("error") or ch.get("stdout") or "")[:300]
        lines.append(f"- `{ch.get('name')}`: **{mark}** {detail}")
    lines.append("")
    lines.append(f"#### Code intel (embed=`{pipe.get('embed_provider')}`)")
    for h in pipe.get("hybrid_hits") or []:
        lines.append(f"- `{h.get('path')}` score={h.get('score')} ({h.get('name')})")
    lines.append(f"\n_Line comments posted: {len(pipe.get('line_comments') or [])}_")
    lines.append("\n_Lumen automated review — human judgment still required._")
    return "\n".join(lines)


def _enqueue_job(repo: str, number: int, review: dict[str, Any]) -> str | None:
    try:
        from lumen.platform.jobs import get_job_runner

        runner = get_job_runner()
        pipe = review.get("pipeline") or {}
        job = runner.enqueue(
            tenant_id=os.getenv("GITHUB_PR_TENANT_ID") or "github",
            kind="github_pr_review",
            input_data={
                "repo": repo,
                "number": number,
                "files": review.get("files") or [],
                "execution_ok": (pipe.get("execution") or {}).get("ok"),
                "repaired": pipe.get("repaired"),
                "pushed": pipe.get("pushed"),
                "pushed_sha": pipe.get("pushed_sha"),
                "line_comments": len(pipe.get("line_comments") or []),
            },
            message=f"pr-review:{repo}#{number}",
        )
        return getattr(job, "job_id", None) or (job.get("job_id") if isinstance(job, dict) else None)
    except Exception:
        logger.exception("enqueue github_pr_review failed")
        return None


def register_event_handlers() -> None:
    from lumen.engine.services.events import subscribe

    def _handler(ev: dict[str, Any]) -> None:
        try:
            handle_pr_event(ev)
        except Exception:
            logger.exception("pr_agent handler failed")

    for n in (
        "github.pull_request.opened",
        "github.pull_request.synchronize",
        "github.pull_request.reopened",
        "github.pr.files",
    ):
        subscribe(n, _handler)
    logger.info("github pr_agent handlers registered")


__all__ = ["handle_pr_event", "register_event_handlers"]
