"""Smart table policy for agent/engine outputs — not fixed UI copy.

Decides when a native Telegram Rich table adds clarity (comparison,
stages, metrics, findings). Agents can also attach an explicit table
via state.extensions["presentation"]["tables"].
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence


@dataclass
class TableSpec:
    headers: list[str]
    rows: list[list[str]]
    caption: str = ""
    kind: str = "custom"  # comparison | stages | findings | metrics | custom
    reason: str = ""
    title: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "headers": list(self.headers),
            "rows": [list(r) for r in self.rows],
            "caption": self.caption,
            "kind": self.kind,
            "reason": self.reason,
            "title": self.title,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "TableSpec | None":
        if not isinstance(d, dict):
            return None
        headers = [str(h) for h in (d.get("headers") or [])]
        rows_raw = d.get("rows") or []
        rows: list[list[str]] = []
        for r in rows_raw:
            if isinstance(r, (list, tuple)):
                rows.append([str(c) for c in r])
        if len(headers) < 2 or len(rows) < 1:
            return None
        # normalize width
        w = len(headers)
        norm = []
        for r in rows[:30]:
            cells = list(r)[:w] + [""] * max(0, w - len(r))
            norm.append(cells[:w])
        return cls(
            headers=headers[:12],
            rows=norm,
            caption=str(d.get("caption") or "")[:120],
            kind=str(d.get("kind") or "custom")[:32],
            reason=str(d.get("reason") or "")[:200],
            title=str(d.get("title") or "")[:80],
        )


def _clip(s: object, n: int = 40) -> str:
    t = str(s if s is not None else "").replace("\n", " ").strip()
    return t if len(t) <= n else t[: n - 1] + "…"


def should_use_table(*, columns: int, rows: int, kind: str = "") -> bool:
    """Hard gates — avoid tables for trivial one-liners."""
    if columns < 2 or rows < 1:
        return False
    if rows == 1 and columns == 2 and kind not in {"comparison", "metrics"}:
        # single pair is ok for comparison/metrics only
        return kind in {"comparison", "metrics"}
    if rows > 25 or columns > 8:
        return False
    return True


def table_from_explicit(payload: dict[str, Any] | None) -> TableSpec | None:
    """Agent-provided table (highest priority)."""
    if not isinstance(payload, dict):
        return None
    # presentation.tables[0] or single table dict
    tables = payload.get("tables")
    if isinstance(tables, list) and tables:
        return TableSpec.from_dict(tables[0] if isinstance(tables[0], dict) else None)
    if payload.get("headers") and payload.get("rows"):
        return TableSpec.from_dict(payload)
    return None


def table_from_comparison(before: Sequence[Any], after: Sequence[Any], *, labels: Sequence[str] | None = None) -> TableSpec | None:
    """Before/after comparison — classic smart use-case."""
    b = list(before or [])
    a = list(after or [])
    n = max(len(b), len(a))
    if n < 1:
        return None
    rows: list[list[str]] = []
    for i in range(min(n, 20)):
        lab = labels[i] if labels and i < len(labels) else f"#{i + 1}"
        rows.append([_clip(lab, 24), _clip(b[i] if i < len(b) else "—", 36), _clip(a[i] if i < len(a) else "—", 36)])
    if not should_use_table(columns=3, rows=len(rows), kind="comparison"):
        return None
    return TableSpec(
        headers=["البند", "قبل", "بعد"],
        rows=rows,
        caption="مقارنة قبل / بعد",
        kind="comparison",
        reason="structured before/after pairs",
        title="مقارنة",
    )


def table_from_stages(stages: Sequence[Any]) -> TableSpec | None:
    rows: list[list[str]] = []
    for i, s in enumerate(list(stages or [])[:20]):
        if isinstance(s, dict):
            name = s.get("name") or s.get("stage") or s.get("id") or f"مرحلة {i+1}"
            ok = s.get("success", s.get("ok", s.get("status")))
            detail = s.get("detail") or s.get("message") or s.get("error") or ""
        else:
            name = getattr(s, "name", None) or getattr(s, "stage", None) or f"مرحلة {i+1}"
            ok = getattr(s, "success", None)
            if ok is None:
                ok = getattr(s, "ok", None)
            detail = getattr(s, "detail", "") or getattr(s, "message", "") or getattr(s, "error", "") or ""
        if ok is True or str(ok).lower() in {"1", "true", "ok", "passed", "success"}:
            status = "نجاح"
        elif ok is False or str(ok).lower() in {"0", "false", "fail", "failed", "error"}:
            status = "فشل"
        else:
            status = _clip(ok if ok is not None else "—", 16)
        rows.append([str(i + 1), _clip(name, 28), status, _clip(detail, 32)])
    if len(rows) < 2:
        return None
    if not should_use_table(columns=4, rows=len(rows), kind="stages"):
        return None
    return TableSpec(
        headers=["#", "المرحلة", "الحالة", "ملاحظة"],
        rows=rows,
        caption=f"{len(rows)} مرحلة",
        kind="stages",
        reason="multi-stage pipeline outcome",
        title="مراحل التنفيذ",
    )


def table_from_findings(findings: Sequence[Any]) -> TableSpec | None:
    rows: list[list[str]] = []
    for i, f in enumerate(list(findings or [])[:20]):
        if isinstance(f, dict):
            sev = f.get("severity") or f.get("level") or "—"
            title = f.get("title") or f.get("code") or f.get("id") or f"ملاحظة {i+1}"
            msg = f.get("message") or f.get("detail") or ""
        else:
            sev = getattr(f, "severity", None) or getattr(f, "level", None) or "—"
            title = getattr(f, "title", None) or getattr(f, "code", None) or f"ملاحظة {i+1}"
            msg = getattr(f, "message", "") or getattr(f, "detail", "") or ""
        rows.append([str(i + 1), _clip(sev, 12), _clip(title, 28), _clip(msg, 36)])
    if len(rows) < 2:
        return None
    if not should_use_table(columns=4, rows=len(rows), kind="findings"):
        return None
    return TableSpec(
        headers=["#", "الحدة", "العنوان", "التفاصيل"],
        rows=rows,
        caption=f"{len(rows)} ملاحظة",
        kind="findings",
        reason="structured findings list",
        title="نتائج الفحص",
    )


def table_from_metrics(metrics: dict[str, Any] | None) -> TableSpec | None:
    if not isinstance(metrics, dict) or len(metrics) < 2:
        return None
    rows = [[_clip(k, 28), _clip(v, 36)] for k, v in list(metrics.items())[:20]]
    if not should_use_table(columns=2, rows=len(rows), kind="metrics"):
        return None
    return TableSpec(
        headers=["المقياس", "القيمة"],
        rows=rows,
        caption="مؤشرات",
        kind="metrics",
        reason="key/value metrics map",
        title="مؤشرات التشغيل",
    )



def synthesize_agent_stages(state: Any) -> list[dict[str, Any]]:
    """Build stage rows from agent state when explicit stages are missing."""
    ext = getattr(state, "extensions", None) or {}
    if not isinstance(ext, dict):
        ext = {}
    stages: list[dict[str, Any]] = []
    # Prefer real stages on extensions
    raw = ext.get("stages") or getattr(state, "stages", None)
    if isinstance(raw, (list, tuple)) and raw:
        for i, s in enumerate(raw):
            if isinstance(s, dict):
                stages.append(s)
            else:
                stages.append({
                    "name": getattr(s, "name", None) or f"stage-{i+1}",
                    "success": getattr(s, "success", None),
                    "detail": getattr(s, "detail", "") or "",
                })
        return stages

    plan = ext.get("execution_plan") or ext.get("plan") or getattr(state, "strict_spec", None)
    stages.append({
        "name": "التخطيط",
        "success": bool(plan),
        "detail": "خطة جاهزة" if plan else "لا خطة",
    })
    build_ok = bool(getattr(state, "build_success", False))
    stages.append({
        "name": "البناء",
        "success": build_ok,
        "detail": (getattr(state, "generated_path", None) or "")[-40:] or ("تم" if build_ok else "فشل"),
    })
    qa_ok = bool(getattr(state, "qa_passed", False))
    qa = getattr(state, "qa_report", None) or {}
    err_n = 0
    if isinstance(qa, dict):
        err_n = len(qa.get("errors") or [])
    stages.append({
        "name": "فحص الجودة",
        "success": qa_ok,
        "detail": f"{err_n} أخطاء" if err_n else ("نجح" if qa_ok else "لم يكتمل"),
    })
    attempts = int(getattr(state, "attempts", 0) or 0)
    if attempts:
        stages.append({
            "name": "المحاولات",
            "success": True,
            "detail": str(attempts),
        })
    status = str(getattr(state, "status", "") or "")
    if status:
        stages.append({
            "name": "الحالة النهائية",
            "success": status.upper() in {"PASSED", "DELIVERED", "COMPLETED", "DONE", "SUCCESS", "AWAITING_CONFIRMATION"},
            "detail": status[:32],
        })
    return stages


def ensure_agent_presentation(state: Any) -> TableSpec | None:
    """Force a useful table from agent state when possible; attach on state."""
    if state is None:
        return None
    ext = getattr(state, "extensions", None)
    if not isinstance(ext, dict):
        try:
            state.extensions = {}
            ext = state.extensions
        except Exception:
            return None
    # If agent already set presentation tables, keep them
    existing = table_from_explicit(ext.get("presentation") if isinstance(ext.get("presentation"), dict) else None)
    if existing is not None:
        return existing

    # Inject synthesized stages for policy
    if not ext.get("stages"):
        ext["stages"] = synthesize_agent_stages(state)

    spec = decide_table_for_state(state)
    if spec is None:
        # Last resort: stages table from synthesis (even 2 rows)
        rows = []
        for i, s in enumerate(ext.get("stages") or []):
            if not isinstance(s, dict):
                continue
            ok = s.get("success")
            status = "نجاح" if ok else ("فشل" if ok is False else "—")
            rows.append([str(i + 1), str(s.get("name") or f"#{i+1}")[:28], status, str(s.get("detail") or "")[:32]])
        if len(rows) >= 2:
            spec = TableSpec(
                headers=["#", "المرحلة", "الحالة", "ملاحظة"],
                rows=rows[:20],
                caption=f"{len(rows)} مرحلة",
                kind="stages",
                reason="synthesized agent stages",
                title="مسار المحرك",
            )
    if spec is not None:
        attach_presentation_table(state, spec)
    return spec


def decide_table_for_state(state: Any) -> TableSpec | None:
    """Engine/agent smart choice — explicit presentation wins, then heuristics."""
    ext = getattr(state, "extensions", None) or {}
    if not isinstance(ext, dict):
        ext = {}

    # 1) Agent explicitly requested a table
    explicit = table_from_explicit(ext.get("presentation") if isinstance(ext.get("presentation"), dict) else None)
    if explicit is not None:
        return explicit
    # also accept top-level extensions["table"]
    explicit = table_from_explicit(ext.get("table") if isinstance(ext.get("table"), dict) else None)
    if explicit is not None:
        return explicit

    # 2) Before/after comparison attached by agents
    before = ext.get("compare_before") or ext.get("before")
    after = ext.get("compare_after") or ext.get("after")
    labels = ext.get("compare_labels") or ext.get("labels")
    if isinstance(before, (list, tuple)) and isinstance(after, (list, tuple)):
        spec = table_from_comparison(before, after, labels=labels if isinstance(labels, (list, tuple)) else None)
        if spec is not None:
            return spec

    # 3) Stages (pipeline)
    stages = ext.get("stages") or getattr(state, "stages", None)
    if stages:
        spec = table_from_stages(stages)
        if spec is not None:
            return spec

    # 4) Findings / QA errors as structured rows
    findings = ext.get("findings") or []
    if findings:
        spec = table_from_findings(findings)
        if spec is not None:
            return spec
    qa = getattr(state, "qa_report", None) or ext.get("qa_report") or {}
    if isinstance(qa, dict):
        errs = qa.get("errors") or []
        if isinstance(errs, list) and len(errs) >= 2:
            fake = [{"severity": "error", "title": "QA", "message": e} for e in errs[:15]]
            spec = table_from_findings(fake)
            if spec is not None:
                return spec

    # 5) Metrics map
    metrics = ext.get("metrics") or ext.get("usage")
    if isinstance(metrics, dict):
        spec = table_from_metrics(metrics)
        if spec is not None:
            return spec

    return None


def attach_presentation_table(state: Any, spec: TableSpec | None) -> Any:
    """Persist chosen table on state for Telegram delivery layer."""
    if state is None or spec is None:
        return state
    ext = getattr(state, "extensions", None)
    if not isinstance(ext, dict):
        try:
            state.extensions = {}
            ext = state.extensions
        except Exception:
            return state
    pres = ext.get("presentation")
    if not isinstance(pres, dict):
        pres = {}
    pres["tables"] = [spec.to_dict()]
    pres["policy_reason"] = spec.reason
    pres["policy_kind"] = spec.kind
    ext["presentation"] = pres
    return state


def decide_and_attach(state: Any) -> TableSpec | None:
    # Prefer full ensure (synthesis + explicit + heuristics)
    try:
        return ensure_agent_presentation(state)
    except Exception:
        spec = decide_table_for_state(state)
        if spec is not None:
            attach_presentation_table(state, spec)
        return spec


__all__ = [
    "TableSpec",
    "should_use_table",
    "table_from_explicit",
    "table_from_comparison",
    "table_from_stages",
    "table_from_findings",
    "table_from_metrics",
    "decide_table_for_state",
    "attach_presentation_table",
    "decide_and_attach",
    "synthesize_agent_stages",
    "ensure_agent_presentation",
]
