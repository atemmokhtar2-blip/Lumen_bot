"""GitHub PR agent — real review + optional repair, not a file-list summary.

Pipeline on pull_request opened/synchronize:
  1) GitHub REST: PR metadata + changed files
  2) Shallow clone of PR head (git)
  3) Critic execution feedback (compileall + import + pytest)
  4) Code intel hybrid_search + preflight on changed paths
  5) Optional Cline run_agent repair when execution fails
  6) GitHub Pull Request Review API (COMMENT / REQUEST_CHANGES)

Requires: GITHUB_TOKEN (repo), git, and for repair: LLM keys.
"""
from __future__ import annotations

import logging
import os
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

    clone_url = ((pr.get("head") or {}).get("repo") or {}).get("clone_url") or ""
    ref = (pr.get("head") or {}).get("ref") or ""
    sha = (pr.get("head") or {}).get("sha") or ""

    review: dict[str, Any] = {
        "title": pr.get("title"),
        "files_count": len(filenames),
        "files": filenames[:50],
        "additions": pr.get("additions"),
        "deletions": pr.get("deletions"),
        "sha": sha,
    }

    if clone_url:
        try:
            review["pipeline"] = _run_clone_review_repair(clone_url, ref, filenames)
        except Exception as exc:
            logger.exception("pr pipeline failed")
            review["pipeline"] = {"ok": False, "error": f"{type(exc).__name__}:{exc}"}
    else:
        review["pipeline"] = {"ok": False, "error": "no_clone_url"}

    pipe = review.get("pipeline") or {}
    body = _format_review_body(review)
    event = "COMMENT"
    if pipe.get("ok") is False and (pipe.get("execution") or {}).get("ok") is False:
        event = (os.getenv("GITHUB_PR_REVIEW_EVENT") or "REQUEST_CHANGES").strip() or "REQUEST_CHANGES"
    if pipe.get("ok") and (pipe.get("execution") or {}).get("ok"):
        event = (os.getenv("GITHUB_PR_APPROVE_EVENT") or "COMMENT").strip() or "COMMENT"

    review_resp = None
    comment_resp = None
    if (os.getenv("GITHUB_PR_POST_REVIEW") or "1").strip().lower() not in {"0", "false", "no"}:
        try:
            rev_event = event if event in {"COMMENT", "REQUEST_CHANGES", "APPROVE"} else "COMMENT"
            # GitHub requires commit_id for REQUEST_CHANGES / APPROVE — without SHA use COMMENT
            if rev_event in {"REQUEST_CHANGES", "APPROVE"} and not sha:
                rev_event = "COMMENT"
            review_resp = create_pull_review(
                owner,
                name_repo,
                number,
                body,
                event=rev_event,
                commit_id=sha or None,
            )
        except Exception:
            logger.exception("create_pull_review failed; falling back to issue comment")
            comment_resp = add_issue_comment(owner, name_repo, number, body)

    job_id = _enqueue_job(repo, number, review)

    return {
        "ok": True,
        "repo": repo,
        "number": number,
        "files": len(filenames),
        "review_id": (review_resp or {}).get("id") if isinstance(review_resp, dict) else None,
        "comment_id": (comment_resp or {}).get("id") if isinstance(comment_resp, dict) else None,
        "review_event": event,
        "pipeline_ok": bool(pipe.get("ok")),
        "execution_ok": (pipe.get("execution") or {}).get("ok"),
        "repaired": bool(pipe.get("repaired")),
        "job_id": job_id,
    }


def _run_clone_review_repair(clone_url: str, ref: str, focus_files: list[str]) -> dict[str, Any]:
    """Clone PR head → execution feedback → code intel → optional agent repair."""
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

        # 1) Critic-class execution feedback (real processes)
        from lumen.engine.services.multi_agent.execution_feedback import run_execution_feedback

        execution = run_execution_feedback(root)

        # 2) Code intel on changed paths
        from lumen.engine.services.code_intelligence.hybrid_retrieval import hybrid_search
        from lumen.engine.services.code_intelligence.repo_context import pack_repo_context_for_goal
        from lumen.engine.services.code_intelligence.preflight import analyze_edit_preflight

        q = " ".join(focus_files[:10]) or "pull request changes"
        hs = hybrid_search(root, q, top_k=10)
        pack = pack_repo_context_for_goal(root, q, extra_paths=focus_files[:12])
        preflights = []
        for rel in focus_files[:8]:
            if not rel.endswith(".py"):
                continue
            if not (root / rel).is_file():
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

        repaired = False
        repair_result: dict[str, Any] = {}
        # 3) Optional real repair via Cline agent_loop when execution failed
        do_repair = (os.getenv("GITHUB_PR_AUTO_REPAIR") or "0").strip().lower() in {"1", "true", "yes"}
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
                    "Fix the following execution failures in this repository. "
                    "Prefer edit_file. Do not wipe the project.\n"
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
                # Re-run execution after repair
                if repaired:
                    execution = run_execution_feedback(root)
            except Exception as exc:
                logger.exception("pr auto-repair failed")
                repair_result = {"ok": False, "error": f"{type(exc).__name__}:{exc}"}

        ok = bool(execution.get("ok", True)) and bool(hs.get("ok", True) or hs.get("hits"))
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
            "repaired": repaired,
            "repair": repair_result,
            "repo_path": str(root),
        }


def _format_review_body(review: dict[str, Any]) -> str:
    pipe = review.get("pipeline") or {}
    exec_fb = pipe.get("execution") or {}
    lines = [
        "### Lumen PR review (execution + code intel)",
        f"- **Title:** {review.get('title')}",
        f"- **Files:** {review.get('files_count')}  (+{review.get('additions')} / -{review.get('deletions')})",
        f"- **SHA:** `{review.get('sha') or 'n/a'}`",
        "",
        "#### Execution feedback",
        f"- ok: **{exec_fb.get('ok')}**",
    ]
    for ch in exec_fb.get("checks") or []:
        mark = "PASS" if ch.get("ok") else "FAIL"
        detail = (ch.get("stderr") or ch.get("error") or ch.get("stdout") or "")[:300]
        lines.append(f"- `{ch.get('name')}`: **{mark}** {detail}")
    if pipe.get("repaired"):
        lines.append(f"- auto-repair attempted: **yes** → {pipe.get('repair')}")
    lines.append("")
    lines.append(f"#### Code intel (embed=`{pipe.get('embed_provider')}`)")
    for h in pipe.get("hybrid_hits") or []:
        lines.append(f"- `{h.get('path')}` score={h.get('score')} ({h.get('name')})")
    if pipe.get("preflights"):
        lines.append("")
        lines.append("#### Preflight (changed Python files)")
        for pf in pipe["preflights"]:
            if pf.get("error"):
                lines.append(f"- `{pf.get('path')}`: error {pf.get('error')}")
            else:
                lines.append(
                    f"- `{pf.get('path')}` risk={pf.get('risk')} impact_score={pf.get('impact_score')} impacted={pf.get('impacted')}"
                )
    if pipe.get("error"):
        lines.append(f"\n_Pipeline error: {pipe.get('error')}_")
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
                "embed_provider": pipe.get("embed_provider"),
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
