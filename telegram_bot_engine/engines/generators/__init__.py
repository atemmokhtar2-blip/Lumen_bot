"""
Generators package — working engines only.

Kept:
  Formal core:
    - FormalUnderstandingEngine
    - FormalGenerationEngine
    - ProjectPlanningEngine
    - ProjectStructurePlanningEngine

  Git / Push-Pull / Workspace chain (as requested):
    - WorkspaceManagementEngine
    - FileSystemEngine
    - DependencyResolutionEngine
    - RepositoryManagementEngine
    - GitOperationsEngine

  Supporting engines required by the above:
    - BlueprintValidatorEngine
    - ComponentDetectionEngine
    - FileGenerationPlanningEngine
    - StructureGenerationEngine
"""

from .formal_understanding import FormalUnderstandingEngine
from .formal_generation import FormalGenerationEngine
from .project_planner import ProjectPlanningEngine
from .project_structure_planning import ProjectStructurePlanningEngine

from .workspace_management import WorkspaceManagementEngine
from .file_system import FileSystemEngine
from .dependency_resolver import DependencyResolutionEngine
from .repository_management import RepositoryManagementEngine
from .git_operations import GitOperationsEngine

from .blueprint_validator import BlueprintValidatorEngine
from .component_detector import ComponentDetectionEngine
from .file_planner import FileGenerationPlanningEngine
from .structure_generator import StructureGenerationEngine

__all__ = [
    "FormalUnderstandingEngine",
    "FormalGenerationEngine",
    "ProjectPlanningEngine",
    "ProjectStructurePlanningEngine",
    "WorkspaceManagementEngine",
    "FileSystemEngine",
    "DependencyResolutionEngine",
    "RepositoryManagementEngine",
    "GitOperationsEngine",
    "BlueprintValidatorEngine",
    "ComponentDetectionEngine",
    "FileGenerationPlanningEngine",
    "StructureGenerationEngine",
]
