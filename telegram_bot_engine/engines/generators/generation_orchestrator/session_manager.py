"""
SessionManager + TaskDistributor — Specification 028

Creates the generation session, distributes tasks from the strategy,
defines checkpoints and initial progress/logs.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Tuple

from .report_data import (
    GenerationTask, Checkpoint, SessionLogEntry, ProgressInfo,
    TASK_PENDING, TASK_ASSIGNED,
    PHASE_FOUNDATION, PHASE_CORE, PHASE_FEATURES, PHASE_INTEGRATION,
    PHASE_CONFIGURATION, PHASE_TESTING, PHASE_DOCUMENTATION, PHASE_FINALIZE,
    ALL_PHASES,
)
from .data_readers import GenericData

_log = logging.getLogger("engine.generation_orchestrator.session_manager")

# Map strategy stage → orchestrator phase
_STAGE_TO_PHASE = {
    "foundation": PHASE_FOUNDATION,
    "core": PHASE_CORE,
    "features": PHASE_FEATURES,
    "integration": PHASE_INTEGRATION,
    "configuration": PHASE_CONFIGURATION,
    "testing": PHASE_TESTING,
    "documentation": PHASE_DOCUMENTATION,
}

# Which downstream engine will eventually own each phase
_PHASE_ENGINE = {
    PHASE_FOUNDATION: "file_scaffold_generator",
    PHASE_CORE: "core_code_generator",
    PHASE_FEATURES: "feature_code_generator",
    PHASE_INTEGRATION: "integration_code_generator",
    PHASE_CONFIGURATION: "config_generator",
    PHASE_TESTING: "test_scaffold_generator",
    PHASE_DOCUMENTATION: "docs_generator",
    PHASE_FINALIZE: "generation_orchestrator",
}


class SessionManager:
    def create_session(
        self,
        strategy_data: GenericData,
        readiness_data: GenericData,
        project_id: str = "",
    ) -> Tuple[
        str,                    # session_id
        str,                    # project_id
        List[GenerationTask],
        List[Checkpoint],
        List[SessionLogEntry],
        ProgressInfo,
        bool,                   # readiness_approved
        float,                  # readiness_score
    ]:
        now = datetime.now(timezone.utc).isoformat()
        session_id = str(uuid.uuid4())
        if not project_id:
            project_id = f"proj_{session_id[:8]}"

        # Readiness
        readiness_approved = False
        readiness_score = 0.0
        if readiness_data.available and readiness_data.raw:
            readiness_score = float(readiness_data.raw.get("overall_score") or 0)
            approval = (readiness_data.raw.get("approval_status") or "").lower()
            readiness_approved = approval == "approved" or readiness_score >= 100.0

        # Tasks from strategy items
        tasks: List[GenerationTask] = []
        items = strategy_data.items if strategy_data.available else []
        if not items and strategy_data.raw:
            items = strategy_data.raw.get("items") or []

        order = 0
        for it in items:
            if not isinstance(it, dict):
                continue
            order += 1
            stage = (it.get("stage") or "foundation").lower()
            phase = _STAGE_TO_PHASE.get(stage, PHASE_FOUNDATION)
            engine = _PHASE_ENGINE.get(phase, "file_scaffold_generator")
            tasks.append(GenerationTask(
                task_id=f"task.{it.get('item_id') or order}",
                name=it.get("name") or it.get("item_id") or f"item-{order}",
                phase=phase,
                assigned_engine=engine,
                status=TASK_ASSIGNED,
                depends_on=list(it.get("depends_on") or []),
                item_ref=it.get("item_id") or "",
                path=it.get("path") or "",
                order=order,
            ))

        # Fallback minimal task set if strategy empty
        if not tasks:
            defaults = [
                ("scaffold root", PHASE_FOUNDATION, "telegram_bot/"),
                ("core package", PHASE_CORE, "telegram_bot/core/"),
                ("handlers", PHASE_CORE, "telegram_bot/handlers/"),
                ("services", PHASE_CORE, "telegram_bot/services/"),
                ("integrations", PHASE_INTEGRATION, "telegram_bot/integrations/"),
                ("configs", PHASE_CONFIGURATION, "telegram_bot/configs/"),
                ("tests", PHASE_TESTING, "tests/"),
                ("readme", PHASE_DOCUMENTATION, "README.md"),
            ]
            for name, phase, path in defaults:
                order += 1
                tasks.append(GenerationTask(
                    task_id=f"task.fallback.{order}",
                    name=name,
                    phase=phase,
                    assigned_engine=_PHASE_ENGINE.get(phase, "file_scaffold_generator"),
                    status=TASK_ASSIGNED,
                    path=path,
                    order=order,
                ))

        # Finalise task
        tasks.append(GenerationTask(
            task_id="task.finalize",
            name="Finalize generation session",
            phase=PHASE_FINALIZE,
            assigned_engine="generation_orchestrator",
            status=TASK_PENDING,
            depends_on=[t.task_id for t in tasks],
            order=order + 1,
        ))

        # Checkpoints after each phase that has tasks
        checkpoints: List[Checkpoint] = []
        phases_with_tasks = sorted(
            {t.phase for t in tasks if t.phase != PHASE_FINALIZE},
            key=lambda p: ALL_PHASES.index(p) if p in ALL_PHASES else 99,
        )
        for phase in phases_with_tasks:
            phase_tasks = [t.task_id for t in tasks if t.phase == phase]
            checkpoints.append(Checkpoint(
                checkpoint_id=f"cp.{phase}",
                after_phase=phase,
                created_at=now,
                description=f"Checkpoint after {phase} phase",
                completed_task_ids=phase_tasks,
                snapshot_keys=["generation_session_report"],
            ))

        # Initial logs
        logs = [
            SessionLogEntry(
                entry_id=str(uuid.uuid4()),
                timestamp=now,
                source="generation_orchestrator",
                event="session_created",
                result="ok",
                details=f"session={session_id} project={project_id} tasks={len(tasks)}",
            ),
            SessionLogEntry(
                entry_id=str(uuid.uuid4()),
                timestamp=now,
                source="generation_orchestrator",
                event="tasks_distributed",
                result="ok",
                details=f"{len(tasks)} tasks assigned across {len(phases_with_tasks)} phases",
            ),
        ]
        if readiness_approved:
            logs.append(SessionLogEntry(
                entry_id=str(uuid.uuid4()),
                timestamp=now,
                source="generation_orchestrator",
                event="readiness_confirmed",
                result="ok",
                details=f"readiness_score={readiness_score}",
            ))
        else:
            logs.append(SessionLogEntry(
                entry_id=str(uuid.uuid4()),
                timestamp=now,
                source="generation_orchestrator",
                event="readiness_warning",
                result="warn",
                details=f"readiness not fully approved (score={readiness_score})",
            ))

        progress = ProgressInfo(
            total_tasks=len(tasks),
            completed_tasks=0,
            failed_tasks=0,
            pending_tasks=len(tasks),
            percent=0.0,
            current_phase=phases_with_tasks[0] if phases_with_tasks else PHASE_FOUNDATION,
            estimated_remaining_seconds=len(tasks) * 5,
        )

        _log.info(
            "SessionManager created session=%s tasks=%d checkpoints=%d approved=%s",
            session_id[:8], len(tasks), len(checkpoints), readiness_approved,
        )
        return (
            session_id, project_id, tasks, checkpoints, logs,
            progress, readiness_approved, readiness_score,
        )


__all__ = ["SessionManager"]
