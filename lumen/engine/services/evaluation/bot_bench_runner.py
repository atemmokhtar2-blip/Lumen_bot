"""Fixed bot-bench scenarios across platforms — no mock LLM production path.

Scenarios exercise real modules:
  platform_generators, deterministic_repair, code_intelligence preflight/postflight,
  plan_contract, findings.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .eval_store import append_eval_record, summarize_evals
from .run_record import EvalRunRecord, finalize_record


def _scenario_platform_scaffold(tmp: Path, platform: str) -> dict[str, Any]:
    from lumen.engine.services.platform_generators import apply_platform_scaffold

    t0 = time.time()
    out = apply_platform_scaffold(tmp, platform=platform)
    ok = bool(out.get("ok")) and (tmp / "main.py").is_file()
    errors = [] if ok else ["missing_main_or_scaffold_failed"]
    return {
        "success": ok,
        "attempts": 1,
        "latency_s": time.time() - t0,
        "cost_usd": 0.0,
        "errors": errors,
        "metrics": {"written": out.get("written"), "platform": out.get("platform")},
    }


def _scenario_det_repair_discord(tmp: Path) -> dict[str, Any]:
    from lumen.engine.services.multi_agent.deterministic_repair import apply_deterministic_repairs

    t0 = time.time()
    rep = apply_deterministic_repairs(tmp, extensions={"user_text": "discord moderation bot"})
    main = (tmp / "main.py").read_text(encoding="utf-8") if (tmp / "main.py").is_file() else ""
    ok = "discord" in main.lower()
    return {
        "success": ok,
        "attempts": 1,
        "latency_s": time.time() - t0,
        "cost_usd": 0.0,
        "errors": [] if ok else ["discord_scaffold_not_applied"],
        "metrics": {"actions": rep.get("actions"), "platform": rep.get("platform")},
    }


def _scenario_code_intel_preflight(tmp: Path) -> dict[str, Any]:
    from lumen.engine.services.platform_generators import apply_platform_scaffold
    from lumen.engine.services.code_intelligence.preflight import analyze_edit_preflight

    apply_platform_scaffold(tmp, platform="telegram")
    t0 = time.time()
    pf = analyze_edit_preflight(tmp, "main.py", old_string="def main", new_string="def main")
    ok = bool(pf.get("ok")) and "risk" in pf
    return {
        "success": ok,
        "attempts": 1,
        "latency_s": time.time() - t0,
        "cost_usd": 0.0,
        "errors": [] if ok else ["preflight_failed"],
        "metrics": {"risk": pf.get("risk"), "engine": pf.get("engine")},
    }


def _scenario_plan_and_findings() -> dict[str, Any]:
    from lumen.engine.services.multi_agent.plan_contract import ExecutionPlan
    from lumen.engine.services.multi_agent.findings import CritiqueFinding, findings_to_errors

    t0 = time.time()
    plan = ExecutionPlan.from_dict({"goal": "whatsapp support bot", "tasks": [{"id": "t1", "title": "webhook"}]})
    fs = [CritiqueFinding(code="missing_deliverable", severity="error", message="no main", path="main.py")]
    errs = findings_to_errors(fs)
    ok = bool(plan.goal) and bool(errs)
    return {
        "success": ok,
        "attempts": 1,
        "latency_s": time.time() - t0,
        "cost_usd": 0.0,
        "errors": [] if ok else ["plan_or_findings_failed"],
        "metrics": {"goal": plan.goal, "errors": errs[:3]},
    }



def _scenario_hybrid_search(tmp: Path) -> dict[str, Any]:
    from lumen.engine.services.platform_generators import apply_platform_scaffold
    from lumen.engine.services.code_intelligence import hybrid_search

    apply_platform_scaffold(tmp, platform="telegram")
    t0 = time.time()
    res = hybrid_search(tmp, "main start handler bot", top_k=5)
    ok = bool(res.get("ok")) and bool(res.get("hits") is not None)
    return {
        "success": ok,
        "attempts": 1,
        "latency_s": time.time() - t0,
        "cost_usd": 0.0,
        "errors": [] if ok else ["hybrid_failed"],
        "metrics": {"engine": res.get("engine"), "hits": len(res.get("hits") or [])},
    }


def _scenario_edit_pre_post(tmp: Path) -> dict[str, Any]:
    from lumen.engine.services.platform_generators import apply_platform_scaffold
    from lumen.engine.services.cline_runtime.agent_fs import edit_file

    apply_platform_scaffold(tmp, platform="telegram")
    main = (tmp / "main.py").read_text(encoding="utf-8")
    # safe no-op-ish replace
    old = "def main"
    if old not in main:
        old = "main"
    t0 = time.time()
    res = edit_file(str(tmp), "main.py", old, old)
    ok = bool(res.get("ok")) and "preflight" in res
    return {
        "success": ok,
        "attempts": 1,
        "latency_s": time.time() - t0,
        "cost_usd": 0.0,
        "errors": [] if ok else ["edit_preflight_missing"],
        "metrics": {"preflight": res.get("preflight"), "postflight": res.get("postflight")},
    }


def _scenario_cost_model() -> dict[str, Any]:
    from .cost_model import estimate_cost_usd

    t0 = time.time()
    c = estimate_cost_usd({"prompt_tokens": 1000, "completion_tokens": 500})
    ok = c > 0
    return {
        "success": ok,
        "attempts": 1,
        "latency_s": time.time() - t0,
        "cost_usd": c,
        "errors": [] if ok else ["cost_zero"],
        "metrics": {"cost_usd": c},
    }



def _scenario_hard(item_id: str):
    from .hard_generation import HARD_SPECS, run_hard_generation_scenario

    item = next(x for x in HARD_SPECS if x["id"] == item_id)

    def _fn(tmp: Path) -> dict[str, Any]:
        return run_hard_generation_scenario(
            tmp,
            platform=item["platform"],
            spec=item["spec"],
            scenario_id=item["id"],
        )

    return _fn



def _scenario_code_intel_gate(tmp: Path) -> dict[str, Any]:
    """Real hybrid + repo_context gate (not scaffold-only)."""
    t0 = time.time()
    (tmp / "main.py").write_text(
        "def main():\n    from handlers import on_start\n    return on_start()\n",
        encoding="utf-8",
    )
    (tmp / "handlers.py").write_text(
        "def on_start():\n    return \"ok\"\n",
        encoding="utf-8",
    )
    from lumen.engine.services.evaluation.code_intel_gate import run_code_intel_gate
    # gate uses its own temp dir; also verify hybrid on tmp
    from lumen.engine.services.code_intelligence.hybrid_retrieval import hybrid_search
    from lumen.engine.services.code_intelligence.repo_context import pack_repo_context_for_goal
    hs = hybrid_search(tmp, "on_start handler", top_k=5)
    pack = pack_repo_context_for_goal(tmp, "on_start", extra_paths=["handlers.py"])
    gate = run_code_intel_gate()
    ok = bool(hs.get("hits")) and bool(pack.get("files")) and bool(gate.get("ok"))
    return {
        "success": ok,
        "attempts": 1,
        "latency_s": time.time() - t0,
        "cost_usd": 0.0,
        "errors": [] if ok else ["code_intel_gate_or_hybrid_failed"],
        "metrics": {
            "embed_provider": hs.get("embed_provider"),
            "hits": len(hs.get("hits") or []),
            "pack_files": list((pack.get("files") or {}).keys()),
            "gate": gate,
        },
    }


SCENARIOS = [
    ("plat_telegram", lambda tmp: _scenario_platform_scaffold(tmp, "telegram"), "telegram"),
    ("plat_discord", lambda tmp: _scenario_platform_scaffold(tmp, "discord"), "discord"),
    ("plat_whatsapp", lambda tmp: _scenario_platform_scaffold(tmp, "whatsapp"), "whatsapp"),
    ("plat_web", lambda tmp: _scenario_platform_scaffold(tmp, "web"), "web"),
    ("det_repair_discord", _scenario_det_repair_discord, "discord"),
    ("code_intel_preflight", _scenario_code_intel_preflight, "telegram"),
    ("plan_findings", lambda tmp: _scenario_plan_and_findings(), "generic"),
    ("code_intel_hybrid", _scenario_hybrid_search, "telegram"),
    ("code_intel_gate", _scenario_code_intel_gate, "telegram"),
    ("edit_pre_post", _scenario_edit_pre_post, "telegram"),
    ("cost_model", lambda tmp: _scenario_cost_model(), "generic"),
    ("hard_tg_support_tickets", _scenario_hard("tg_support_tickets"), "telegram"),
    ("hard_discord_moderation", _scenario_hard("discord_moderation"), "discord"),
    ("hard_wa_catalog_orders", _scenario_hard("wa_catalog_orders"), "whatsapp"),
    ("hard_web_status_dashboard", _scenario_hard("web_status_dashboard"), "web"),
]




# registered agent-layer scenarios
AGENT_LAYER_SCENARIOS = [
    ("agent_layer_contracts", _scenario_agent_layer_contracts),
    ("planner_to_acceptance_tree", _scenario_planner_to_acceptance_tree),
]


def run_bot_bench_suite(*, work_root: Path | None = None, persist: bool = True) -> dict[str, Any]:
    import tempfile

    records: list[EvalRunRecord] = []
    base = work_root or Path(tempfile.mkdtemp(prefix="lumen_bot_bench_"))
    base.mkdir(parents=True, exist_ok=True)

    for scenario_id, fn, platform in SCENARIOS:
        tmp = base / scenario_id
        tmp.mkdir(parents=True, exist_ok=True)
        rec = EvalRunRecord(scenario_id=scenario_id, platform=platform)
        try:
            result = fn(tmp)
            rec.attempts = int(result.get("attempts") or 1)
            rec.cost_usd = float(result.get("cost_usd") or 0.0)
            rec.metrics = dict(result.get("metrics") or {})
            # trust scenario latency if provided, else finalize computes
            if result.get("latency_s") is not None:
                rec.latency_s = float(result["latency_s"])
            finalize_record(rec, success=bool(result.get("success")), errors=list(result.get("errors") or []))
            if result.get("latency_s") is not None:
                rec.latency_s = float(result["latency_s"])
        except Exception as exc:
            finalize_record(rec, success=False, errors=[f"{type(exc).__name__}:{exc}"])
        records.append(rec)
        if persist:
            append_eval_record(rec)

    summary = summarize_evals([r.to_dict() for r in records])
    return {
        "ok": summary["success_rate"] >= 0.85,
        "summary": summary,
        "records": [r.to_dict() for r in records],
        "engine": "bot_bench_runner",
    }


__all__ = ["run_bot_bench_suite", "SCENARIOS"]


def _scenario_agent_layer_contracts() -> dict[str, Any]:
    """E2E offline: all four agent layers + market scenarios (no LLM)."""
    import time
    from lumen.engine.services.multi_agent.layer_scenarios import run_all_layer_scenarios
    t0 = time.time()
    out = run_all_layer_scenarios()
    return {
        "success": bool(out.get("ok")),
        "attempts": 1,
        "latency_s": time.time() - t0,
        "cost_usd": 0.0,
        "errors": [] if out.get("ok") else [r["name"] for r in out.get("results") or [] if not r.get("ok")],
        "metrics": {"passed": out.get("passed"), "total": out.get("total")},
    }


def _scenario_planner_to_acceptance_tree() -> dict[str, Any]:
    """Plan → TaskTree → parallel wave → acceptance on empty fails."""
    import time
    from pathlib import Path as P
    import tempfile
    from lumen.engine.services.multi_agent.dynamic_planner import assemble_plan
    from lumen.engine.services.multi_agent.task_tree import TaskTree, TaskStatus
    from lumen.engine.services.multi_agent.acceptance_check import evaluate_task
    t0 = time.time()
    plan = assemble_plan(goal="telegram bot", preferred_keys=["admin", "payments"])
    tree = TaskTree.from_execution_plan(plan, goal=plan.goal)
    tree.mark("scaffold", TaskStatus.DONE)
    tree.refresh_readiness()
    wave = tree.parallel_wave()
    tmp = P(tempfile.mkdtemp())
    acc = evaluate_task(tmp, files=["main.py"], acceptance=["main.py exists"], strict=True)
    ok = len(wave) >= 2 and acc.get("ok") is False
    return {
        "success": ok,
        "attempts": 1,
        "latency_s": time.time() - t0,
        "cost_usd": 0.0,
        "errors": [] if ok else ["wave_or_acceptance"],
        "metrics": {"wave": [n.id for n in wave]},
    }
