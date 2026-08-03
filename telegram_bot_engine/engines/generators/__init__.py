"""
Generators package — concrete generator engines.

Each module in this package defines a single engine.  Engines are
imported and registered by the bootstrap function (see
:mod:`telegram_bot_engine.core.bootstrap`).
"""

from .intent_parser_engine import IntentParserEngine
from .blueprint_composer_engine import BlueprintComposerEngine
from .analyzer import AnalyzerEngine
from .project_planner import ProjectPlanningEngine
from .blueprint_validator import BlueprintValidatorEngine
from .structure_generator import StructureGenerationEngine
from .component_detector import ComponentDetectionEngine
from .file_planner import FileGenerationPlanningEngine
from .dependency_resolver import DependencyResolutionEngine
from .project_context import ProjectContextEngine
from .intelligence_graph import IntelligenceGraphEngine
from .requirement_intelligence import RequirementIntelligenceEngine
from .semantic_understanding import SemanticUnderstandingEngine
from .requirement_normalization import RequirementNormalizationEngine
from .architecture_decision import ArchitectureDecisionEngine
from .technology_selection import TechnologySelectionEngine
from .capability_analyzer import ProjectCapabilityAnalyzerEngine
from .risk_detection import RiskDetectionEngine
from .execution_planning import ExecutionPlanningEngine
from .project_structure_planning import ProjectStructurePlanningEngine
from .module_architecture_planning import ModuleArchitecturePlanningEngine
from .component_architecture_planning import ComponentArchitecturePlanningEngine
from .interface_contract_planning import InterfaceContractPlanningEngine

__all__ = [
    "IntentParserEngine",
    "BlueprintComposerEngine",
    "AnalyzerEngine",
    "ProjectPlanningEngine",
    "BlueprintValidatorEngine",
    "StructureGenerationEngine",
    "ComponentDetectionEngine",
    "FileGenerationPlanningEngine",
    "DependencyResolutionEngine",
    "ProjectContextEngine",
    "IntelligenceGraphEngine",
    "RequirementIntelligenceEngine",
    "SemanticUnderstandingEngine",
    "RequirementNormalizationEngine",
    "ArchitectureDecisionEngine",
    "TechnologySelectionEngine",
    "ProjectCapabilityAnalyzerEngine",
    "RiskDetectionEngine",
    "ExecutionPlanningEngine",
    "ProjectStructurePlanningEngine",
    "ModuleArchitecturePlanningEngine",
    "ComponentArchitecturePlanningEngine",
    "InterfaceContractPlanningEngine",
]
