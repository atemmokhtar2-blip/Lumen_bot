"""Control Plane: projects, plans, permissions, deployment records."""
from __future__ import annotations
from typing import Dict, Optional
from ..core.state import DeploymentState, JobState, ProjectState, RunState

class ControlPlane:
    def __init__(self) -> None:
        self._projects: Dict[str, ProjectState] = {}
        self._runs: Dict[str, RunState] = {}
        self._deployments: Dict[str, DeploymentState] = {}
        self._jobs: Dict[str, JobState] = {}
    def upsert_project(self, project: ProjectState) -> ProjectState:
        self._projects[project.project_id] = project
        return project
    def get_project(self, project_id: str) -> Optional[ProjectState]:
        return self._projects.get(project_id)
    def upsert_run(self, run: RunState) -> RunState:
        self._runs[run.run_id] = run
        return run
    def get_run(self, run_id: str) -> Optional[RunState]:
        return self._runs.get(run_id)
    def upsert_deployment(self, dep: DeploymentState) -> DeploymentState:
        self._deployments[dep.deployment_id] = dep
        return dep
    def get_deployment(self, deployment_id: str) -> Optional[DeploymentState]:
        return self._deployments.get(deployment_id)
    def upsert_job(self, job: JobState) -> JobState:
        self._jobs[job.job_id] = job
        return job
    def get_job(self, job_id: str) -> Optional[JobState]:
        return self._jobs.get(job_id)

__all__ = ["ControlPlane"]
