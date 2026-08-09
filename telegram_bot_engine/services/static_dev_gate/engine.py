"""Rule engine — run registered rules on a shared AnalysisContext."""

from __future__ import annotations

from .context import build_context
from .models import AnalysisContext, StaticFinding, StaticReport
from .rules.registry import all_rules


def run_rules(
    ctx: AnalysisContext,
    *,
    rule_ids: list[str] | None = None,
    tags: list[str] | None = None,
) -> StaticReport:
    findings: list[StaticFinding] = []
    ran: list[str] = []
    for rule in all_rules(enabled_only=True):
        if rule_ids and rule.meta.id not in rule_ids:
            continue
        if tags and not any(t in rule.meta.tags for t in tags):
            continue
        try:
            findings.extend(rule.check(ctx))
            ran.append(rule.meta.id)
        except Exception as e:
            findings.append(StaticFinding(
                severity="warning",
                code="rule_crash",
                rule_id=rule.meta.id,
                file="engine",
                message_ar=f"القاعدة تعطلت: {type(e).__name__}",
            ))
            ran.append(rule.meta.id)
    return StaticReport.from_findings(
        findings,
        files_checked=len(ctx.modules),
        rules_run=ran,
        meta=dict(ctx.meta),
    )


def analyze(
    root: str,
    focus_files: list[str] | None = None,
    expected_commands: list[str] | None = None,
    tags: list[str] | None = None,
) -> StaticReport:
    ctx = build_context(
        root,
        focus_files=focus_files,
        expected_commands=expected_commands,
    )
    return run_rules(ctx, tags=tags)
