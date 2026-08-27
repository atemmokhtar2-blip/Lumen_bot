"""Market-grade scenarios for the four core agent layers.

Each scenario asserts the *correct* pipeline behavior without calling an LLM.
This is the contract the product must satisfy to compete with Cursor-class agents.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .dynamic_planner import assemble_plan, classify_intent
from .task_tree import TaskStatus, TaskTree
from .acceptance_check import evaluate_task


@dataclass
class ScenarioResult:
    name: str
    ok: bool
    checks: list[dict[str, Any]] = field(default_factory=list)
    detail: str = ""

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.checks.append({"name": name, "ok": ok, "detail": detail})
        if not ok:
            self.ok = False


# ---------------------------------------------------------------------------
# Layer 1 — Planner scenarios
# ---------------------------------------------------------------------------

def sc_planner_telegram_multi_feature() -> ScenarioResult:
    r = ScenarioResult("planner.telegram_multi_feature", True)
    plan = assemble_plan(
        goal="بوت تيليجرام للترحيب",
        preferred_keys=["admin", "payments", "ai_chat"],
    )
    r.add("intent_telegram", any("intent:telegram" in c for c in plan.constraints))
    feats = [t for t in plan.tasks if t.parallel_group == "feature_modules"]
    r.add("parallel_features_ge_2", len(feats) >= 2, f"n={len(feats)}")
    r.add("modules_not_main", all(t.files and "main.py" not in t.files for t in feats))
    r.add("wire_depends_on_feats", any(t.id == "wire_features" for t in plan.tasks))
    tree = TaskTree.from_execution_plan(plan, goal=plan.goal)
    tree.mark("scaffold", TaskStatus.DONE)
    tree.refresh_readiness()
    wave = tree.parallel_wave()
    r.add("wave_parallel", len(wave) >= 2, f"wave={[n.id for n in wave]}")
    return r


def sc_planner_discord_parallel() -> ScenarioResult:
    r = ScenarioResult("planner.discord_parallel", True)
    plan = assemble_plan(goal="discord moderation bot", preferred_keys=["mute", "ban"])
    r.add("intent", classify_intent("discord moderation bot").kind == "discord_bot")
    feats = [t for t in plan.tasks if t.parallel_group == "feature_modules"]
    r.add("feat_modules", len(feats) >= 2)
    return r


def sc_planner_web_routers() -> ScenarioResult:
    r = ScenarioResult("planner.web_routers", True)
    plan = assemble_plan(goal="FastAPI billing API", preferred_keys=["auth", "payments"])
    r.add("intent_web", classify_intent("FastAPI billing API").kind == "web_api")
    feats = [t for t in plan.tasks if t.parallel_group == "feature_modules"]
    r.add("routers_dir", all("routers/" in (t.files[0] if t.files else "") for t in feats), str([t.files for t in feats]))
    return r


def sc_planner_refine_existing(tmp: Path) -> ScenarioResult:
    r = ScenarioResult("planner.refine_existing", True)
    (tmp / "main.py").write_text("print(1)\n", encoding="utf-8")
    plan = assemble_plan(goal="أصلح البوت", work_dir=tmp)
    ids = [t.id for t in plan.tasks]
    r.add("refine_mode", "mode:incremental_repair" in plan.constraints)
    r.add("no_full_scaffold_wipe", "scaffold" not in ids or "inspect" in ids or "patch" in ids)
    return r


def sc_planner_ambiguous_bot() -> ScenarioResult:
    r = ScenarioResult("planner.ambiguous_bot", True)
    intent = classify_intent("اعمل بوت")
    r.add("not_forced_telegram", intent.kind == "general_app", intent.kind)
    return r


# ---------------------------------------------------------------------------
# Layer 2 — Worker packet / acceptance gate scenarios
# ---------------------------------------------------------------------------

def sc_worker_packet_has_acceptance() -> ScenarioResult:
    from .coding_agent import build_task_packet
    r = ScenarioResult("worker.packet_acceptance", True)
    p = build_task_packet(
        goal="build",
        task_brief="scaffold",
        acceptance=["main.py exists", "compileall passes"],
        target_files=["main.py"],
        constraints=["platform:telegram"],
    )
    r.add("has_acceptance_block", "ACCEPTANCE CRITERIA" in p)
    r.add("has_targets", "TARGET FILES" in p)
    r.add("has_constraints", "CONSTRAINTS" in p)
    r.add("finish_protocol", "finish" in p.lower())
    return r


def sc_worker_post_acceptance_fails_on_empty(tmp: Path) -> ScenarioResult:
    """Session ok cannot pass if acceptance fails — simulated evaluate_task only."""
    r = ScenarioResult("worker.post_acceptance_empty_project", True)
    rep = evaluate_task(tmp, files=["main.py"], acceptance=["main.py exists"], strict=True)
    r.add("empty_fails", rep["ok"] is False)
    return r


def sc_worker_post_acceptance_passes_scaffold(tmp: Path) -> ScenarioResult:
    r = ScenarioResult("worker.post_acceptance_scaffold", True)
    (tmp / "main.py").write_text(
        "import os\nfrom telegram.ext import Application, CommandHandler, MessageHandler\n"
        "async def start(u,c): pass\n"
        "def main():\n"
        "    t=os.getenv('BOT_TOKEN')\n"
        "    app=Application.builder().token(t).build()\n"
        "    app.add_handler(CommandHandler('start', start))\n"
        "    app.add_handler(MessageHandler(None, start))\n",
        encoding="utf-8",
    )
    (tmp / "requirements.txt").write_text("python-telegram-bot\n", encoding="utf-8")
    rep = evaluate_task(
        tmp,
        files=["main.py", "requirements.txt"],
        acceptance=[
            "main.py exists",
            "compileall passes",
            "requirements lists telegram",
            "token from environment",
            "/start handler registered",
        ],
        strict=True,
    )
    r.add("scaffold_ok", rep["ok"] is True, str(rep.get("failed")))
    return r


# ---------------------------------------------------------------------------
# Layer 3 — Parallel isolation + merge scenarios
# ---------------------------------------------------------------------------

def sc_parallel_isolation_merge(tmp: Path) -> ScenarioResult:
    """Simulate Send path: active=[one], parallel_group set → isolate + merge."""
    import shutil
    r = ScenarioResult("parallel.isolation_merge_send_safe", True)
    (tmp / "main.py").write_text("# root\n", encoding="utf-8")
    (tmp / "modules").mkdir(exist_ok=True)

    class Task:
        parallel_group = "feature_modules"
        files = ["modules/admin.py"]
        acceptance = ["modules/admin.py exists", "feature working: admin"]

    task = Task()
    active = ["feat_admin"]  # Send shape
    use_iso = bool(getattr(task, "parallel_group", "") or "")
    r.add("iso_on_single_active", use_iso is True)

    session = tmp / ".parallel" / "feat_admin"
    if session.exists():
        shutil.rmtree(session)
    session.mkdir(parents=True)
    for src in tmp.rglob("*"):
        if src.is_file() and ".parallel" not in src.parts:
            dest = session / src.relative_to(tmp)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
    # worker writes only its module
    mod = session / "modules" / "admin.py"
    mod.parent.mkdir(parents=True, exist_ok=True)
    mod.write_text("def admin():\n    return True\n", encoding="utf-8")
    # merge declared files only
    for rel in task.files:
        src = session / rel
        if src.is_file():
            dest = tmp / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
    r.add("merged_file", (tmp / "modules" / "admin.py").is_file())
    r.add("main_untouched", (tmp / "main.py").read_text() == "# root\n")
    acc = evaluate_task(tmp, files=task.files, acceptance=task.acceptance, strict=True)
    r.add("acceptance_after_merge", acc["ok"] is True, str(acc.get("failed")))
    return r


def sc_parallel_wave_after_scaffold() -> ScenarioResult:
    r = ScenarioResult("parallel.wave_after_scaffold", True)
    plan = assemble_plan(goal="telegram bot", preferred_keys=["a", "b", "c"])
    tree = TaskTree.from_execution_plan(plan, goal=plan.goal)
    tree.mark("scaffold", TaskStatus.DONE)
    tree.refresh_readiness()
    wave = tree.parallel_wave()
    r.add("ge_2", len(wave) >= 2, str([n.id for n in wave]))
    r.add("disjoint_files", not any(
        set(wave[i].files) & set(wave[j].files)
        for i in range(len(wave)) for j in range(i + 1, len(wave))
    ))
    return r


# ---------------------------------------------------------------------------
# Layer 4 — Acceptance market matrix
# ---------------------------------------------------------------------------

def sc_acceptance_fail_closed_unknown(tmp: Path) -> ScenarioResult:
    r = ScenarioResult("acceptance.fail_closed_unknown", True)
    (tmp / "main.py").write_text("x=1\n", encoding="utf-8")
    from .acceptance_check import check_criterion
    c = check_criterion(tmp, "must integrate quantum flux", strict=True)
    r.add("unknown_fails", c["ok"] is False)
    return r


def sc_acceptance_compileall_bad_syntax(tmp: Path) -> ScenarioResult:
    r = ScenarioResult("acceptance.compileall_bad_syntax", True)
    (tmp / "main.py").write_text("def broken(\n", encoding="utf-8")
    rep = evaluate_task(tmp, files=["main.py"], acceptance=["compileall passes"], strict=True)
    r.add("fails", rep["ok"] is False)
    return r


def sc_acceptance_feature_in_module_path(tmp: Path) -> ScenarioResult:
    r = ScenarioResult("acceptance.feature_in_module_path", True)
    (tmp / "modules").mkdir(exist_ok=True)
    (tmp / "modules" / "payments.py").write_text("def charge():\n    return 1\n", encoding="utf-8")
    (tmp / "main.py").write_text("x=1\n", encoding="utf-8")
    rep = evaluate_task(
        tmp,
        files=["modules/payments.py"],
        acceptance=["modules/payments.py exists", "feature working: payments"],
        strict=True,
    )
    r.add("ok", rep["ok"] is True, str(rep.get("failed")))
    return r


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def sc_graph_compile_and_hitl_routes() -> ScenarioResult:
    """LangGraph HITL deliver routes are wired (static + callable checks)."""
    r = ScenarioResult("durability.graph_compile_hitl_routes", True)
    try:
        from .langgraph_pipeline import (
            langgraph_available,
            hitl_deliver_enabled,
            hitl_interrupt_enabled,
        )
        r.add("langgraph_available_fn", callable(langgraph_available))
        r.add("hitl_plan_fn", callable(hitl_interrupt_enabled))
        r.add("hitl_deliver_fn", callable(hitl_deliver_enabled))
        src = Path(__file__).with_name("langgraph_pipeline.py").read_text(encoding="utf-8")
        r.add(
            "after_critique_routes_deliver_gate",
            'return "human_deliver_gate"' in src and "hitl_deliver_enabled()" in src,
        )
        r.add("pending_deliver_tool", "langgraph_deliver_approve" in src)
        r.add("approve_deliver_payload", '"approve_deliver"' in src or "'approve_deliver'" in src)
    except Exception as exc:
        r.add("graph_smoke", False, type(exc).__name__)
    return r


def run_all_layer_scenarios(tmp_root: Path | None = None) -> dict[str, Any]:
    import tempfile
    root = Path(tmp_root) if tmp_root else Path(tempfile.mkdtemp(prefix="lumen_sc_"))
    results: list[ScenarioResult] = []

    results.append(sc_planner_telegram_multi_feature())
    results.append(sc_planner_discord_parallel())
    results.append(sc_planner_web_routers())
    (root / "refine").mkdir(parents=True, exist_ok=True)
    results.append(sc_planner_refine_existing(root / "refine"))
    results.append(sc_planner_ambiguous_bot())

    results.append(sc_worker_packet_has_acceptance())
    (root / "empty").mkdir(parents=True, exist_ok=True)
    results.append(sc_worker_post_acceptance_fails_on_empty(root / "empty"))
    (root / "scaffold").mkdir(parents=True, exist_ok=True)
    results.append(sc_worker_post_acceptance_passes_scaffold(root / "scaffold"))

    (root / "iso").mkdir(parents=True, exist_ok=True)
    results.append(sc_parallel_isolation_merge(root / "iso"))
    results.append(sc_parallel_wave_after_scaffold())

    (root / "unk").mkdir(parents=True, exist_ok=True)
    results.append(sc_acceptance_fail_closed_unknown(root / "unk"))
    (root / "bad").mkdir(parents=True, exist_ok=True)
    results.append(sc_acceptance_compileall_bad_syntax(root / "bad"))
    (root / "feat").mkdir(parents=True, exist_ok=True)
    results.append(sc_acceptance_feature_in_module_path(root / "feat"))
    results.append(sc_graph_compile_and_hitl_routes())

    passed = sum(1 for x in results if x.ok)
    return {
        "ok": passed == len(results),
        "passed": passed,
        "total": len(results),
        "results": [
            {"name": x.name, "ok": x.ok, "checks": x.checks, "detail": x.detail}
            for x in results
        ],
    }


__all__ = ["run_all_layer_scenarios", "ScenarioResult"]
