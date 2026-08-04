"""
Core bootstrap — assembles the engine from its components.

This module is the *only* place that knows which concrete engines,
builders, and validators to instantiate and register.  It wires the
whole system together using the configuration and returns a ready-to-use
:class:`~telegram_bot_engine.registry.EngineRegistry` and a configured
:class:`~telegram_bot_engine.pipeline.PipelineOrchestrator`.

Keeping the wiring in a single function means:

* Adding a new engine is a one-line change here.
* Tests can build a custom registry by calling ``bootstrap`` with a
  custom configuration or by manually registering components.
* The pipeline never imports concrete engines.
"""

from __future__ import annotations

from typing import Optional

from ..builders import DirectoryBuilder, FileBuilder, PythonModuleBuilder
from ..configuration import ConfigSource, Configuration
from ..configuration.defaults import build_default_schema
from ..engines.generators import (
    AnalyzerEngine,
    BlueprintComposerEngine,
    IntentParserEngine,
    ProjectPlanningEngine,
    BlueprintValidatorEngine,
    StructureGenerationEngine,
    ComponentDetectionEngine,
    FileGenerationPlanningEngine,
    DependencyResolutionEngine,
    ProjectContextEngine,
    IntelligenceGraphEngine,
    RequirementIntelligenceEngine,
    SemanticUnderstandingEngine,
    RequirementNormalizationEngine,
    ArchitectureDecisionEngine,
    TechnologySelectionEngine,
    ProjectCapabilityAnalyzerEngine,
    RiskDetectionEngine,
    ExecutionPlanningEngine,
    ProjectStructurePlanningEngine,
    ModuleArchitecturePlanningEngine,
    ComponentArchitecturePlanningEngine,
    InterfaceContractPlanningEngine,
    DataFlowPlanningEngine,
    ResourceDependencyPlanningEngine,
    GenerationStrategyEngine,
    GenerationReadinessEngine,
    GenerationOrchestratorEngine,
    CodeGenerationPlanningEngine,
    ProjectBuilderEngine,
    ClassGenerationEngine,
    FunctionGenerationEngine,
    BusinessLogicGenerationEngine,
    CodeOptimizationEngine,
    SecurityReviewEngine,
    PerformanceOptimizationEngine,
    ArchitectureComplianceEngine,
    CodeRefactoringEngine,
    StaticAnalysisEngine,
    RuntimeSimulationEngine,
    SelfHealingEngine,
    IntegrationVerificationEngine,
    UnitTestGenerationEngine,
    E2EScenarioTestingEngine,
    ProductionReadinessEngine,
    RepositoryManagementEngine,
    GitOperationsEngine,
    FileSystemEngine,
    WorkspaceManagementEngine,
    DependencyManagementEngine,
    EnvironmentConfigEngine,
    EngineEcosystemEngine,
    EngineOrchestratorEngine,
    ExecutionContextEngine,
    SynchronizationEngine,
    ResourceManagementEngine,
    SystemMonitoringEngine,
    CentralLoggingEngine,
    ConfigurationManagementEngine,
    SecurityPermissionEngine,
    ServiceManagementEngine,
    MessageQueueEngine,
    TaskSchedulerEngine,
    WorkflowExecutionEngine,
    LiveDeploymentEngine,
)
from ..logging import EngineLogger
from ..manager import CoreEngineManager
from ..output import OutputManager
from ..pipeline import PipelineOrchestrator
from ..registry import EngineRegistry
from ..validators import BlueprintValidator, StructureValidator
from .errors import ConfigurationError


def build_configuration(
    sources: Optional[list] = None,
) -> Configuration:
    """Build a :class:`Configuration` from the default schema and sources.

    ``sources`` is a list of :class:`ConfigSource` instances.  When
    omitted, the defaults and environment are used.
    """
    schema = build_default_schema()
    if sources is None:
        sources = [ConfigSource(name="defaults")]
    return Configuration(schema=schema, sources=sources)


def bootstrap(
    config: Optional[Configuration] = None,
    sources: Optional[list] = None,
) -> tuple:
    """Initialise the whole engine and return (registry, orchestrator).

    Parameters:
        config: An already-built configuration.  When ``None`` a new
            configuration is built from ``sources`` (or defaults).
        sources: Configuration sources used when ``config`` is ``None``.

    Returns:
        A tuple ``(registry, orchestrator, manager)`` ready to generate
        bots.  The ``manager`` is the :class:`CoreEngineManager` that
        governs engine lifecycle, dependencies, and execution order.
    """
    if config is None:
        config = build_configuration(sources=sources)

    EngineLogger.configure(config)

    registry = EngineRegistry()

    # -- builders ----------------------------------------------------------
    directory_builder = DirectoryBuilder()
    file_builder = FileBuilder()
    python_module_builder = PythonModuleBuilder()
    registry.register_builder(directory_builder)
    registry.register_builder(file_builder)
    registry.register_builder(python_module_builder)

    # -- understanding engines ---------------------------------------------
    analyzer = AnalyzerEngine()
    intent_parser = IntentParserEngine()
    blueprint_composer = BlueprintComposerEngine()
    project_planner = ProjectPlanningEngine()
    registry.register_engine(analyzer)
    registry.register_engine(intent_parser)
    registry.register_engine(blueprint_composer)
    registry.register_engine(project_planner)

    # -- understanding engines (validator) -------------------------------
    blueprint_validator = BlueprintValidatorEngine()
    registry.register_engine(blueprint_validator)

    # -- structure generation engine (Specification 006) -----------------
    structure_generator = StructureGenerationEngine()
    registry.register_engine(structure_generator)

    # -- component detection engine (Specification 007) ------------------
    # The component detector scans the blueprint and structure map to
    # detect every software component before code generation begins.
    # It does not write code — it only produces a Component Registry.
    component_detector = ComponentDetectionEngine()
    registry.register_engine(component_detector)

    # -- file generation planning engine (Specification 008) -------------
    # The file planner plans every file the project will contain
    # before any file is created on disk.  It reads the blueprint,
    # validation report, structure map, and component registry, and
    # produces a File Generation Plan.  It does not write code or
    # create files.
    file_planner = FileGenerationPlanningEngine()
    registry.register_engine(file_planner)

    # -- dependency resolution engine (Specification 009) ----------------
    # The dependency resolver builds the complete dependency map for
    # the project before construction begins.  It reads the blueprint,
    # validation report, structure map, component registry, and file
    # generation plan, and produces a Dependency Resolution Report.
    # It does not write code, create files, install libraries, or add
    # dependencies.
    dependency_resolver = DependencyResolutionEngine()
    registry.register_engine(dependency_resolver)

    # -- project context engine (Specification 010) ---------------------
    # The project context engine builds the complete, unified project
    # context by merging the Project Blueprint, Blueprint Validation
    # Report, Project Structure Map, Component Registry, File
    # Generation Plan, and Dependency Resolution Report.  It produces
    # a Project Context artefact with precomputed O(1) look-up
    # indices.  It does not write code, create files, or make build
    # decisions.
    project_context_engine = ProjectContextEngine()
    registry.register_engine(project_context_engine)

    # -- intelligence graph engine (Specification 011) ------------------
    # The intelligence graph engine builds the complete, intelligent
    # project graph by converting the seven upstream artefacts
    # (blueprint, validation report, structure map, component
    # registry, file plan, dependency report, and project context)
    # into a single Project Intelligence Graph with 19 node types
    # and 12 edge kinds.  It produces O(1) look-up indices for
    # fast navigation and detects circular dependencies, broken
    # references, unused components, orphan files, and dead
    # components.  It does not write code, create files, or make
    # build decisions.
    intelligence_graph_engine = IntelligenceGraphEngine()
    registry.register_engine(intelligence_graph_engine)

    # -- requirement intelligence engine (Specification 012) -------------
    # The requirement intelligence engine understands the user's
    # request with the highest possible precision and converts it into
    # a precise set of engineering requirements.  It reads the four
    # data sources (user request, project context, intelligence graph,
    # and knowledge base), performs intent analysis across five
    # dimensions, classifies requirements into nine categories,
    # detects missing information, ambiguity points, and conflicts,
    # assigns priorities, validates quality, and produces a
    # Requirement Intelligence Report.  It does not write code,
    # create files, choose libraries, or make build decisions.
    requirement_intelligence_engine = RequirementIntelligenceEngine()
    registry.register_engine(requirement_intelligence_engine)

    # -- semantic understanding engine (Specification 013) ---------------
    # The semantic understanding engine understands the TRUE meaning
    # of the user's request.  It does not rely on keywords alone —
    # it relies on understanding the intent, the context, and the
    # meaning.  It reads the five data sources (user request,
    # requirement intelligence report, project context, knowledge
    # base, and built-in language rules), performs full sentence
    # analysis (dialect normalization, spell correction, abbreviation
    # expansion, synonym resolution), extracts the true intent, maps
    # all variations to a unified intent, detects ambiguities and
    # requests clarification, understands the relationships between
    # the parts of the request, calculates the confidence score, and
    # produces a Semantic Understanding Report.  It does not write
    # code, create files, choose libraries, or make build decisions.
    semantic_understanding_engine = SemanticUnderstandingEngine()
    registry.register_engine(semantic_understanding_engine)

    # -- requirement normalization engine (Specification 014) -------------
    # The requirement normalization engine transforms ALL user
    # requirements into a unified, canonical model that every
    # downstream engine can understand.  It reads five data sources
    # (user request, requirement intelligence report, semantic
    # understanding report, project context, and knowledge base),
    # unifies all names into canonical snake_case keys, unifies all
    # terminology into a single vocabulary, removes duplicates using
    # Jaccard similarity, validates consistency (detecting conflicts,
    # terminology variations, and lost requirements), links each
    # requirement to its feature, component, priority, dependencies,
    # and expected output, caches the normalized model for
    # re-normalization, enforces quality rules, and produces a
    # Normalization Report.  It does not write code, create files,
    # choose libraries, or make build decisions.
    requirement_normalization_engine = RequirementNormalizationEngine()
    registry.register_engine(requirement_normalization_engine)

    # -- architecture decision engine (Specification 015) ----------------
    # The architecture decision engine makes ALL architectural
    # decisions for the project.  It reads five data sources
    # (normalized requirement model, intelligence graph, requirement
    # intelligence report, semantic understanding report, and
    # knowledge base), analyses the project across five dimensions
    # (size, scalability, performance, security, maintainability),
    # and makes all eight architectural decisions (layers, modules,
    # services, dependency structure, project layout, communication
    # pattern, error handling strategy, configuration strategy).
    # Every decision has a reason, an analysis, an impact, and at
    # least one rejected alternative.  It validates all decisions,
    # enforces quality rules (no architecture that fails quality or
    # scalability requirements is allowed), caches the decision
    # report for re-decision, and produces an Architecture Decision
    # Report — the official reference for all other engines.  It
    # does not write code, create files, or build the project.
    architecture_decision_engine = ArchitectureDecisionEngine()
    registry.register_engine(architecture_decision_engine)

    # -- technology selection engine (Specification 016) -----------------
    # The technology selection engine selects all ten technology
    # categories for the project based on the architecture decision,
    # requirements, intelligence graph, knowledge base, and quality
    # rules.  It performs compatibility, performance, and security
    # analyses, validates selections through the quality gate, and
    # produces a Technology Selection Report.  It does not write code,
    # create files, or build the project.
    technology_selection_engine = TechnologySelectionEngine()
    registry.register_engine(technology_selection_engine)

    # -- project capability analyzer engine (Specification 017) -----------
    # The project capability analyzer engine analyzes the project's
    # full capability before building starts.  It reads five data
    # sources (architecture decision report, technology selection
    # report, normalized requirement model, intelligence graph, and
    # knowledge base), performs five analyses (complexity, resource
    # estimation, scalability, architecture stress, dependencies),
    # validates the architecture through the quality gate (blocks
    # generation if the architecture can't meet performance,
    # scalability, or quality requirements), and produces a Project
    # Capability Report.  It does not write code, create files, or
    # build the project.
    capability_analyzer_engine = ProjectCapabilityAnalyzerEngine()
    registry.register_engine(capability_analyzer_engine)

    # -- risk detection engine (Specification 018) ----------------------
    # The risk detection engine detects all potential risks before
    # project generation begins.  It reads five data sources
    # (project capability report, architecture decision report,
    # technology selection report, normalized requirement model, and
    # knowledge base), performs seven risk analyses (architecture,
    # performance, scalability, security, dependency, maintenance,
    # resource), classifies each risk by severity (Critical, High,
    # Medium, Low), produces recommendations, and determines the
    # project's readiness for the generation phase.  It blocks
    # generation if a Critical risk exists.  It does not write code,
    # create files, or start the build process.
    risk_detection_engine = RiskDetectionEngine()
    registry.register_engine(risk_detection_engine)

    # -- execution planning engine (Specification 019) --------------------
    # The execution planning engine converts all previous analysis and
    # planning artefacts into a precise, ordered Execution Plan that the
    # remaining engines can follow step by step.  It partitions work into
    # phases, orders tasks, resolves dependencies, detects parallel-safe
    # work, detects conflicts, and validates the plan through a quality
    # gate.  It does not write code, create files, or start the build.
    execution_planning_engine = ExecutionPlanningEngine()
    registry.register_engine(execution_planning_engine)

    # -- project structure planning engine (Specification 020) ------------
    # Designs the complete project folder and file structure before any
    # file is created. Produces the Project Structure Blueprint.
    project_structure_planning_engine = ProjectStructurePlanningEngine()
    registry.register_engine(project_structure_planning_engine)

    # -- module architecture planning engine (Specification 021) ----------
    # Designs all logical modules, assigns responsibilities, defines
    # interfaces and prevents overlapping before any file is created.
    module_architecture_planning_engine = ModuleArchitecturePlanningEngine()
    registry.register_engine(module_architecture_planning_engine)

    # -- component architecture planning engine (Specification 022) -------
    # Splits every module into independent components with clear
    # responsibilities, interfaces and dependencies.
    component_architecture_planning_engine = ComponentArchitecturePlanningEngine()
    registry.register_engine(component_architecture_planning_engine)

    # -- interface & contract planning engine (Specification 023) ---------
    # Designs all interfaces and contracts that regulate communication
    # between modules and components, preventing strong coupling.
    interface_contract_planning_engine = InterfaceContractPlanningEngine()
    registry.register_engine(interface_contract_planning_engine)

    # -- data flow planning engine (Specification 024) --------------------
    # Designs all data movement paths, transformations, validation and
    # security rules before generation begins.
    data_flow_planning_engine = DataFlowPlanningEngine()
    registry.register_engine(data_flow_planning_engine)

    # -- resource & dependency planning engine (Specification 025) --------
    # Plans all libraries, frameworks, resources, versions, compatibility
    # and risks before any file is generated.
    resource_dependency_planning_engine = ResourceDependencyPlanningEngine()
    registry.register_engine(resource_dependency_planning_engine)

    # -- generation strategy engine (Specification 026) -------------------
    # Builds the complete ordered strategy for generating the project
    # (stages, items, rules, rollback, optimisations) before any file is written.
    generation_strategy_engine = GenerationStrategyEngine()
    registry.register_engine(generation_strategy_engine)

    # -- generation readiness validation engine (Specification 027) -------
    # Final gate before generation. Requires 100% readiness across all
    # upstream blueprints; rejects if any critical gap remains.
    generation_readiness_engine = GenerationReadinessEngine()
    registry.register_engine(generation_readiness_engine)

    # -- project generation orchestrator engine (Specification 028) -------
    # Creates the generation session, distributes tasks to downstream
    # generators, defines checkpoints and tracks progress. Does not write
    # code itself — it orchestrates the generation process.
    generation_orchestrator_engine = GenerationOrchestratorEngine()
    registry.register_engine(generation_orchestrator_engine)

    # -- intelligent code generation planning engine (Specification 029 v2)
    # Last planning step before code is written. Builds adaptive queue,
    # SOLID/Clean rules, style, dry simulation, rollback and intelligence score.
    code_generation_planning_engine = CodeGenerationPlanningEngine()
    registry.register_engine(code_generation_planning_engine)

    # -- intelligent project builder engine (Specification 030) -----------
    # Scaffolds the project: folders, empty files, manifest and registry
    # according to the intelligent plan. Does not write business logic.
    project_builder_engine = ProjectBuilderEngine()
    registry.register_engine(project_builder_engine)

    # -- intelligent class generation engine (Specification 031) ----------
    # Emits class skeletons only (no business logic, no method bodies).
    class_generation_engine = ClassGenerationEngine()
    registry.register_engine(class_generation_engine)

    # -- intelligent function generation engine (Specification 032) -------
    # Emits method/function signatures and constructors only — no bodies.
    function_generation_engine = FunctionGenerationEngine()
    registry.register_engine(function_generation_engine)

    # -- intelligent business logic generation engine (Specification 033) -
    # ULTRA CRITICAL: production-grade bodies with Clean Code / SOLID / security.
    business_logic_generation_engine = BusinessLogicGenerationEngine()
    registry.register_engine(business_logic_generation_engine)

    # -- intelligent code optimization engine (Specification 034) ---------
    # ULTRA CRITICAL: optimises generated source without changing behaviour.
    code_optimization_engine = CodeOptimizationEngine()
    registry.register_engine(code_optimization_engine)

    # -- intelligent security review engine (Specification 035) -----------
    # ULTRA CRITICAL: detects/fixes vulns; blocks critical issues.
    security_review_engine = SecurityReviewEngine()
    registry.register_engine(security_review_engine)

    # -- intelligent performance optimization engine (Specification 036) --
    # ULTRA CRITICAL: CPU/memory/API/Telegram optimisations; no behaviour change.
    performance_optimization_engine = PerformanceOptimizationEngine()
    registry.register_engine(performance_optimization_engine)

    # -- intelligent architecture compliance engine (Specification 037) ---
    # ULTRA CRITICAL: implementation must match architecture; violations block.
    architecture_compliance_engine = ArchitectureComplianceEngine()
    registry.register_engine(architecture_compliance_engine)

    # -- intelligent code refactoring engine (Specification 038) ----------
    # ULTRA CRITICAL: safe refactorings only; behaviour & architecture preserved.
    code_refactoring_engine = CodeRefactoringEngine()
    registry.register_engine(code_refactoring_engine)

    # -- intelligent static analysis engine (Specification 039) -----------
    # ULTRA CRITICAL: static analysis without execution; critical issues block.
    static_analysis_engine = StaticAnalysisEngine()
    registry.register_engine(static_analysis_engine)

    # -- intelligent runtime simulation engine (Specification 040) --------
    # ULTRA CRITICAL: simulate runtime/Telegram/stress; block on crash/leak.
    runtime_simulation_engine = RuntimeSimulationEngine()
    registry.register_engine(runtime_simulation_engine)

    # -- intelligent self-healing engine (Specification 041) --------------
    # ULTRA CRITICAL: auto-repair upstream issues; re-validate; never break arch.
    self_healing_engine = SelfHealingEngine()
    registry.register_engine(self_healing_engine)

    # -- intelligent integration verification engine (Specification 042) --
    # ULTRA CRITICAL: verify whole-system integration; block on failure.
    integration_verification_engine = IntegrationVerificationEngine()
    registry.register_engine(integration_verification_engine)

    # -- intelligent unit test generation engine (Specification 043) ------
    # ULTRA CRITICAL: generate unit tests for all units; block if any fail.
    unit_test_generation_engine = UnitTestGenerationEngine()
    registry.register_engine(unit_test_generation_engine)

    # -- intelligent e2e scenario testing engine (Specification 044) ------
    # ULTRA CRITICAL: real-user scenario testing; any failed scenario blocks.
    e2e_scenario_testing_engine = E2EScenarioTestingEngine()
    registry.register_engine(e2e_scenario_testing_engine)

    # -- production readiness certification engine (Specification 045) ----
    # MAXIMUM CRITICAL: final certificate; Telegram token gate CLOSED until certified.
    production_readiness_engine = ProductionReadinessEngine()
    registry.register_engine(production_readiness_engine)

    # -- intelligent repository management engine (Specification 046) -----
    # CRITICAL: ownership+permission gated; never autonomous.
    repository_management_engine = RepositoryManagementEngine()
    registry.register_engine(repository_management_engine)

    # -- intelligent git operations engine (Specification 047) ------------
    # CRITICAL: git ops after user/perm/repo checks; dangerous ops need confirm.
    git_operations_engine = GitOperationsEngine()
    registry.register_engine(git_operations_engine)

    # -- intelligent file system engine (Specification 048) ---------------
    # CRITICAL: abstract FS layer; backup+integrity; workspace isolation.
    file_system_engine = FileSystemEngine()
    registry.register_engine(file_system_engine)

    # -- intelligent workspace management engine (Specification 049) ------
    # CRITICAL: isolated project workspaces; lifecycle; snapshots; recovery.
    workspace_management_engine = WorkspaceManagementEngine()
    registry.register_engine(workspace_management_engine)

    # -- intelligent dependency management engine (Specification 050) -----
    # ULTRA CRITICAL: discover/validate/lock deps; block unsafe/incompatible.
    dependency_management_engine = DependencyManagementEngine()
    registry.register_engine(dependency_management_engine)

    # -- intelligent environment configuration engine (Specification 051) -
    # ULTRA CRITICAL: Dev/Test/Staging/Prod; secrets isolation; health checks.
    environment_config_engine = EnvironmentConfigEngine()
    registry.register_engine(environment_config_engine)

    # -- intelligent engine ecosystem & registry (Specification 052) ------
    # MAXIMUM CRITICAL: central registry; no engine runs unregistered.
    engine_ecosystem_engine = EngineEcosystemEngine()
    registry.register_engine(engine_ecosystem_engine)

    # -- intelligent engine orchestrator (Specification 053) ---------------
    # MAXIMUM CRITICAL: all engine execution flows through orchestrator only.
    engine_orchestrator_engine = EngineOrchestratorEngine()
    registry.register_engine(engine_orchestrator_engine)

    # -- intelligent execution context engine (Specification 054) ----------
    # CRITICAL: unified shared context; one active per project; versioned.
    execution_context_engine = ExecutionContextEngine()
    registry.register_engine(execution_context_engine)

    # -- intelligent synchronization engine (Specification 055) ------------
    # CRITICAL: all engines see same data; conflict-free atomic sync.
    synchronization_engine = SynchronizationEngine()
    registry.register_engine(synchronization_engine)

    # -- intelligent resource management engine (Specification 056) --------
    # CRITICAL: CPU/RAM/storage/threads; limits; leak detection; cleanup.
    resource_management_engine = ResourceManagementEngine()
    registry.register_engine(resource_management_engine)

    # -- intelligent system monitoring engine (Specification 057) ----------
    # CRITICAL: real-time health/performance/anomaly/alert/trend monitoring.
    system_monitoring_engine = SystemMonitoringEngine()
    registry.register_engine(system_monitoring_engine)

    # -- central logging & audit engine (Specification 058) ----------------
    # CRITICAL: single log sink; immutable; redact secrets; search; rotate.
    central_logging_engine = CentralLoggingEngine()
    registry.register_engine(central_logging_engine)

    # -- configuration management engine (Specification 059) ---------------
    # CRITICAL: central config registry; versioning; rollback; protection.
    configuration_management_engine = ConfigurationManagementEngine()
    registry.register_engine(configuration_management_engine)

    # -- security & permission engine (Specification 060) ------------------
    # MAXIMUM CRITICAL: least privilege, isolation, auth, audit, recovery.
    security_permission_engine = SecurityPermissionEngine()
    registry.register_engine(security_permission_engine)

    # -- service management engine (Specification 061) ---------------------
    # MAXIMUM CRITICAL: service registry, lifecycle, health, recovery.
    service_management_engine = ServiceManagementEngine()
    registry.register_engine(service_management_engine)

    # -- message queue engine (Specification 062) --------------------------
    # MAXIMUM CRITICAL: reliable inter-engine messaging, DLQ, dedupe.
    message_queue_engine = MessageQueueEngine()
    registry.register_engine(message_queue_engine)

    # -- task scheduler engine (Specification 063) -------------------------
    # MAXIMUM CRITICAL: schedule tasks with deps, policies, load awareness.
    task_scheduler_engine = TaskSchedulerEngine()
    registry.register_engine(task_scheduler_engine)

    # -- workflow execution engine (Specification 064) ---------------------
    # MAXIMUM CRITICAL: workflow stages, checkpoints, resume, rollback.
    workflow_execution_engine = WorkflowExecutionEngine()
    registry.register_engine(workflow_execution_engine)

    # -- live deployment engine (Specification 065) ------------------------
    # MAXIMUM CRITICAL: token, secrets, deploy, health, functional tests.
    live_deployment_engine = LiveDeploymentEngine()
    registry.register_engine(live_deployment_engine)

    # -- validators --------------------------------------------------------
    registry.register_validator(BlueprintValidator())
    registry.register_validator(StructureValidator())

    # -- Core Engine Manager (Specification 003) --------------------------
    # The manager is the executive brain that governs every engine's
    # lifecycle, dependencies, execution order, and error handling.
    # It is wired here so the pipeline (and any caller) has access to
    # managed execution.  The manager uses the same engine instances
    # already registered with the dumb EngineRegistry.
    manager = CoreEngineManager(config=config)
    manager.register(analyzer, engine_id="analyzer", priority=10,
                     dependencies=[])
    manager.register(intent_parser, engine_id="intent_parser", priority=20,
                     dependencies=["analyzer"])
    manager.register(blueprint_composer, engine_id="blueprint_composer",
                     priority=30, dependencies=["analyzer", "intent_parser"])
    manager.register(project_planner, engine_id="project_planner",
                     priority=40, dependencies=["analyzer"])
    manager.register(blueprint_validator, engine_id="blueprint_validator",
                     priority=50, dependencies=["project_planner"])
    manager.register(structure_generator, engine_id="structure_generator",
                     priority=60, dependencies=["blueprint_validator"])
    manager.register(component_detector, engine_id="component_detector",
                     priority=70, dependencies=["structure_generator"])
    manager.register(file_planner, engine_id="file_planner",
                     priority=80, dependencies=["component_detector"])
    manager.register(dependency_resolver, engine_id="dependency_resolver",
                     priority=95, dependencies=["file_planner"])
    manager.register(project_context_engine, engine_id="project_context",
                     priority=96, dependencies=["dependency_resolver"])
    manager.register(intelligence_graph_engine, engine_id="intelligence_graph",
                     priority=97, dependencies=["project_context"])
    manager.register(requirement_intelligence_engine,
                     engine_id="requirement_intelligence",
                     priority=98, dependencies=["intelligence_graph"])
    manager.register(semantic_understanding_engine,
                     engine_id="semantic_understanding",
                     priority=99, dependencies=["requirement_intelligence"])
    manager.register(requirement_normalization_engine,
                     engine_id="requirement_normalization",
                     priority=100, dependencies=["semantic_understanding"])
    manager.register(architecture_decision_engine,
                     engine_id="architecture_decision",
                     priority=101, dependencies=["requirement_normalization"])
    manager.register(technology_selection_engine,
                     engine_id="technology_selection",
                     priority=102,
                     dependencies=["architecture_decision"])
    manager.register(capability_analyzer_engine,
                     engine_id="capability_analyzer",
                     priority=103,
                     dependencies=["technology_selection"])
    manager.register(risk_detection_engine,
                     engine_id="risk_detection",
                     priority=104,
                     dependencies=["capability_analyzer"])
    manager.register(execution_planning_engine,
                     engine_id="execution_planning",
                     priority=105,
                     dependencies=["risk_detection"])
    manager.register(project_structure_planning_engine,
                     engine_id="project_structure_planning",
                     priority=106,
                     dependencies=["execution_planning"])
    manager.register(module_architecture_planning_engine,
                     engine_id="module_architecture_planning",
                     priority=107,
                     dependencies=["project_structure_planning"])
    manager.register(component_architecture_planning_engine,
                     engine_id="component_architecture_planning",
                     priority=108,
                     dependencies=["module_architecture_planning"])
    manager.register(interface_contract_planning_engine,
                     engine_id="interface_contract_planning",
                     priority=109,
                     dependencies=["component_architecture_planning"])
    manager.register(data_flow_planning_engine,
                     engine_id="data_flow_planning",
                     priority=110,
                     dependencies=["interface_contract_planning"])
    manager.register(resource_dependency_planning_engine,
                     engine_id="resource_dependency_planning",
                     priority=111,
                     dependencies=["data_flow_planning"])
    manager.register(generation_strategy_engine,
                     engine_id="generation_strategy",
                     priority=112,
                     dependencies=["resource_dependency_planning"])
    manager.register(generation_readiness_engine,
                     engine_id="generation_readiness",
                     priority=113,
                     dependencies=["generation_strategy"])
    manager.register(generation_orchestrator_engine,
                     engine_id="generation_orchestrator",
                     priority=114,
                     dependencies=["generation_readiness"])
    manager.register(code_generation_planning_engine,
                     engine_id="code_generation_planning",
                     priority=115,
                     dependencies=["generation_orchestrator"])
    manager.register(project_builder_engine,
                     engine_id="project_builder",
                     priority=116,
                     dependencies=["code_generation_planning"])
    manager.register(class_generation_engine,
                     engine_id="class_generation",
                     priority=117,
                     dependencies=["project_builder"])
    manager.register(function_generation_engine,
                     engine_id="function_generation",
                     priority=118,
                     dependencies=["class_generation"])
    manager.register(business_logic_generation_engine,
                     engine_id="business_logic_generation",
                     priority=119,
                     dependencies=["function_generation"])
    manager.register(code_optimization_engine,
                     engine_id="code_optimization",
                     priority=120,
                     dependencies=["business_logic_generation"])
    manager.register(security_review_engine,
                     engine_id="security_review",
                     priority=121,
                     dependencies=["code_optimization"])
    manager.register(performance_optimization_engine,
                     engine_id="performance_optimization",
                     priority=122,
                     dependencies=["security_review"])
    manager.register(architecture_compliance_engine,
                     engine_id="architecture_compliance",
                     priority=123,
                     dependencies=["performance_optimization"])
    manager.register(code_refactoring_engine,
                     engine_id="code_refactoring",
                     priority=124,
                     dependencies=["architecture_compliance"])
    manager.register(static_analysis_engine,
                     engine_id="static_analysis",
                     priority=125,
                     dependencies=["code_refactoring"])
    manager.register(runtime_simulation_engine,
                     engine_id="runtime_simulation",
                     priority=126,
                     dependencies=["static_analysis"])
    manager.register(self_healing_engine,
                     engine_id="self_healing",
                     priority=127,
                     dependencies=["runtime_simulation"])
    manager.register(integration_verification_engine,
                     engine_id="integration_verification",
                     priority=128,
                     dependencies=["self_healing"])
    manager.register(unit_test_generation_engine,
                     engine_id="unit_test_generation",
                     priority=129,
                     dependencies=["integration_verification"])
    manager.register(e2e_scenario_testing_engine,
                     engine_id="e2e_scenario_testing",
                     priority=130,
                     dependencies=["unit_test_generation"])
    manager.register(production_readiness_engine,
                     engine_id="production_readiness",
                     priority=131,
                     dependencies=["e2e_scenario_testing"])
    manager.register(repository_management_engine,
                     engine_id="repository_management",
                     priority=132,
                     dependencies=["production_readiness"])
    manager.register(git_operations_engine,
                     engine_id="git_operations",
                     priority=133,
                     dependencies=["repository_management"])
    manager.register(file_system_engine,
                     engine_id="file_system",
                     priority=134,
                     dependencies=["git_operations"])
    manager.register(workspace_management_engine,
                     engine_id="workspace_management",
                     priority=135,
                     dependencies=["file_system"])
    manager.register(dependency_management_engine,
                     engine_id="dependency_management",
                     priority=136,
                     dependencies=["workspace_management"])
    manager.register(environment_config_engine,
                     engine_id="environment_config",
                     priority=137,
                     dependencies=["dependency_management"])
    manager.register(engine_ecosystem_engine,
                     engine_id="engine_ecosystem",
                     priority=138,
                     dependencies=["environment_config"])
    manager.register(engine_orchestrator_engine,
                     engine_id="engine_orchestrator",
                     priority=139,
                     dependencies=["engine_ecosystem"])
    manager.register(execution_context_engine,
                     engine_id="execution_context",
                     priority=140,
                     dependencies=["engine_orchestrator"])
    manager.register(synchronization_engine,
                     engine_id="synchronization",
                     priority=141,
                     dependencies=["execution_context"])
    manager.register(resource_management_engine,
                     engine_id="resource_management",
                     priority=142,
                     dependencies=["synchronization"])
    manager.register(system_monitoring_engine,
                     engine_id="system_monitoring",
                     priority=143,
                     dependencies=["resource_management"])
    manager.register(central_logging_engine,
                     engine_id="central_logging",
                     priority=144,
                     dependencies=["system_monitoring"])
    manager.register(configuration_management_engine,
                     engine_id="configuration_management",
                     priority=145,
                     dependencies=["central_logging"])
    manager.register(security_permission_engine,
                     engine_id="security_permission",
                     priority=146,
                     dependencies=["configuration_management"])
    manager.register(service_management_engine,
                     engine_id="service_management",
                     priority=147,
                     dependencies=["security_permission"])
    manager.register(message_queue_engine,
                     engine_id="message_queue",
                     priority=148,
                     dependencies=["service_management"])
    manager.register(task_scheduler_engine,
                     engine_id="task_scheduler",
                     priority=149,
                     dependencies=["message_queue"])
    manager.register(workflow_execution_engine,
                     engine_id="workflow_execution",
                     priority=150,
                     dependencies=["task_scheduler"])
    manager.register(live_deployment_engine,
                     engine_id="live_deployment",
                     priority=151,
                     dependencies=["workflow_execution"])

    # -- output & pipeline -------------------------------------------------
    output_manager = OutputManager(config=config)
    orchestrator = PipelineOrchestrator(
        registry=registry, output_manager=output_manager, config=config,
    )

    return registry, orchestrator, manager


__all__ = ["bootstrap", "build_configuration"]
