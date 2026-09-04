"""GitHub PR agent — real review + line comments + optional repair push.

Requires GITHUB_TOKEN. Optional:
  GITHUB_PR_POST_REVIEW=1
  GITHUB_PR_AUTO_REPAIR=1
  GITHUB_PR_PUSH_REPAIR=1
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
        rev_event = event if event in {"COMMENT", "REQUEST_CHANGES", "APPROVE"} else "COMMENT"
        try:
            review_resp = create_pull_review(
                owner,
                name_repo,
                number,
                body,
                event=rev_event,
                commit_id=post_sha or None,
                comments=line_comments or None,
            )
        except Exception as rev_exc:
            logger.warning("review with comments failed (%s); body-only", type(rev_exc).__name__)
            try:
                review_resp = create_pull_review(
                    owner,
                    name_repo,
                    number,
                    body,
                    event="COMMENT",
                    commit_id=post_sha or None,
                    comments=None,
                )
            except Exception:
                logger.exception("body-only review failed; issue comment")
                try:
                    comment_resp = add_issue_comment(owner, name_repo, number, body)
                except Exception:
                    logger.exception("issue comment failed")

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
    if not patch:
        return None
    m = re.search(r"@@\s+-\d+(?:,\d+)?\s+\+(\d+)(?:,\d+)?\s+@@", patch)
    if not m:
        return None
    try:
        return max(1, int(m.group(1)))
    except ValueError:
        return None


def _parse_traceback_locations(text: str) -> list[tuple[str, int]]:
    locs: list[tuple[str, int]] = []
    if not text:
        return locs
    for m in re.finditer(r'File ["\']([^"\']+)["\'], line (\d+)', text):
        path = m.group(1).replace("\\", "/").lstrip("./")
        locs.append((path, int(m.group(2))))
    for m in re.finditer(r"([A-Za-z0-9_./\\-]+\.py):(\d+)(?::\d+)?", text):
        locs.append((m.group(1).replace("\\", "/"), int(m.group(2))))
    seen: set[tuple[str, int]] = set()
    out: list[tuple[str, int]] = []
    for item in locs:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _line_in_patch(patch: str, line: int) -> bool:
    if not patch or line < 1:
        return False
    new_line: int | None = None
    remaining = 0
    for raw in patch.splitlines():
        hm = re.match(r"@@\s+-\d+(?:,\d+)?\s+\+(\d+)(?:,(\d+))?\s+@@", raw)
        if hm:
            new_line = int(hm.group(1))
            remaining = int(hm.group(2) or "1")
            continue
        if new_line is None:
            continue
        if raw.startswith("\\") or raw.startswith("diff "):
            continue
        if raw.startswith("-"):
            continue
        if new_line == line:
            return True
        new_line += 1
        remaining -= 1
        if remaining <= 0:
            new_line = None
    return False


def _build_line_comments(
    files_meta: list[dict[str, Any]],
    execution: dict[str, Any],
    preflights: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Comments only when traceback maps to a PR file or preflight is high-impact."""
    comments: list[dict[str, Any]] = []
    by_name = {str(f.get("filename") or ""): f for f in files_meta if f.get("filename")}

    blobs = []
    for ch in execution.get("checks") or []:
        if not ch.get("ok"):
            blobs.append(str(ch.get("stderr") or ch.get("error") or ch.get("stdout") or ""))
    blob = "\n".join(blobs)

    for path, line in _parse_traceback_locations(blob)[:15]:
        match = None
        for fn, meta in by_name.items():
            if fn == path or path.endswith(fn) or fn.endswith(path.split("/")[-1]):
                match = (fn, meta)
                break
        if not match:
            continue
        fn, meta = match
        patch = str(meta.get("patch") or "")
        use_line = line
        if not _line_in_patch(patch, line):
            alt = _first_right_line_from_patch(patch)
            if alt is None:
                continue
            use_line = alt
        comments.append(
            {
                "path": fn,
                "body": f"Execution error references this location:\n```\n{blob[:800]}\n```",
                "line": int(use_line),
                "side": "RIGHT",
            }
        )

    for pf in preflights:
        path = str(pf.get("path") or "")
        if pf.get("error") or path not in by_name:
            continue
        score = float(pf.get("impact_score") or 0)
        impacted = int(pf.get("impacted") or 0)
        if score < 0.5 and impacted < 5:
            continue
        if any(c["path"] == path for c in comments):
            continue
        patch = str(by_name[path].get("patch") or "")
        line = _first_right_line_from_patch(patch)
        if line is None:
            continue
        comments.append(
            {
                "path": path,
                "body": (
                    f"High blast-radius change on `{path}`: "
                    f"impact_score={score}, impacted_files≈{impacted}, risk={pf.get('risk')}."
                ),
                "line": int(line),
                "side": "RIGHT",
            }
        )

    return comments[:20]


def _safe_https_github_clone_url(clone_url: str) -> str:
    """Accept only https://github.com/... without embedded credentials."""
    from urllib.parse import urlparse, urlunparse
    raw = (clone_url or "").strip()
    if not raw:
        raise ValueError("empty_clone_url")
    # Strip any accidental userinfo before parse
    if "://" in raw and "@" in raw.split("://", 1)[1].split("/", 1)[0]:
        # Reject URLs that already embed credentials
        raise ValueError("clone_url_must_not_embed_credentials")
    parsed = urlparse(raw)
    if parsed.scheme != "https":
        raise ValueError("clone_url_must_be_https")
    host = (parsed.hostname or "").lower()
    if host not in {"github.com", "www.github.com"}:
        raise ValueError(f"clone_url_host_not_github:{host}")
    # Rebuild without userinfo/query/fragment
    path = parsed.path or ""
    if not path.endswith(".git"):
        path = path.rstrip("/") + ".git"
    return urlunparse(("https", "github.com", path, "", "", ""))


def _git_clone_authenticated(clone_url: str, dest: Path, *, ref: str = "") -> None:
    """Clone via GIT_ASKPASS — token never appears in argv or remote URL."""
    token = (_token() or "").strip()
    url = _safe_https_github_clone_url(clone_url)
    cmd = ["git", "-c", "credential.helper=", "clone", "--depth", "1"]
    if ref:
        cmd += ["--branch", ref]
    cmd += [url, str(dest)]
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "never"
    askpass_path = None
    try:
        if token:
            # Askpass script: never logs; token only in env LUMEN_GIT_TOKEN
            fd, askpass_path = tempfile.mkstemp(prefix="lumen_askpass_", suffix=".sh")
            os.close(fd)
            Path(askpass_path).write_text(
                (
                    "#!/bin/sh\n"
                    "case \"$1\" in\n"
                    "  *Username*|username*) printf '%s\\n' 'x-access-token' ;;\n"
                    "  *Password*|password*) printf '%s\\n' \"$LUMEN_GIT_TOKEN\" ;;\n"
                    "  *) printf '\\n' ;;\n"
                    "esac\n"
                ),
                encoding="utf-8",
            )

            os.chmod(askpass_path, 0o700)
            env["GIT_ASKPASS"] = askpass_path
            env["SSH_ASKPASS"] = askpass_path
            env["LUMEN_GIT_TOKEN"] = token
            env["GIT_ASKPASS_REQUIRE"] = "force"
        # Never pass token-bearing URL; redact in CalledProcessError paths
        proc = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=240,
            check=False,
        )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "")[:400]
            # Defense: strip token if somehow echoed
            if token:
                err = err.replace(token, "***")
            raise RuntimeError(f"git_clone_failed:rc={proc.returncode}:{err}")
    finally:
        if askpass_path:
            try:
                os.unlink(askpass_path)
            except OSError:
                pass
        env.pop("LUMEN_GIT_TOKEN", None)


def _run_clone_review_repair(
    *,
    clone_url: str,
    ref: str,
    focus_files: list[str],
    files_meta: list[dict[str, Any]],
    head_owner: str,
    head_name: str,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="lumen_pr_") as td:
        root = Path(td) / "repo"
        _git_clone_authenticated(clone_url, root, ref=ref or "")

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
                preflights.append(
                    {
                        "path": rel,
                        "impact_score": pf.get("impact_score"),
                        "impacted": len(pf.get("impacted_files_union") or []),
                        "risk": pf.get("risk"),
                    }
                )
            except Exception as exc:
                preflights.append({"path": rel, "error": type(exc).__name__})

        # Deep per-hunk analysis (ast / tree-sitter / py_compile on changed files)
        deep = {}
        try:
            from lumen.engine.services.integrations.github.pr_deep_review import (
                deep_review_pr_files,
                findings_to_line_comments,
            )
            deep = deep_review_pr_files(root, files_meta)
        except Exception as _deep_exc:
            deep = {"ok": False, "error": type(_deep_exc).__name__, "findings": []}

        line_comments = _build_line_comments(files_meta, execution, preflights)
        # Merge deep findings as line comments (signal-only)
        try:
            deep_comments = findings_to_line_comments(list(deep.get("findings") or []))
            # prefer deep comments first
            seen = {(c["path"], c["line"]) for c in deep_comments}
            for c in line_comments:
                if (c["path"], c["line"]) not in seen:
                    deep_comments.append(c)
            line_comments = deep_comments[:25]
        except Exception:
            pass

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
                        "user_id": int(os.getenv("GITHUB_PR_USER_ID") or "0"),
                        "metadata": {
                            "mode": "incremental_repair",
                            "pre_read_files": focus_files[:16],
                            "findings": [{"message": e} for e in errors[:10]],
                            "user_id": int(os.getenv("GITHUB_PR_USER_ID") or "0"),
                        },
                        "project_context": {"file_list": focus_files[:16]},
                    },
                    max_steps=int(os.getenv("GITHUB_PR_REPAIR_STEPS") or "16"),
                )
                written = list(getattr(state, "files_written", None) or [])
                # Real dirty check — do not trust agent.ok alone
                dirty = _git_is_dirty(root)
                execution_before_ok = bool(execution.get("ok"))
                execution = run_execution_feedback(root)
                execution_after_ok = bool(execution.get("ok"))
                # "repaired" only if disk changed AND execution now passes
                repaired = bool(dirty or written) and execution_after_ok and not execution_before_ok
                # If already was going to fail and still fails but files changed → attempted only
                repair_result = {
                    "ok": repaired,
                    "attempted": True,
                    "agent_ok": bool(getattr(state, "ok", False)),
                    "files_written": written[:20],
                    "git_dirty": dirty,
                    "execution_before_ok": execution_before_ok,
                    "execution_after_ok": execution_after_ok,
                    "stop_reason": getattr(state, "stop_reason", ""),
                    "errors": list(getattr(state, "errors", None) or [])[:5],
                }
                try:
                    deep = deep_review_pr_files(root, files_meta)
                except Exception:
                    pass
                line_comments = _build_line_comments(files_meta, execution, preflights)
                try:
                    from lumen.engine.services.integrations.github.pr_deep_review import findings_to_line_comments
                    deep_comments = findings_to_line_comments(list((deep or {}).get("findings") or []))
                    seen = {(c["path"], c["line"]) for c in deep_comments}
                    for c in line_comments:
                        if (c["path"], c["line"]) not in seen:
                            deep_comments.append(c)
                    line_comments = deep_comments[:25]
                except Exception:
                    pass
                # Push only with real dirty tree (never on agent.ok alone)
                if do_push and ref and dirty:
                    pushed, pushed_sha = _git_commit_and_push(root, ref)
                    repair_result["pushed"] = pushed
            except Exception as exc:
                logger.exception("pr auto-repair failed")
                repair_result = {"ok": False, "error": f"{type(exc).__name__}:{exc}"}

        return {
            "ok": bool(execution.get("ok", True)) and bool(deep.get("ok", True)),
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
            "deep_review": {
                "ok": deep.get("ok"),
                "analyzed_files": deep.get("analyzed_files"),
                "findings_count": len(deep.get("findings") or []),
                "findings": list(deep.get("findings") or [])[:20],
                "hybrid": deep.get("hybrid"),
            },
            "repaired": repaired,
            "repair": repair_result,
            "pushed": pushed,
            "pushed_sha": pushed_sha,
        }


def _git_is_dirty(root: Path) -> bool:
    try:
        st = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=True,
        )
        return bool((st.stdout or "").strip())
    except Exception:
        return False


def _git_commit_and_push(root: Path, ref: str) -> tuple[bool, str | None]:

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
        "### Lumen PR review",
        f"- **Title:** {review.get('title')}",
        f"- **Files:** {review.get('files_count')} (+{review.get('additions')} / -{review.get('deletions')})",
        f"- **SHA:** `{review.get('sha') or 'n/a'}`",
        f"- **repaired/pushed:** {pipe.get('repaired')} / {pipe.get('pushed')} (`{pipe.get('pushed_sha') or 'n/a'}`)",
        "",
        "#### Execution",
        f"- ok: **{exec_fb.get('ok')}**",
    ]
    for ch in exec_fb.get("checks") or []:
        mark = "PASS" if ch.get("ok") else "FAIL"
        detail = (ch.get("stderr") or ch.get("error") or ch.get("stdout") or "")[:300]
        lines.append(f"- `{ch.get('name')}`: **{mark}** {detail}")
    lines.append(f"\n_Line comments (signal-only): {len(pipe.get('line_comments') or [])}_")
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
