"""
Project Planning Engine (Specification 004) \u2014 the planning brain.

The :class:`ProjectPlanningEngine` is the planning brain of the system.
It does **not** generate code, create files, or build folders.  Its
sole function is to convert the analysis report into a professional,
clear build plan \u2014 the :class:`ProjectBlueprint` \u2014 that the
rest of the system relies on.

Data source
-----------
The engine is **forbidden** from reading the user's request or
analysing it.  Its only source of information is the
:class:`~telegram_bot_engine.engines.generators.analyzer.AnalysisReport`
produced by the Core Request Analyzer Engine.  The report is read from
the ``analysis_report`` artefact in the generation context.

Responsibility
--------------
* Convert requirements into a complete execution plan.
* Divide the project into clear phases.
* Determine execution order.
* Identify the required generator engines.
* Identify the relationships between all parts of the project.

Output
------
The final output is a :class:`ProjectBlueprint`, stored in the context
as the ``project_blueprint`` artefact.  It is the official reference
that all generation engines after this point must rely on.  No engine
may modify the blueprint directly \u2014 any future modification must go
through a dedicated engine.

The blueprint is built in several internal steps:

1. **Project identity** \u2014 name, type, language, libraries, database.
2. **Expected structure** \u2014 the folder/file layout.
3. **Feature breakdown** \u2014 each feature becomes an independent
   :class:`FeatureUnit`.
4. **Internal components** \u2014 each feature introduces components
   with priorities.
5. **Component relationships** \u2014 the edges between components.
6. **Dependency graph** \u2014 the full dependency map.
7. **Execution plan** \u2014 the eight phases with tasks assigned.
8. **Risk detection** \u2014 conflicts, missing, missing phases,
   incomplete dependencies.
9. **Validation** \u2014 the three required checks.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from .blueprint import (
    BlueprintRisk,
    BlueprintValidation,
    ComponentRelationship,
    ExpectedStructure,
    InternalComponent,
    ProjectBlueprint,
    ProjectIdentity,
    RequiredEngine,
    StructureEntry,
)
from .dependency_graph import DependencyGraph
from .execution_plan import DEFAULT_PHASES, ExecutionPhase, ExecutionPlan
from .feature_unit import (
    PRIORITY_CRITICAL,
    PRIORITY_HIGH,
    PRIORITY_NORMAL,
    PRIORITY_LOW,
    FeatureUnit,
)
from .risk_detection import RiskDetector
from .validation import BlueprintValidator


# ---------------------------------------------------------------------------
# Bot-type profiles for the planner.
# Each profile returns the planning pieces for a bot type: default
# structure, default components, and feature-to-phase mapping.  New bot
# types can be added by adding a function and a dispatch entry \u2014 no
# existing code changes.
# ---------------------------------------------------------------------------

def _slugify(text: str) -> str:
    """Convert text into a valid Python package name."""
    ar_map = [
        ("\u0645\u062a\u062c\u0631", "store"), ("\u0625\u0644\u0643\u062a\u0631\u0648\u0646\u064a", "ecommerce"),
        ("\u062c\u0631\u0648\u0628", "group"), ("\u0627\u062f\u0627\u0631\u0629", "admin"),
        ("\u062a\u062d\u0645\u064a\u0644", "downloader"), ("\u0641\u064a\u062f\u064a\u0648", "video"),
        ("\u0630\u0643\u0627\u0621", "ai"), ("\u0627\u0635\u0637\u0646\u0627\u0639\u064a", "assistant"),
        ("\u0645\u0647\u0645\u0629", "task"), ("\u062a\u0630\u0643\u064a\u0631", "reminder"),
        ("\u0627\u062e\u0628\u0627\u0631", "news"), ("\u0637\u0642\u0633", "weather"),
        ("\u0627\u0633\u0639\u0627\u0631", "prices"), ("\u0639\u0645\u0644\u0629", "currency"),
    ]
    slug = text
    for ar, en in ar_map:
        slug = slug.replace(ar, f" {en} ")
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", slug).strip("_").lower()
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug or "generated_bot"


# Default structure entries common to all bot types.
def _common_structure(root: str) -> List[StructureEntry]:
    return [
        StructureEntry(path=f"{root}/", kind="directory",
                       description="Root package directory."),
        StructureEntry(path=f"{root}/__init__.py", kind="file",
                       description="Package initialiser."),
        StructureEntry(path=f"{root}/config.py", kind="file",
                       description="Configuration loader."),
        StructureEntry(path=f"{root}/main.py", kind="file",
                       description="Bot entry point."),
        StructureEntry(path=f"{root}/handlers/", kind="directory",
                       description="Message and callback handlers."),
        StructureEntry(path=f"{root}/handlers/__init__.py", kind="file",
                       description="Handlers package."),
        StructureEntry(path=f"{root}/models/", kind="directory",
                       description="Database models."),
        StructureEntry(path=f"{root}/models/__init__.py", kind="file",
                       description="Models package."),
        StructureEntry(path="requirements.txt", kind="file",
                       description="Python dependencies."),
        StructureEntry(path=".env.example", kind="file",
                       description="Environment variable template."),
        StructureEntry(path="README.md", kind="file",
                       description="Project documentation."),
    ]


# Mapping of feature keyword patterns to internal component names.
# This is how the planner decides which components a feature introduces
# and which phase each component belongs to.
_FEATURE_COMPONENT_MAP: Dict[str, Dict[str, Any]] = {
    "admin": {
        "component": "admin_panel",
        "display_name": "Admin Panel",
        "phase": "generate_code",
        "priority": PRIORITY_HIGH,
    },
    "subscription": {
        "component": "subscription_system",
        "display_name": "Subscription System",
        "phase": "generate_code",
        "priority": PRIORITY_NORMAL,
    },
    "database": {
        "component": "database",
        "display_name": "Database Layer",
        "phase": "build_database",
        "priority": PRIORITY_CRITICAL,
    },
    "logging": {
        "component": "logger",
        "display_name": "Logging System",
        "phase": "create_files",
        "priority": PRIORITY_HIGH,
    },
    "settings": {
        "component": "settings_manager",
        "display_name": "Settings Manager",
        "phase": "create_files",
        "priority": PRIORITY_NORMAL,
    },
    "command": {
        "component": "commands",
        "display_name": "Commands",
        "phase": "generate_code",
        "priority": PRIORITY_NORMAL,
    },
    "ai": {
        "component": "ai_integration",
        "display_name": "AI Integration",
        "phase": "generate_code",
        "priority": PRIORITY_NORMAL,
    },
    "payment": {
        "component": "payment_integration",
        "display_name": "Payment Integration",
        "phase": "generate_code",
        "priority": PRIORITY_NORMAL,
    },
    "download": {
        "component": "downloader",
        "display_name": "Media Downloader",
        "phase": "generate_code",
        "priority": PRIORITY_NORMAL,
    },
    "warning": {
        "component": "warning_system",
        "display_name": "Warning System",
        "phase": "generate_code",
        "priority": PRIORITY_NORMAL,
    },
    "mute": {
        "component": "mute_system",
        "display_name": "Mute System",
        "phase": "generate_code",
        "priority": PRIORITY_NORMAL,
    },
    "ban": {
        "component": "ban_system",
        "display_name": "Ban System",
        "phase": "generate_code",
        "priority": PRIORITY_NORMAL,
    },
    "cart": {
        "component": "cart_system",
        "display_name": "Shopping Cart",
        "phase": "generate_code",
        "priority": PRIORITY_NORMAL,
    },
    "order": {
        "component": "order_system",
        "display_name": "Order System",
        "phase": "generate_code",
        "priority": PRIORITY_NORMAL,
    },
}


def _feature_to_component(feature_name: str) -> Optional[Dict[str, Any]]:
    """Map a feature name to its component definition, if known."""
    name_lower = feature_name.lower()
    for key, mapping in _FEATURE_COMPONENT_MAP.items():
        if key in name_lower:
            return mapping
    return None


# ---------------------------------------------------------------------------
# The engine
# ---------------------------------------------------------------------------

class ProjectPlanningEngine(BaseEngine):
    """The planning brain \u2014 converts an AnalysisReport into a
    ProjectBlueprint.

    This engine is forbidden from reading the user request directly.
    It reads the ``analysis_report`` artefact from the context and
    produces a ``project_blueprint`` artefact.
    """

    def __init__(self) -> None:
        super().__init__(
            name="project_planner",
            version="1.0.0",
            description=(
                "Converts the AnalysisReport into a professional "
                "ProjectBlueprint that drives all generation engines. "
                "Does not generate code or create files."
            ),
            tags=["planning"],
            metadata={"phase": "planning"},
        )
        self._risk_detector = RiskDetector()
        self._validator = BlueprintValidator()

    # -----------------------------------------------------------------
    # Main entry point
    # -----------------------------------------------------------------

    def execute(self, context: GenerationContext) -> StageResult:
        # Step 0: obtain the analysis report \u2014 the only data source.
        report = context.get("analysis_report")
        if report is None:
            return self.failed([
                "No 'analysis_report' artefact found. The Project "
                "Planning Engine requires the Core Request Analyzer to "
                "have run first. The planning engine does not read the "
                "raw request."
            ])

        self._log.info("Planning project from analysis report",
                       {"project_name": report.project_name,
                        "features": len(report.features),
                        "bot_type": (report.primary_bot_type.type
                                     if report.primary_bot_type else "general")})

        # Build the blueprint step by step.
        blueprint = ProjectBlueprint()

        # Step 1: project identity.
        blueprint.identity = self._build_identity(report)

        # Step 2: expected structure.
        blueprint.structure = self._build_structure(report, blueprint.identity)

        # Step 3: feature breakdown.
        blueprint.features = self._breakdown_features(report)

        # Step 4: internal components.
        blueprint.components = self._build_components(report, blueprint.features)

        # Step 5: component relationships.
        blueprint.relationships = self._build_relationships(
            report, blueprint.components, blueprint.features)

        # Step 6: dependency graph.
        blueprint.dependency_graph = self._build_dependency_graph(
            blueprint.components, blueprint.features, report)

        # Step 7: required engines.
        blueprint.required_engines = self._build_required_engines(
            report, blueprint.features)

        # Step 8: execution plan.
        blueprint.execution_plan = self._build_execution_plan(
            blueprint.features, blueprint.components,
            blueprint.dependency_graph, blueprint.required_engines)

        # Step 9: risk detection.
        blueprint.risks = self._risk_detector.detect(
            conflicts=report.conflicts,
            missing_info=report.missing_info,
            feature_units=blueprint.features,
            components=blueprint.components,
            dependency_graph=blueprint.dependency_graph,
            execution_plan=blueprint.execution_plan,
        )

        # Step 10: validation.
        blueprint.validation = self._validator.validate(
            feature_units=blueprint.features,
            dependency_graph=blueprint.dependency_graph,
            execution_plan=blueprint.execution_plan,
            risks=blueprint.risks,
        )

        # Finalise: the blueprint is ready only if validation passed.
        blueprint.ready = blueprint.validation.valid

        # Record notes and warnings.
        blueprint.notes = list(report.notes)
        blueprint.warnings = list(report.warnings)
        if blueprint.validation.warnings:
            blueprint.warnings.extend(blueprint.validation.warnings)

        # Store the blueprint in the context as the authoritative plan.
        context.set("project_blueprint", blueprint)
        context.metadata["project_blueprint"] = blueprint

        self._log.info("Project blueprint built",
                       {"valid": blueprint.ready,
                        "components": len(blueprint.components),
                        "features": len(blueprint.features),
                        "phases": len(blueprint.execution_plan.phases),
                        "risks": len(blueprint.risks)})

        if not blueprint.ready:
            error_msgs = [r.description for r in blueprint.risks
                          if r.severity == "error"]
            if blueprint.validation.errors:
                error_msgs.extend(blueprint.validation.errors)
            return self.failed(
                errors=error_msgs or ["Project blueprint validation failed."],
                outputs={"project_blueprint": blueprint},
                warnings=blueprint.warnings,
            )

        return self.ok(
            outputs={"project_blueprint": blueprint},
            metadata={
                "components": len(blueprint.components),
                "features": len(blueprint.features),
                "phases": len(blueprint.execution_plan.phases),
            },
        )

    # -----------------------------------------------------------------
    # Step 1: project identity
    # -----------------------------------------------------------------

    def _build_identity(self, report) -> ProjectIdentity:
        bot_type = "general"
        if report.primary_bot_type:
            bot_type = report.primary_bot_type.type

        # Determine the project name.
        name = _slugify(report.project_name or report.cleaned_request)[:40]
        if not name.replace("_", "").isalnum():
            name = "generated_bot"

        # Determine the language and framework.
        language = "python"
        language_version = "3.11"
        framework = "python-telegram-bot"
        for tech in report.technologies:
            if tech.category == "language" and tech.name.lower() == "python":
                language = "python"
            if tech.category == "framework":
                framework = tech.name

        # Determine the database.
        database = ""
        for tech in report.technologies:
            if tech.category == "database":
                database = tech.name.lower()
                break

        # Determine the libraries.
        libraries: List[str] = [f"{framework}>=20.7"]
        for tech in report.technologies:
            if tech.category == "library":
                libraries.append(tech.name)
            if tech.category == "external_api":
                libraries.append(tech.name)
        # Add database library.
        if database:
            if database == "sqlite":
                libraries.append("SQLAlchemy>=2.0")
            elif database == "postgres" or database == "postgresql":
                libraries.append("SQLAlchemy>=2.0")
                libraries.append("psycopg2-binary")
            elif database == "mysql":
                libraries.append("SQLAlchemy>=2.0")
                libraries.append("PyMySQL")

        # De-duplicate libraries while preserving order.
        seen: set = set()
        unique_libs: List[str] = []
        for lib in libraries:
            if lib not in seen:
                seen.add(lib)
                unique_libs.append(lib)

        display_name = report.project_name or report.cleaned_request[:60]

        return ProjectIdentity(
            name=name,
            display_name=display_name,
            bot_type=bot_type,
            language=language,
            language_version=language_version,
            framework=framework,
            libraries=unique_libs,
            database=database,
        )

    # -----------------------------------------------------------------
    # Step 2: expected structure
    # -----------------------------------------------------------------

    def _build_structure(self, report, identity: ProjectIdentity) -> ExpectedStructure:
        root = identity.name
        entries = _common_structure(root)
        # Add bot-type-specific entries.
        if identity.database:
            entries.append(StructureEntry(
                path=f"{root}/models/base.py", kind="file",
                description="Database base/model definitions.",
            ))
        return ExpectedStructure(root=root, entries=entries)

    # -----------------------------------------------------------------
    # Step 3: feature breakdown
    # -----------------------------------------------------------------

    def _breakdown_features(self, report) -> List[FeatureUnit]:
        units: List[FeatureUnit] = []
        for feature in report.features:
            mapping = _feature_to_component(feature.name)
            component_name = mapping["component"] if mapping else feature.name
            phase = mapping["phase"] if mapping else "generate_code"
            priority = mapping["priority"] if mapping else PRIORITY_NORMAL

            # Determine if the feature needs the database.
            requires_db = (
                "database" in feature.name.lower()
                or "subscription" in feature.name.lower()
                or "order" in feature.name.lower()
                or "cart" in feature.name.lower()
                or bool(feature.related_entities)
            )

            # Build dependency hints from the feature's related_features.
            depends_on_features: List[str] = []
            for related in feature.related_features:
                # Only include if it looks like a feature name.
                if related and related != feature.name:
                    depends_on_features.append(related)

            unit = FeatureUnit(
                name=feature.name,
                display_name=feature.display_name or feature.name,
                description=feature.description,
                source_feature=feature.name,
                build_priority=priority,
                phase=phase,
                introduces_components=[component_name],
                depends_on_components=[],
                depends_on_features=depends_on_features,
                parallel_safe=True,
                requires_database=requires_db,
                requires_config=bool(feature.related_entities),
                confidence=feature.confidence,
                metadata={"keywords": list(feature.keywords)},
            )
            units.append(unit)
        return units

    # -----------------------------------------------------------------
    # Step 4: internal components
    # -----------------------------------------------------------------

    def _build_components(self, report,
                           feature_units: List[FeatureUnit]) -> List[InternalComponent]:
        components: List[InternalComponent] = []
        seen_names: set = set()

        # Always include core infrastructure components.
        core_components = [
            InternalComponent(
                name="config_loader", display_name="Configuration Loader",
                kind="infrastructure", priority=PRIORITY_CRITICAL,
                description="Loads environment and configuration settings.",
                dependencies=[],
            ),
            InternalComponent(
                name="logger", display_name="Logging System",
                kind="infrastructure", priority=PRIORITY_HIGH,
                description="Structured logging for the bot.",
                dependencies=["config_loader"],
            ),
        ]
        for comp in core_components:
            if comp.name not in seen_names:
                components.append(comp)
                seen_names.add(comp.name)

        # Add a database component if any feature needs it or the
        # identity declares a database.
        needs_db = any(u.requires_database for u in feature_units)
        # Also check technologies for a database.
        has_db_tech = any(t.category == "database" for t in report.technologies)
        if needs_db or has_db_tech:
            db_comp = InternalComponent(
                name="database", display_name="Database Layer",
                kind="infrastructure", priority=PRIORITY_CRITICAL,
                description="Database connection, models, and session "
                           "management.",
                dependencies=["config_loader"],
            )
            if db_comp.name not in seen_names:
                components.append(db_comp)
                seen_names.add(db_comp.name)

        # Add a component for each feature unit.
        for unit in feature_units:
            comp_name = (unit.introduces_components[0]
                         if unit.introduces_components else unit.name)
            if comp_name in seen_names:
                continue
            # Determine dependencies: database features depend on the
            # database component.
            deps: List[str] = []
            if unit.requires_database and "database" in seen_names:
                deps.append("database")
            comp = InternalComponent(
                name=comp_name,
                display_name=unit.display_name,
                kind="feature",
                priority=unit.build_priority,
                description=unit.description,
                source_feature=unit.name,
                dependencies=deps,
            )
            components.append(comp)
            seen_names.add(comp_name)

        return components

    # -----------------------------------------------------------------
    # Step 5: component relationships
    # -----------------------------------------------------------------

    def _build_relationships(self, report, components: List[InternalComponent],
                              feature_units: List[FeatureUnit]) -> List[ComponentRelationship]:
        relationships: List[ComponentRelationship] = []
        comp_names = {c.name for c in components}

        # From component dependencies.
        for comp in components:
            for dep in comp.dependencies:
                if dep in comp_names:
                    relationships.append(ComponentRelationship(
                        source=comp.name, target=dep, kind="depends_on",
                        description=f"{comp.name} depends on {dep}.",
                    ))

        # From the analysis report relationships.
        for rel in report.relationships:
            source = rel.source
            target = rel.target
            # Only include if both sides are known components.
            if source in comp_names and target in comp_names:
                relationships.append(ComponentRelationship(
                    source=source, target=target, kind=rel.kind,
                    description=rel.description,
                ))

        # From feature unit dependencies on other features.
        for unit in feature_units:
            for dep_feature in unit.depends_on_features:
                # Map the feature to its component name.
                dep_comp = None
                for u in feature_units:
                    if u.name == dep_feature and u.introduces_components:
                        dep_comp = u.introduces_components[0]
                        break
                if dep_comp and dep_comp in comp_names \
                        and unit.introduces_components:
                    source_comp = unit.introduces_components[0]
                    if source_comp != dep_comp:
                        relationships.append(ComponentRelationship(
                            source=source_comp, target=dep_comp,
                            kind="depends_on",
                            description=f"{source_comp} depends on "
                                        f"{dep_comp} (via feature "
                                        f"{unit.name}).",
                        ))

        return relationships

    # -----------------------------------------------------------------
    # Step 6: dependency graph
    # -----------------------------------------------------------------

    def _build_dependency_graph(self, components: List[InternalComponent],
                                feature_units: List[FeatureUnit],
                                report) -> DependencyGraph:
        graph = DependencyGraph()
        # Add all components as nodes.
        for comp in components:
            graph.add_node(
                name=comp.name, kind="component",
                priority=comp.priority,
                dependencies=comp.dependencies,
            )
        # Add edges from component dependencies.
        for comp in components:
            for dep in comp.dependencies:
                graph.add_edge(comp.name, dep)
        # Add feature nodes and their dependencies.
        for unit in feature_units:
            comp_name = (unit.introduces_components[0]
                          if unit.introduces_components else unit.name)
            graph.add_node(
                name=unit.name, kind="feature",
                priority=unit.build_priority,
            )
            # Feature depends on its components.
            for comp in unit.introduces_components:
                # Skip self-loops: a feature may introduce a component
                # with the same name (e.g. the "database" feature
                # introduces the "database" component).  A self-edge
                # would create a false cycle.
                if comp == unit.name:
                    continue
                graph.add_edge(unit.name, comp)
            # Feature depends on other features.
            for dep_feature in unit.depends_on_features:
                if dep_feature == unit.name:
                    continue
                graph.add_edge(unit.name, dep_feature)
        return graph

    # -----------------------------------------------------------------
    # Step 7: required engines
    # -----------------------------------------------------------------

    def _build_required_engines(self, report,
                                 feature_units: List[FeatureUnit]) -> List[RequiredEngine]:
        engines: List[RequiredEngine] = []
        seen: set = set()

        def _add(engine_id: str, name: str, purpose: str, phase: str,
                 priority: int) -> None:
            if engine_id not in seen:
                engines.append(RequiredEngine(
                    engine_id=engine_id, name=name, purpose=purpose,
                    phase=phase, priority=priority,
                ))
                seen.add(engine_id)

        # Phase 1: project setup.
        _add("project_setup_engine", "Project Setup Engine",
             "Initialise the project directory and configuration.",
             "project_setup", 10)

        # Phase 2: create structure.
        _add("structure_builder_engine", "Structure Builder Engine",
             "Create the folder and file structure.",
             "create_structure", 10)

        # Phase 3: build database (if needed).
        needs_db = any(u.requires_database for u in feature_units) or \
            any(t.category == "database" for t in report.technologies)
        if needs_db:
            _add("database_engine", "Database Engine",
                 "Build database models and schema.",
                 "build_database", 10)

        # Phase 4: create files.
        _add("file_builder_engine", "File Builder Engine",
             "Create source files for each component.",
             "create_files", 10)

        # Phase 5: generate code.
        _add("code_generator_engine", "Code Generator Engine",
             "Generate implementation code for each component.",
             "generate_code", 10)

        # Phase 6: wire components.
        _add("wiring_engine", "Wiring Engine",
             "Wire components together and connect dependencies.",
             "wire_components", 10)

        # Phase 7: review.
        _add("review_engine", "Review Engine",
             "Review the generated project for correctness.",
             "review", 10)

        # Phase 8: export.
        _add("export_engine", "Export Engine",
             "Export the final, packaged project.",
             "export", 10)

        return engines

    # -----------------------------------------------------------------
    # Step 8: execution plan
    # -----------------------------------------------------------------

    def _build_execution_plan(self, feature_units: List[FeatureUnit],
                              components: List[InternalComponent],
                              graph: DependencyGraph,
                              required_engines: List[RequiredEngine]) -> ExecutionPlan:
        # Build the eight phases from the default definitions.
        phases: List[ExecutionPhase] = []
        for phase_def in DEFAULT_PHASES:
            phase = ExecutionPhase(
                number=phase_def.number,
                name=phase_def.name,
                description=phase_def.description,
                can_parallel=phase_def.can_parallel,
                skippable=phase_def.skippable,
            )
            phases.append(phase)

        # Assign engines to phases.
        for engine in required_engines:
            phase = self._find_phase_by_name(phases, engine.phase)
            if phase:
                phase.engines.append(engine.engine_id)

        # Assign components to phases based on their kind and priority.
        for comp in components:
            phase = self._assign_component_to_phase(comp, phases)
            if phase:
                phase.components.append(comp.name)

        # Assign features to phases.
        for unit in feature_units:
            phase = self._find_phase_by_name(phases, unit.phase)
            if phase:
                phase.features.append(unit.name)
            else:
                # Default to phase 5.
                phase5 = self._find_phase_by_number(phases, 5)
                if phase5:
                    phase5.features.append(unit.name)

        # Phase 1 always has the project setup.
        phase1 = self._find_phase_by_number(phases, 1)
        if phase1 and not phase1.components and not phase1.engines:
            phase1.components.append("config_loader")

        # Phase 2 always has the structure builder.
        phase2 = self._find_phase_by_number(phases, 2)
        if phase2 and not phase2.components:
            phase2.components.append("project_structure")

        # Phase 6 always has wiring (components from the graph).
        phase6 = self._find_phase_by_number(phases, 6)
        if phase6 and not phase6.components:
            phase6.components.append("component_wiring")

        # Phase 7 always has review.
        phase7 = self._find_phase_by_number(phases, 7)
        if phase7 and not phase7.components:
            phase7.components.append("project_review")

        # Phase 8 always has export.
        phase8 = self._find_phase_by_number(phases, 8)
        if phase8 and not phase8.components:
            phase8.components.append("project_export")

        # Build parallel design summary.
        groups = graph.parallel_groups()
        parallel_design: Dict[str, Any] = {
            "parallel_phases": ["build_database",
                                "create_files",
                                "generate_code"],
            "sequential_phases": ["project_setup",
                                  "create_structure",
                                  "wire_components",
                                  "review",
                                  "export"],
            "dependency_groups": {
                str(k): v for k, v in groups.items()
            },
        }

        return ExecutionPlan(
            phases=phases,
            parallel_design=parallel_design,
            order_locked=True,
        )

    def _find_phase_by_name(self, phases: List[ExecutionPhase],
                             name: str) -> Optional[ExecutionPhase]:
        for p in phases:
            if p.name == name:
                return p
        return None

    def _find_phase_by_number(self, phases: List[ExecutionPhase],
                               number: int) -> Optional[ExecutionPhase]:
        for p in phases:
            if p.number == number:
                return p
        return None

    def _assign_component_to_phase(self, comp: InternalComponent,
                                    phases: List[ExecutionPhase]) -> Optional[ExecutionPhase]:
        """Assign a component to the appropriate phase by its kind/priority."""
        if comp.kind == "infrastructure":
            if comp.name == "config_loader":
                return self._find_phase_by_number(phases, 1)
            if comp.name == "database":
                return self._find_phase_by_number(phases, 3)
            if comp.name == "logger":
                return self._find_phase_by_number(phases, 4)
            # Other infrastructure defaults to phase 4.
            return self._find_phase_by_number(phases, 4)
        # Feature components go to phase 5 (code generation).
        return self._find_phase_by_number(phases, 5)


__all__ = ["ProjectPlanningEngine"]
