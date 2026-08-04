"""
WorkflowRunner — Specification 064 (MAXIMUM CRITICAL)

Build and execute workflows: sequential/parallel/conditional stages,
branches, checkpoints, resume and rollback.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Tuple

from .data_readers import GenericData
from .report_data import (
    WorkflowStage, Checkpoint, WorkflowEvent, RollbackRecord, WorkflowStats,
    STAGE_PENDING, STAGE_RUNNING, STAGE_COMPLETED, STAGE_FAILED,
    STAGE_SKIPPED, STAGE_ROLLED_BACK,
    MODE_SEQUENTIAL, MODE_PARALLEL, MODE_CONDITIONAL,
    BRANCH_IF, BRANCH_ELSE, BRANCH_SWITCH, BRANCH_DEFAULT,
)

_log = logging.getLogger("engine.workflow_execution.workflow_engine")


class WorkflowRunner:
    """Build stages from plan and execute with checkpoints."""

    def execute(
        self,
        scheduler_data: GenericData,
        queue_data: GenericData,
        orch_data: GenericData,
        ctx_data: GenericData,
        service_data: GenericData,
        request_data: GenericData,
    ) -> Tuple[
        str,  # workflow_id
        List[WorkflowStage],
        List[Checkpoint],
        List[WorkflowEvent],
        List[RollbackRecord],
        WorkflowStats,
        int,   # sequential_gate_violations
        bool,  # resumed
        bool,  # rolled_back
        bool,  # self_ok
    ]:
        workflow_id = str(uuid.uuid4())[:12]
        stages = self._build(request_data, orch_data, scheduler_data)
        events: List[WorkflowEvent] = [
            self._event("workflow", "build", "", "", True, f"built {len(stages)} stages"),
        ]
        checkpoints: List[Checkpoint] = []
        rollbacks: List[RollbackRecord] = []
        gate_violations = 0
        resumed = False
        rolled_back = False

        raw = request_data.raw or {}

        # Resume from checkpoint if requested
        if raw.get("resume_from"):
            resumed = True
            events.append(self._event(
                str(raw["resume_from"]), "resume", STAGE_PENDING, STAGE_PENDING, True,
                f"resume requested from {raw['resume_from']}",
            ))

        # Validate all stages first
        for s in stages:
            s.validated = self._validate_stage(s)
            events.append(self._event(
                s.stage_id, "validate", STAGE_PENDING, STAGE_PENDING,
                s.validated, "validated" if s.validated else "validation failed",
            ))

        completed: Set[str] = set()
        failed_stage: Optional[str] = None

        # Group parallel stages by order band
        by_order: Dict[int, List[WorkflowStage]] = {}
        for s in stages:
            by_order.setdefault(s.order, []).append(s)

        for order in sorted(by_order.keys()):
            group = by_order[order]
            parallel = all(s.mode == MODE_PARALLEL for s in group) and len(group) > 1

            for s in group:
                if not s.validated:
                    s.state = STAGE_SKIPPED
                    events.append(self._event(
                        s.stage_id, "skip", STAGE_PENDING, STAGE_SKIPPED, True,
                        "skipped — validation failed",
                    ))
                    continue

                # Conditional branch evaluation
                if s.mode == MODE_CONDITIONAL or s.branch:
                    if not self._eval_condition(s, raw):
                        s.state = STAGE_SKIPPED
                        events.append(self._event(
                            s.stage_id, "skip", STAGE_PENDING, STAGE_SKIPPED, True,
                            f"condition not met: {s.condition or s.branch}",
                        ))
                        continue

                # Sequential gate: deps must be completed
                if s.mode == MODE_SEQUENTIAL or not parallel:
                    missing = [d for d in s.depends_on if d not in completed]
                    if missing:
                        gate_violations += 1
                        events.append(self._event(
                            s.stage_id, "start", s.state, s.state, False,
                            f"sequential gate blocked — missing: {missing}",
                        ))
                        if not raw.get("force_skip_gate"):
                            s.state = STAGE_FAILED
                            failed_stage = s.stage_id
                            events.append(self._event(
                                s.stage_id, "fail", STAGE_PENDING, STAGE_FAILED, False,
                                "blocked by sequential gate",
                            ))
                            break

                # Resume: skip already-done stages
                if resumed and s.stage_id == str(raw.get("resume_from")):
                    # start from here
                    pass
                elif resumed and s.order < self._order_of(stages, str(raw.get("resume_from"))):
                    s.state = STAGE_COMPLETED
                    completed.add(s.stage_id)
                    continue

                # Execute
                prev = s.state
                s.state = STAGE_RUNNING
                events.append(self._event(s.stage_id, "start", prev, STAGE_RUNNING, True, "stage started"))

                fail_ids = set(raw.get("fail_stages") or [])
                if s.stage_id in fail_ids or (raw.get("force_stage_failure") and s.order >= 3):
                    s.state = STAGE_FAILED
                    s.duration_ms = 50.0
                    failed_stage = s.stage_id
                    events.append(self._event(
                        s.stage_id, "fail", STAGE_RUNNING, STAGE_FAILED, False, "stage failed",
                    ))
                    break

                s.state = STAGE_COMPLETED
                s.duration_ms = 20.0 + s.order * 5
                completed.add(s.stage_id)
                events.append(self._event(
                    s.stage_id, "complete", STAGE_RUNNING, STAGE_COMPLETED, True, "stage completed",
                ))

                # Checkpoint after success
                cp = Checkpoint(
                    checkpoint_id=str(uuid.uuid4())[:10],
                    stage_id=s.stage_id,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    snapshot={"stage_id": s.stage_id, "state": s.state, "order": s.order},
                    valid=True,
                )
                checkpoints.append(cp)
                events.append(self._event(
                    s.stage_id, "checkpoint", STAGE_COMPLETED, STAGE_COMPLETED, True,
                    f"checkpoint {cp.checkpoint_id}",
                ))

            if failed_stage:
                break

        # Rollback on failure
        if failed_stage and checkpoints:
            last_cp = checkpoints[-1]
            # If failure is the last attempted, roll back to previous checkpoint
            if len(checkpoints) >= 1:
                target = checkpoints[-1]
                # Mark failed and subsequent as rolled back conceptually
                for s in stages:
                    if s.state == STAGE_FAILED:
                        s.state = STAGE_ROLLED_BACK
                rb = RollbackRecord(
                    rollback_id=str(uuid.uuid4())[:10],
                    from_stage=failed_stage,
                    to_checkpoint=target.checkpoint_id,
                    success=True,
                    message=f"Rolled back to checkpoint after {target.stage_id}",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
                rollbacks.append(rb)
                rolled_back = True
                events.append(self._event(
                    failed_stage, "rollback", STAGE_FAILED, STAGE_ROLLED_BACK, True,
                    rb.message,
                ))

        stats = WorkflowStats(
            total_stages=len(stages),
            running=sum(1 for s in stages if s.state == STAGE_RUNNING),
            completed=sum(1 for s in stages if s.state == STAGE_COMPLETED),
            failed=sum(1 for s in stages if s.state in (STAGE_FAILED, STAGE_ROLLED_BACK)),
            skipped=sum(1 for s in stages if s.state == STAGE_SKIPPED),
            remaining=sum(1 for s in stages if s.state == STAGE_PENDING),
            checkpoints=len(checkpoints),
            rollbacks=len(rollbacks),
        )
        self_ok = self._self_verify(stages, checkpoints, events, gate_violations)

        _log.info(
            "WorkflowRunner: stages=%d completed=%d failed=%d cps=%d",
            len(stages), stats.completed, stats.failed, len(checkpoints),
        )
        return (
            workflow_id, stages, checkpoints, events, rollbacks, stats,
            gate_violations, resumed, rolled_back, self_ok,
        )

    def self_verify(
        self,
        stages: List[WorkflowStage],
        checkpoints: List[Checkpoint],
        events: List[WorkflowEvent],
        gate_violations: int,
        self_ok: bool,
    ) -> bool:
        if not stages:
            return False
        if not events:
            return False
        return self_ok

    # ------------------------------------------------------------------

    def _build(
        self,
        request_data: GenericData,
        orch_data: GenericData,
        scheduler_data: GenericData,
    ) -> List[WorkflowStage]:
        stages: List[WorkflowStage] = []
        seen: Set[str] = set()
        order = 0

        def _add(
            sid: str,
            name: str = "",
            mode: str = MODE_SEQUENTIAL,
            condition: str = "",
            branch: str = "",
            depends: Optional[List[str]] = None,
            engine_id: str = "",
            ord_override: Optional[int] = None,
        ) -> None:
            nonlocal order
            if not sid or sid in seen:
                return
            seen.add(sid)
            o = ord_override if ord_override is not None else order
            order = max(order, o) + 1
            stages.append(WorkflowStage(
                stage_id=sid,
                name=name or sid,
                order=o,
                mode=mode,
                state=STAGE_PENDING,
                condition=condition,
                branch=branch,
                depends_on=list(depends or []),
                engine_id=engine_id,
            ))

        # Explicit stages from request
        prev = ""
        for i, it in enumerate(request_data.items or []):
            if isinstance(it, str):
                deps = [prev] if prev else []
                _add(f"stage_{it}", name=it, depends=deps, engine_id=it)
                prev = f"stage_{it}"
            elif isinstance(it, dict):
                sid = str(it.get("stage_id") or it.get("id") or it.get("name") or f"stage_{i}")
                mode = str(it.get("mode") or MODE_SEQUENTIAL)
                if mode not in (MODE_SEQUENTIAL, MODE_PARALLEL, MODE_CONDITIONAL):
                    mode = MODE_SEQUENTIAL
                deps = it.get("depends_on") or it.get("dependencies") or []
                if isinstance(deps, str):
                    deps = [deps]
                if not deps and prev and mode == MODE_SEQUENTIAL:
                    deps = [prev]
                _add(
                    sid=sid,
                    name=str(it.get("name") or sid),
                    mode=mode,
                    condition=str(it.get("condition") or ""),
                    branch=str(it.get("branch") or ""),
                    depends=[str(d) for d in deps],
                    engine_id=str(it.get("engine_id") or ""),
                    ord_override=it.get("order"),
                )
                prev = sid

        # From orchestrator plan
        if not stages:
            prev = ""
            for i, step in enumerate(orch_data.items or []):
                if isinstance(step, dict):
                    eid = str(step.get("engine_id") or step.get("id") or f"step_{i}")
                    deps = [prev] if prev else []
                    _add(
                        sid=f"stage_{eid}",
                        name=str(step.get("action") or step.get("name") or eid),
                        depends=deps,
                        engine_id=eid,
                    )
                    prev = f"stage_{eid}"
                elif isinstance(step, str):
                    deps = [prev] if prev else []
                    _add(f"stage_{step}", name=step, depends=deps, engine_id=step)
                    prev = f"stage_{step}"

        # From scheduler tasks
        if not stages:
            prev = ""
            for i, t in enumerate(scheduler_data.items or []):
                if isinstance(t, dict):
                    tid = str(t.get("task_id") or t.get("id") or f"task_{i}")
                    deps = [prev] if prev else []
                    _add(f"stage_{tid}", name=str(t.get("name") or tid), depends=deps)
                    prev = f"stage_{tid}"

        if not stages:
            for name in ("analyze", "plan", "build", "validate", "deliver"):
                deps = [stages[-1].stage_id] if stages else []
                _add(f"stage_{name}", name=name, depends=deps, engine_id=name)

        return stages

    def _validate_stage(self, stage: WorkflowStage) -> bool:
        if not stage.stage_id:
            return False
        if stage.mode not in (MODE_SEQUENTIAL, MODE_PARALLEL, MODE_CONDITIONAL):
            return False
        return True

    def _eval_condition(self, stage: WorkflowStage, raw: Dict) -> bool:
        """Simple condition evaluator for branches."""
        cond = stage.condition or ""
        branch = stage.branch or ""
        flags = raw.get("conditions") or {}
        if not isinstance(flags, dict):
            flags = {}

        if branch == BRANCH_ELSE:
            # run if no if-branch matched — simplified: always allow else if not skipped by flags
            return not flags.get("if_taken", False)
        if branch == BRANCH_IF or cond:
            key = cond or "default_if"
            return bool(flags.get(key, True))
        if branch == BRANCH_SWITCH:
            switch_val = flags.get("switch")
            return str(flags.get("case", "")) == str(stage.name) or switch_val is None
        return True

    def _order_of(self, stages: List[WorkflowStage], stage_id: str) -> int:
        for s in stages:
            if s.stage_id == stage_id:
                return s.order
        return 0

    def _event(
        self,
        stage_id: str,
        action: str,
        from_state: str,
        to_state: str,
        success: bool,
        message: str,
    ) -> WorkflowEvent:
        return WorkflowEvent(
            event_id=str(uuid.uuid4())[:8],
            stage_id=stage_id,
            action=action,
            from_state=from_state,
            to_state=to_state,
            success=success,
            message=message,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def _self_verify(
        self,
        stages: List[WorkflowStage],
        checkpoints: List[Checkpoint],
        events: List[WorkflowEvent],
        gate_violations: int,
    ) -> bool:
        if not stages:
            return False
        if not events:
            return False
        # Completed stages should have checkpoints (unless skipped/failed early)
        completed = [s for s in stages if s.state == STAGE_COMPLETED]
        if completed and not checkpoints:
            return False
        return True


__all__ = ["WorkflowRunner"]
