"""
Generators package — hybrid set.

Formal + Planning + Reviews + Performance + Git/Repo engines.
"""

from .formal_understanding import FormalUnderstandingEngine
from .formal_generation import FormalGenerationEngine
from .project_planner import ProjectPlanningEngine
from .project_structure_planning import ProjectStructurePlanningEngine
from .execution_planning import ExecutionPlanningEngine
from .architecture_decision import ArchitectureDecisionEngine
from .technology_selection import TechnologySelectionEngine
from .risk_detection import RiskDetectionEngine
from .generation_readiness import GenerationReadinessEngine
from .generation_strategy import GenerationStrategyEngine
from .code_generation_planning import CodeGenerationPlanningEngine
from .structure_generator import StructureGenerationEngine
from .file_planner import FileGenerationPlanningEngine
from .dependency_resolver import DependencyResolutionEngine
from .project_context import ProjectContextEngine
from .component_detector import ComponentDetectionEngine
from .security_review import SecurityReviewEngine
from .performance_optimization import PerformanceOptimizationEngine
from .architecture_compliance import ArchitectureComplianceEngine
from .code_optimization import CodeOptimizationEngine
from .code_refactoring import CodeRefactoringEngine
from .static_analysis import StaticAnalysisEngine
from .unit_test_generation import UnitTestGenerationEngine
from .capability_analyzer import ProjectCapabilityAnalyzerEngine
from .blueprint_validator import BlueprintValidatorEngine
from .git_operations import GitOperationsEngine
from .repository_management import RepositoryManagementEngine
from .workspace_management import WorkspaceManagementEngine
from .file_system import FileSystemEngine
from .live_deployment import LiveDeploymentEngine

__all__ = [
    "FormalUnderstandingEngine",
    "FormalGenerationEngine",
    "ProjectPlanningEngine",
    "ProjectStructurePlanningEngine",
    "ExecutionPlanningEngine",
    "ArchitectureDecisionEngine",
    "TechnologySelectionEngine",
    "RiskDetectionEngine",
    "GenerationReadinessEngine",
    "GenerationStrategyEngine",
    "CodeGenerationPlanningEngine",
    "StructureGenerationEngine",
    "FileGenerationPlanningEngine",
    "DependencyResolutionEngine",
    "ProjectContextEngine",
    "ComponentDetectionEngine",
    "SecurityReviewEngine",
    "PerformanceOptimizationEngine",
    "ArchitectureComplianceEngine",
    "CodeOptimizationEngine",
    "CodeRefactoringEngine",
    "StaticAnalysisEngine",
    "UnitTestGenerationEngine",
    "ProjectCapabilityAnalyzerEngine",
    "BlueprintValidatorEngine",
    "GitOperationsEngine",
    "RepositoryManagementEngine",
    "WorkspaceManagementEngine",
    "FileSystemEngine",
    "LiveDeploymentEngine",
]
