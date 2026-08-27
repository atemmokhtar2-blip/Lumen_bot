"""Critic / Reviewer — Phase A+: structured findings + observe + multi-check QA.

Produces CritiqueFinding list on state.extensions["findings"] for Repair/Worker.
"""
from __future__ import annotations

import ast
from pathlib import Path

from ..execution_feedback import run_execution_feedback as _execution_feedback_sandbox
from typing import Any, Optional

from ..context_views import critic_view
from ..findings import CritiqueFinding, findings_to_errors
from ..protocol import Agent
from ..state import AgentRole, AgentState, AgentStatus


class CriticAgent(Agent):
    role = AgentRole.CRITIC.value
    name = "critic"
    order = 40
    role_alias = "reviewer"

    def can_run(self, state: AgentState) -> bool:
        path = (state.generated_path or "").strip()
        return bool(state.build_success and path)

    def run(self, state: AgentState, *, context: Optional[dict[str, Any]] = None) -> AgentState:
        state.transition(AgentStatus.QA, role=AgentRole.CRITIC, force=True)
        view = critic_view(state)
        path = str(view.get("generated_path") or "").strip()
        findings: list[CritiqueFinding] = []
        warnings: list[str] = []
        details: dict[str, Any] = {}

        if not path or not Path(path).is_dir():
            findings.append(CritiqueFinding(
                code="no_project",
                severity="error",
                message="No generated project directory",
                fix_hint="Worker must write a project with main.py under work_dir",
            ))
            return self._finish(state, findings, warnings, details)

        root = Path(path)

        # --- 1) Deliverables vs execution plan ---
        plan = (state.extensions or {}).get("execution_plan") or {}
        deliverables = list(plan.get("deliverables") or [
            "main.py", "app/handlers.py", "requirements.txt", "README.md", ".env.example",
        ])
        missing_del = [d for d in deliverables if not (root / d).exists()]
        details["deliverables"] = {"required": deliverables, "missing": missing_del}
        for d in missing_del:
            findings.append(CritiqueFinding(
                code="missing_deliverable",
                severity="error",
                message=f"Missing required file: {d}",
                path=d,
                fix_hint=f"Create {d} with appropriate content for a Telegram bot project",
            ))

        # --- 2) Syntax AST for all Python files ---
        syn_errors = []
        py_files = list(root.rglob("*.py"))
        details["py_files"] = len(py_files)
        if not py_files:
            findings.append(CritiqueFinding(
                code="no_python",
                severity="error",
                message="No Python files in project",
                fix_hint="Write main.py and any modules",
            ))
        for py in py_files[:40]:
            try:
                src = py.read_text(encoding="utf-8", errors="replace")
                ast.parse(src, filename=str(py))
            except SyntaxError as e:
                rel = str(py.relative_to(root))
                msg = f"{e.msg} at line {e.lineno}"
                syn_errors.append(f"{rel}:{msg}")
                findings.append(CritiqueFinding(
                    code="syntax_error",
                    severity="error",
                    message=msg,
                    path=rel,
                    fix_hint=f"Fix Python syntax in {rel} line {e.lineno}: {e.msg}",
                ))
        details["syntax"] = {"ok": not syn_errors, "errors": syn_errors[:15]}

        # --- 3) Entry + token env convention ---
        main = root / "main.py"
        bot = root / "bot.py"
        entry = main if main.is_file() else (bot if bot.is_file() else None)
        if entry is None:
            findings.append(CritiqueFinding(
                code="no_entry",
                severity="error",
                message="Neither main.py nor bot.py present",
                fix_hint="Add main.py as Telegram bot entry using Application.run_polling or equivalent",
            ))
        else:
            src = entry.read_text(encoding="utf-8", errors="replace")
            if "BOT_TOKEN" not in src and "TELEGRAM_BOT_TOKEN" not in src and "token" not in src.lower():
                findings.append(CritiqueFinding(
                    code="no_token_env",
                    severity="error",
                    message="Entry does not reference bot token env",
                    path=entry.name,
                    fix_hint="Read BOT_TOKEN or TELEGRAM_BOT_TOKEN from os.environ",
                ))
            if "telegram" not in src.lower() and "Application" not in src:
                findings.append(CritiqueFinding(
                    code="no_telegram_api",
                    severity="warning",
                    message="Entry may not use python-telegram-bot Application",
                    path=entry.name,
                    fix_hint="Use telegram.ext.Application for a standard bot",
                ))
                warnings.append("no_telegram_api_heuristic")

        # --- 4) gen_verify ---
        try:
            from lumen.engine.services.gen_verify import verify_generated_project
            rep = verify_generated_project(path)
            gv = rep.to_dict() if hasattr(rep, "to_dict") else {"ok": bool(getattr(rep, "ok", False))}
            details["gen_verify"] = gv
            if not gv.get("ok"):
                for e in list(gv.get("errors") or ["gen_verify_failed"])[:10]:
                    findings.append(CritiqueFinding(
                        code="gen_verify",
                        severity="error",
                        message=str(e)[:300],
                        fix_hint="Address gen_verify failure: " + str(e)[:200],
                    ))
            warnings.extend(list(gv.get("warnings") or [])[:10])
        except Exception as exc:
            warnings.append(f"gen_verify_error:{type(exc).__name__}")
            details["gen_verify"] = {"ok": False, "error": type(exc).__name__}

        # --- 5) static_dev_gate ---
        try:
            from lumen.engine.services.static_dev_gate.engine import analyze
            sg = analyze(path)
            if hasattr(sg, "ok"):
                flist = list(getattr(sg, "findings", None) or [])
                err_msgs = []
                for f in flist:
                    if getattr(f, "severity", "") != "error":
                        continue
                    rid = str(getattr(f, "rule_id", "") or "static")
                    msg = str(getattr(f, "message_ar", None) or getattr(f, "message", "") or "")[:250]
                    fpath = str(getattr(f, "path", "") or "")[:200]
                    err_msgs.append(f"{rid}:{msg}")
                    findings.append(CritiqueFinding(
                        code=f"static:{rid}",
                        severity="error",
                        message=msg,
                        path=fpath,
                        fix_hint=f"Satisfy static rule {rid}: {msg}",
                    ))
                details["static_dev_gate"] = {
                    "ok": bool(sg.ok),
                    "errors": int(getattr(sg, "errors", 0) or 0),
                    "warnings": int(getattr(sg, "warnings", 0) or 0),
                    "error_messages": err_msgs[:15],
                }
            elif isinstance(sg, dict) and sg.get("ok") is False:
                findings.append(CritiqueFinding(
                    code="static_dev_gate",
                    severity="error",
                    message="static_dev_gate_failed",
                    fix_hint="Fix static analysis errors in generated project",
                ))
        except Exception as exc:
            warnings.append(f"static_gate_skip:{type(exc).__name__}")
            details["static_dev_gate"] = {"skipped": type(exc).__name__}

        # --- 6) Observe smoke ---
        try:
            from lumen.bot.generation_steps.helpers import _smoke_test_project
            smoke_ok, smoke_msg = _smoke_test_project(root, seconds=4.0)
            details["observe_smoke"] = {"ok": bool(smoke_ok), "message": str(smoke_msg)[:400]}
            if not smoke_ok:
                findings.append(CritiqueFinding(
                    code="observe_smoke",
                    severity="error",
                    message=str(smoke_msg)[:300],
                    fix_hint="Ensure project imports cleanly and entry is runnable",
                ))
        except Exception as exc:
            if entry is None:
                findings.append(CritiqueFinding(
                    code="observe_no_entry",
                    severity="error",
                    message="Cannot smoke-test without entry file",
                    fix_hint="Add main.py",
                ))
            else:
                warnings.append(f"observe_smoke_skip:{type(exc).__name__}")
                details["observe_smoke"] = {"skipped": type(exc).__name__}

        # --- 7) Plan feature coverage (soft if names not in source) ---
        feats = list(plan.get("features") or [])[:15]
        if feats and entry and entry.is_file():
            blob = entry.read_text(encoding="utf-8", errors="replace").lower()
            for mod in root.glob("modules/*.py"):
                blob += mod.read_text(encoding="utf-8", errors="replace").lower()
            missing_feat = [f for f in feats if f.lower().replace("-", "_") not in blob]
            details["feature_coverage"] = {"missing": missing_feat[:10]}
            for f in missing_feat[:8]:
                findings.append(CritiqueFinding(
                    code="feature_gap",
                    severity="warning",
                    message=f"Feature '{f}' not clearly present in code",
                    fix_hint=f"Implement handler/module for feature '{f}'",
                ))
                warnings.append(f"feature_gap:{f}")

        # Phase C: Tree-sitter/BM25 intelligence snapshot on the generated project
        try:
            from lumen.engine.services.code_intelligence import blast_radius, hybrid_search
            br = blast_radius(str(root), path="main.py", max_depth=2)
            q = (state.user_text or state.spec_request or "telegram bot")[:200]
            hs = hybrid_search(str(root), q, top_k=5)
            details["code_intelligence"] = {
                "blast_radius_ok": br.get("ok"),
                "impacted_files": (br.get("impacted_files") or [])[:20],
                "impacted_count": br.get("impacted_count"),
                "retrieval_hits": [
                    {"name": h.get("name"), "path": h.get("path"), "score": h.get("score")}
                    for h in (hs.get("hits") or [])[:5]
                ],
                "engine": "tree-sitter+jedi-ready+bm25",
            }
        except Exception as _ci_exc:
            details["code_intelligence_error"] = type(_ci_exc).__name__

        return self._finish(state, findings, warnings, details)

    def _finish(
        self,
        state: AgentState,
        findings: list[CritiqueFinding],
        warnings: list[str],
        details: dict[str, Any],
    ) -> AgentState:
        
        try:
            exec_fb = _execution_feedback_sandbox(Path(path))
            details["execution_feedback"] = exec_fb
            state.extensions["execution_feedback"] = exec_fb
            if not exec_fb.get("ok", True):
                for ch in exec_fb.get("checks") or []:
                    if ch.get("ok"):
                        continue
                    msg = (ch.get("stderr") or ch.get("error") or ch.get("stdout") or "execution_failed")[:400]
                    # Missing optional runtime deps (telegram/discord not installed in CI) = warning, not hard fail
                    soft = any(
                        x in msg
                        for x in (
                            "ModuleNotFoundError",
                            "No module named",
                            "ImportError",
                        )
                    )
                    findings.append(CritiqueFinding(
                        code=f"exec_{ch.get('name') or 'check'}",
                        severity="warning" if soft else "error",
                        message=msg,
                        fix_hint="Install project requirements in runtime image, or fix real runtime errors",
                    ))
        except Exception as _ef_exc:
            warnings.append(f"execution_feedback_skip:{type(_ef_exc).__name__}")

        # Optional visual check via Playwright when browser tools enabled
        try:
            import os as _os
            if (_os.getenv("BROWSER_USE_ENABLED") or "0").strip().lower() in {"1", "true", "yes"}:
                from lumen.engine.services.browser_use import browse_url, screenshot, is_playwright_available
                if is_playwright_available():
                    url = (_os.getenv("CRITIC_VISUAL_URL") or "").strip()
                    if url:
                        br = browse_url(url)
                        if br.get("ok"):
                            shot = screenshot(str(br.get("session_id") or ""), path=str(Path(path) / "critic_shot.png"))
                            details["visual_check"] = {"browse": br, "screenshot": shot}
                            if not shot.get("ok"):
                                findings.append(CritiqueFinding(
                                    code="visual_screenshot_failed",
                                    severity="warning",
                                    message=str(shot.get("error") or "screenshot_failed")[:200],
                                    fix_hint="Check Playwright browser install",
                                ))
                        else:
                            details["visual_check"] = {"browse": br}
        except Exception as _vis_exc:
            warnings.append(f"visual_check_skip:{type(_vis_exc).__name__}")


        # Acceptance (AST) BEFORE qa_passed — official gate
        try:
            from ..acceptance_check import evaluate_tree, evaluate_task
            from ..task_tree import TaskTree
            work = Path(
                state.generated_path
                or (state.extensions or {}).get("work_dir")
                or "."
            )
            tree_raw = (state.extensions or {}).get("task_tree")
            acc = None
            if isinstance(tree_raw, dict) and tree_raw.get("nodes"):
                tree = TaskTree.from_dict(tree_raw)
                acc = evaluate_tree(work, tree, strict=True)
            else:
                acc = evaluate_task(
                    work,
                    files=["main.py"],
                    acceptance=["main.py exists", "compileall passes"],
                    strict=True,
                )
            state.extensions = dict(state.extensions or {})
            state.extensions["acceptance_report"] = acc
            details["acceptance"] = {
                "ok": acc.get("ok"),
                "failed_count": acc.get("failed_count") if "failed_count" in acc else sum(
                    1 for tr in (acc.get("tasks") or {}).values() for _ in (tr.get("failed") or [])
                ),
            }
            if not acc.get("ok"):
                # fold into findings as errors so qa_passed stays false
                failed_items = list(acc.get("failed") or [])
                if not failed_items:
                    for tid, tr in (acc.get("tasks") or {}).items():
                        for f in tr.get("failed") or []:
                            failed_items.append({**f, "task": tid})
                for f in failed_items[:20]:
                    findings.append(CritiqueFinding(
                        code="acceptance_failed",
                        severity="error",
                        message=str(f.get("id") or f.get("detail") or f)[:300],
                        path=str(f.get("path") or ""),
                        fix_hint="Satisfy task acceptance criteria before deliver",
                    ))
                state.record(AgentRole.CRITIC, "acceptance_failed", f"n={len(failed_items)}")
            else:
                state.record(AgentRole.CRITIC, "acceptance_passed", "ok")
        except Exception:
            logger.exception("acceptance_check failed")

        errors = findings_to_errors(findings)
        # warnings from findings
        for f in findings:
            if f.severity == "warning":
                warnings.append(f"{f.code}: {f.message}")
        state.extensions["findings"] = [f.to_dict() for f in findings]
        state.qa_passed = len(errors) == 0
        state.qa_report = {
            "ok": state.qa_passed,
            "errors": errors[:40],
            "warnings": warnings[:40],
            "details": details,
            "attempt": state.attempts,
            "findings_count": len(findings),
            "role_alias": "critic",
        }
        state.record(
            AgentRole.CRITIC,
            "qa_done",
            f"ok={state.qa_passed} errors={len(errors)} findings={len(findings)} attempt={state.attempts}",
        )
        try:
            from ..trajectory import append_trajectory
            append_trajectory(
                state,
                step="critic_qa",
                role=AgentRole.CRITIC.value,
                ok=state.qa_passed,
                detail=f"errors={len(errors)} findings={len(findings)}",
                payload={"errors": errors[:8], "findings": [f.to_dict() for f in findings[:8]]},
            )
        except Exception:
            pass
        if state.qa_passed:
            state.transition(AgentStatus.PASSED, role=AgentRole.CRITIC)
        else:
            state.transition(AgentStatus.FAILED, role=AgentRole.CRITIC, detail="qa_failed")

        return state


def run_critic(state: AgentState) -> AgentState:
    return CriticAgent().run(state)


ReviewerAgent = CriticAgent
run_reviewer = run_critic

__all__ = ["CriticAgent", "ReviewerAgent", "run_critic", "run_reviewer"]


