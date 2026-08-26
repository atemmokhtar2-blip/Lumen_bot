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


SCENARIOS = [
    ("plat_telegram", lambda tmp: _scenario_platform_scaffold(tmp, "telegram"), "telegram"),
    ("plat_discord", lambda tmp: _scenario_platform_scaffold(tmp, "discord"), "discord"),
    ("plat_whatsapp", lambda tmp: _scenario_platform_scaffold(tmp, "whatsapp"), "whatsapp"),
    ("plat_web", lambda tmp: _scenario_platform_scaffold(tmp, "web"), "web"),
    ("det_repair_discord", _scenario_det_repair_discord, "discord"),
    ("code_intel_preflight", _scenario_code_intel_preflight, "telegram"),
    ("plan_findings", lambda tmp: _scenario_plan_and_findings(), "generic"),
    ("code_intel_hybrid", _scenario_hybrid_search, "telegram"),
    ("edit_pre_post", _scenario_edit_pre_post, "telegram"),
    ("cost_model", lambda tmp: _scenario_cost_model(), "generic"),
    ("hard_tg_support_tickets", _scenario_hard("tg_support_tickets"), "telegram"),
    ("hard_discord_moderation", _scenario_hard("discord_moderation"), "discord"),
    ("hard_wa_catalog_orders", _scenario_hard("wa_catalog_orders"), "whatsapp"),
    ("hard_web_status_dashboard", _scenario_hard("web_status_dashboard"), "web"),
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
