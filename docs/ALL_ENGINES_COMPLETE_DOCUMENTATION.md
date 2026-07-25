# Telegram Bot Generation Engine
## Complete Technical Documentation — All 14 Engines

> **This project is under active development — iterating through numbered
> Specifications.**
>
> Each specification adds one complete, tested engine to the generation
> pipeline. Implemented so far: **001 through 014** (14 engines).
> Specification **015** is next.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Architecture](#2-architecture)
3. [Core Infrastructure](#3-core-infrastructure)
4. [Engine 01 — Core Request Analyzer Engine](#4-engine-01--core-request-analyzer-engine)
5. [Engine 02 — Intent Parser Engine](#5-engine-02--intent-parser-engine)
6. [Engine 03 — Blueprint Composer Engine](#6-engine-03--blueprint-composer-engine)
7. [Engine 04 — Project Planning Engine](#7-engine-04--project-planning-engine)
8. [Engine 05 — Blueprint Validator Engine](#8-engine-05--blueprint-validator-engine)
9. [Engine 06 — Structure Generation Engine](#9-engine-06--structure-generation-engine)
10. [Engine 07 — Component Detection Engine](#10-engine-07--component-detection-engine)
11. [Engine 08 — File Generation Planning Engine](#11-engine-08--file-generation-planning-engine)
12. [Engine 09 — Dependency Resolution Engine](#12-engine-09--dependency-resolution-engine)
13. [Engine 10 — Project Context Engine](#13-engine-10--project-context-engine)
14. [Engine 11 — Intelligence Graph Engine](#14-engine-11--intelligence-graph-engine)
15. [Engine 12 — Requirement Intelligence Engine](#15-engine-12--requirement-intelligence-engine)
16. [Engine 13 — Semantic Understanding Engine](#16-engine-13--semantic-understanding-engine)
17. [Engine 14 — Requirement Normalization Engine](#17-engine-14--requirement-normalization-engine)
18. [Pipeline Architecture & Data Flow](#18-pipeline-architecture--data-flow)
19. [Core Engine Manager](#19-core-engine-manager)
20. [Test Suite Summary](#20-test-suite-summary)
21. [Technology Stack](#21-technology-stack)
22. [Design Principles](#22-design-principles)
23. [Project Statistics](#23-project-statistics)

---

## 1. System Overview

The **Telegram Bot Generation Engine** is not a Telegram bot — it is a
generation engine that takes a natural-language request and produces a
complete, ready-to-run Telegram bot project.

The system is built as a modular pipeline of **14 independent generation
engines**, each with a single responsibility. All engines communicate
exclusively through `GenerationContext` artefacts. No engine reads or
modifies another engine's outputs directly.

The pipeline has two logical phases:

- **Understanding Phase** (Engines 1–14) — the engines parse, understand,
  plan, and normalise the user's request into a complete, canonical model.

- **Building Phase** (future) — generator engines will read the canonical
  model and materialise the project files.

**Key phases of the understanding pipeline:**

- **Phase 1 — Analysis & Intent (Engines 1–3):** The request is parsed,
  cleaned, segmented, classified, and structured into an intent.

- **Phase 2 — Planning & Blueprint (Engines 4–5):** The intent is converted
  into a full `ProjectBlueprint` with features, dependency graph, execution
  plan, and risks, then validated across 6 layers.

- **Phase 3 — Structure & Components (Engines 6–9):** The project structure,
  components, file plan, and dependency map are generated.

- **Phase 4 — Context & Intelligence (Engines 10–11):** All upstream
  artefacts are unified into a `ProjectContext` and converted into a
  `ProjectIntelligenceGraph`.

- **Phase 5 — Understanding & Normalization (Engines 12–14):** The request
  is understood with precision, its true meaning is extracted, and all
  requirements are transformed into a unified, canonical model.

---

## 2. Architecture

### 2.1 Pipeline Architecture

The 14 engines run in a fixed order determined by priority and dependencies.
The `CoreEngineManager` builds the execution queue, checks dependencies, and
enforces fail-fast semantics.

```
Engine 01: Analyzer               (priority=10)
    ↓
Engine 02: Intent Parser           (priority=20, deps=[analyzer])
    ↓
Engine 03: Blueprint Composer     (priority=30, deps=[analyzer, intent_parser])
    ↓
Engine 04: Project Planner        (priority=40, deps=[analyzer])
    ↓
Engine 05: Blueprint Validator    (priority=50, deps=[project_planner])
    ↓
Engine 06: Structure Generator    (priority=60, deps=[blueprint_validator])
    ↓
Engine 07: Component Detector     (priority=70, deps=[structure_generator])
    ↓
Engine 08: File Planner           (priority=80, deps=[component_detector])
    ↓
Engine 09: Dependency Resolver     (priority=95, deps=[file_planner])
    ↓
Engine 10: Project Context        (priority=96, deps=[dependency_resolver])
    ↓
Engine 11: Intelligence Graph     (priority=97, deps=[project_context])
    ↓
Engine 12: Requirement Intelligence (priority=98, deps=[intelligence_graph])
    ↓
Engine 13: Semantic Understanding   (priority=99, deps=[requirement_intelligence])
    ↓
Engine 14: Requirement Normalization (priority=100, deps=[semantic_understanding])
```

### 2.2 Engine Contract Pattern

Every engine inherits from `BaseEngine` (in
`engines/base/base_engine.py`), which provides:

- A `logger` — structured logging via `EngineLogger`.
- An `ok(outputs)` helper — returns a successful `StageResult`.
- A `failed(errors)` helper — returns a failed `StageResult`.
- An `execute(context)` method — the engine's main entry point.

The `StageResult` has the following attributes:

| Attribute | Type | Description |
|-----------|------|-------------|
| `success` | `bool` | Whether the engine succeeded. |
| `outputs` | `dict` | The artefacts produced by the engine. |
| `errors` | `list[str]` | Error messages (empty if successful). |
| `warnings` | `list[str]` | Warning messages. |
| `metadata` | `dict` | Engine metadata (duration, stage, etc.). |

### 2.3 GenerationContext

The `GenerationContext` is the shared state that flows through the pipeline.
It is the **only** way engines communicate with each other.

| Attribute | Type | Description |
|-----------|------|-------------|
| `request` | `str` | The original user request (natural language). |
| `config` | `Configuration` | The configuration object. |
| `artefacts` | `dict[str, Any]` | Named artefacts produced by engines. |

Engines read from `context.artefacts` and write their outputs to
`context.artefacts` via `StageResult.outputs`.

### 2.4 Engine Registration and Ordering

All 14 engines are registered in `core/bootstrap.py`:

```python
manager.register(analyzer, engine_id="analyzer", priority=10, dependencies=[])
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
```

The `CoreEngineManager` sorts engines by priority (ascending) and respects
dependencies. Lower priority numbers run first.

---

## 3. Core Infrastructure

### 3.1 File Inventory

The project contains **192 Python files** across **29 directories**:

| Layer | Files | Description |
|-------|-------|-------------|
| `blueprint/` | 2 | Data model (Blueprint, BotMeta, etc.) |
| `builders/` | 4 | File-writing components |
| `configuration/` | 4 | Schema-validated configuration |
| `core/` | 6 | Contracts, context, result, errors, bootstrap |
| `engines/base/` | 3 | BaseEngine, BaseGenerator |
| `engines/generators/` | 167 | All 14 generation engines |
| `logging/` | 2 | EngineLogger facade |
| `manager/` | 6 | CoreEngineManager and sub-modules |
| `output/` | 2 | OutputManager |
| `pipeline/` | 9 | Orchestrator and 6 stages |
| `registry/` | 2 | EngineRegistry |
| `validators/` | 4 | Blueprint & structure validators |

### 3.2 Component Contract

The `Component` abstract base class defines the interface for all components:

| Method | Description |
|--------|-------------|
| `name` | The component name (string property). |
| `version` | The component version (string property). |

### 3.3 Engine Contract

The `Engine` abstract base class extends `Component`:

| Method | Description |
|--------|-------------|
| `initialize()` | Called once before the first run. |
| `execute(context)` | The main entry point. Returns `StageResult`. |

### 3.4 BaseEngine

`BaseEngine` (in `engines/base/base_engine.py`) provides shared boilerplate:

| Attribute/Method | Description |
|------------------|-------------|
| `logger` | Structured logger instance. |
| `ok(outputs)` | Returns a successful `StageResult` with the given outputs. |
| `failed(errors)` | Returns a failed `StageResult` with the given errors. |

---

## 4. Engine 01 — Core Request Analyzer Engine

### 4.1 Overview

| Property | Value |
|----------|-------|
| **Specification** | 002 |
| **Priority** | 10 |
| **Dependencies** | none |
| **Output Artefact** | `analysis_report` |
| **Tags** | `["analysis", "nlp", "parsing"]` |

The **Core Request Analyzer Engine** parses the user's natural-language
request through **10 stages** and produces an `AnalysisReport`. It cleans the
text, segments it, extracts keywords, classifies the bot type, identifies
features and technologies, analyses relationships, detects conflicts, and
identifies missing information.

### 4.2 The 10 Analysis Stages

| Stage | File | Responsibility |
|-------|------|----------------|
| 1 | `stage1_cleaner.py` | Normalises whitespace, removes noise. |
| 2 | `stage2_segmenter.py` | Splits the request into sentences and phrases. |
| 3 | `stage3_keyword_extractor.py` | Extracts keywords from the text. |
| 4 | `stage4_classifier.py` | Classifies the bot type. |
| 5 | `stage5_feature_extractor.py` | Identifies features. |
| 6 | `stage6_technology_extractor.py` | Identifies technologies. |
| 7 | `stage7_relationship_analyzer.py` | Analyses feature relationships. |
| 8 | `stage8_conflict_detector.py` | Detects conflicting requirements. |
| 9 | `stage9_missing_info_detector.py` | Detects missing information. |
| 10 | `stage10_report_builder.py` | Assembles the `AnalysisReport`. |

### 4.3 Data Model (AnalysisReport)

The `AnalysisReport` contains:

- Cleaned text
- Segments (sentences and phrases)
- Keywords
- Bot type classification
- Features
- Technologies
- Relationships
- Conflicts
- Missing information

### 4.4 Key Properties

- **Tolerant:** If a stage fails, the report is still produced with the
  available data.
- **Deterministic:** Same input always produces the same output.
- **Arabic-aware:** Handles Arabic text normalization.

### 4.5 Execution Flow

1. The engine receives the `GenerationContext` with the user request.
2. Each stage runs in order, reading the previous stage's output.
3. The final stage assembles the `AnalysisReport`.
4. The engine returns `ok({"analysis_report": report})`.

### 4.6 Output

| Artefact | Type | Description |
|----------|------|-------------|
| `analysis_report` | `AnalysisReport` | The complete analysis of the user request. |

---

## 5. Engine 02 — Intent Parser Engine

### 5.1 Overview

| Property | Value |
|----------|-------|
| **Specification** | 005 |
| **Priority** | 20 |
| **Dependencies** | `["analyzer"]` |
| **Output Artefact** | `intent` |
| **Tags** | `["intent", "parsing", "structured"]` |

The **Intent Parser Engine** parses the natural-language request into a
structured intent dictionary. It classifies the bot type, detects features,
and identifies the language.

### 5.2 Bot Type Classification Rules

The engine classifies the request into a bot type (e.g., store, support,
game, assistant) based on keywords and patterns.

### 5.3 Feature Detection

The engine detects features the bot should have based on the request text.

### 5.4 Language Detection

The engine detects the primary language of the request (Arabic, English, or
mixed).

### 5.5 Output

| Artefact | Type | Description |
|----------|------|-------------|
| `intent` | `dict` | Structured intent with bot type, features, and language. |

---

## 6. Engine 03 — Blueprint Composer Engine

### 6.1 Overview

| Property | Value |
|----------|-------|
| **Specification** | 005 |
| **Priority** | 30 |
| **Dependencies** | `["analyzer", "intent_parser"]` |
| **Output Artefact** | `blueprint` (draft) |
| **Tags** | `["blueprint", "composition", "profiles"]` |

The **Blueprint Composer Engine** composes a draft blueprint from the
structured intent using bot-type profiles. This is the first pass; the
Project Planner (Engine 04) will build the full blueprint.

### 6.2 Bot-Type Profiles

The engine uses bot-type profiles to determine the default structure,
features, and dependencies for each bot type.

### 6.3 Arabic Slugification

The engine handles Arabic text by slugifying it into ASCII-safe names.

### 6.4 Default Dependencies

Each bot-type profile includes default dependencies (e.g., a store bot
defaults to SQLite, a support bot defaults to a FAQ system).

### 6.5 Output

| Artefact | Type | Description |
|----------|------|-------------|
| `blueprint` | `Blueprint` | A draft blueprint with bot type, features, and default dependencies. |

---

## 7. Engine 04 — Project Planning Engine

### 7.1 Overview

| Property | Value |
|----------|-------|
| **Specification** | 004 |
| **Priority** | 40 |
| **Dependencies** | `["analyzer"]` |
| **Output Artefact** | `project_blueprint` |
| **Tags** | `["planning", "blueprint", "execution"]` |
| **Tests** | 288/288 ✅ |

The **Project Planning Engine** builds the full `ProjectBlueprint` from the
`AnalysisReport`. It creates features, a dependency graph, an 8-phase
execution plan, and risk detection.

### 7.2 Internal Steps

1. Read the `AnalysisReport` from the context.
2. Create `FeatureUnit` objects for each feature.
3. Build a `DependencyGraph` with topological sort.
4. Create an `ExecutionPlan` with 8 phases.
5. Detect risks using `RiskDetector`.
6. Validate the blueprint using `BlueprintValidator`.
7. Assemble the `ProjectBlueprint`.
8. Return `ok({"project_blueprint": blueprint})`.

### 7.3 The Eight Execution Phases

| Phase | Name | Description |
|-------|------|-------------|
| 1 | Scaffolding | Create folder structure and `__init__.py` files. |
| 2 | Core | Write `main.py` — the bot entry point. |
| 3 | Handlers | Write command and message handlers. |
| 4 | Conversations | Write conversation/state machine handlers. |
| 5 | Database | Write database models and session. |
| 6 | Middleware | Write middleware components. |
| 7 | Config | Write `config.py` and `.env.example`. |
| 8 | Deployment | Write `Dockerfile`, `docker-compose.yml`, `README.md`. |

### 7.4 Data Model (ProjectBlueprint)

The `ProjectBlueprint` contains:

- `features` — list of `FeatureUnit` objects.
- `dependency_graph` — `DependencyGraph` with topological sort.
- `execution_plan` — `ExecutionPlan` with 8 phases.
- `risks` — list of detected risks.
- `metadata` — blueprint metadata (name, version, timestamp).

### 7.5 Sub-Modules

| File | Responsibility |
|------|----------------|
| `blueprint.py` | `ProjectBlueprint` and sub-dataclasses. |
| `feature_unit.py` | `FeatureUnit` + priority constants. |
| `dependency_graph.py` | `DependencyGraph` with topological sort. |
| `execution_plan.py` | 8-phase `ExecutionPlan`. |
| `risk_detection.py` | `RiskDetector`. |
| `validation.py` | `BlueprintValidator`. |
| `planning_engine.py` | `ProjectPlanningEngine`. |

### 7.6 Priority Constants

Feature priorities are defined as constants:

- `PRIORITY_CRITICAL` — must-have features.
- `PRIORITY_HIGH` — important features.
- `PRIORITY_MEDIUM` — nice-to-have features.
- `PRIORITY_LOW` — optional features.

### 7.7 Output

| Artefact | Type | Description |
|----------|------|-------------|
| `project_blueprint` | `ProjectBlueprint` | Full blueprint with features, dependency graph, execution plan, and risks. |

---

## 8. Engine 05 — Blueprint Validator Engine

### 8.1 Overview

| Property | Value |
|----------|-------|
| **Specification** | 004 |
| **Priority** | 50 |
| **Dependencies** | `["project_planner"]` |
| **Output Artefact** | `validation_report` |
| **Tags** | `["validation", "blueprint", "quality"]` |
| **Tests** | 27/27 ✅ |

The **Blueprint Validator Engine** validates the blueprint across **6
layers**. It checks basic data, features, relationships, the execution plan,
dependencies, and buildability.

### 8.2 The Six Validation Layers

| Layer | File | Responsibility |
|-------|------|----------------|
| 1 | `layer1_basic_data.py` | Checks for missing or empty fields. |
| 2 | `layer2_features.py` | Validates feature definitions. |
| 3 | `layer3_relationships.py` | Checks relationship integrity. |
| 4 | `layer4_execution_plan.py` | Validates the plan phases. |
| 5 | `layer5_dependencies.py` | Checks dependency graph consistency. |
| 6 | `layer6_buildability.py` | Assesses whether the project can be built. |

### 8.3 Conflict Detection

The `ConflictDetector` detects conflicts between features (e.g., two features
requiring incompatible technologies).

### 8.4 Quality Scoring

The `QualityScorer` scores the blueprint quality on a scale from 0 to 100.

### 8.5 Approval Rules

The validation report can be:
- **Approved** — all layers passed, quality score above threshold.
- **Approved with warnings** — all layers passed, but with warnings.
- **Rejected** — one or more layers failed.

### 8.6 Constants

| Constant | Description |
|----------|-------------|
| `APPROVAL_APPROVED` | The blueprint is approved. |
| `APPROVAL_WARNINGS` | Approved with warnings. |
| `APPROVAL_REJECTED` | The blueprint is rejected. |

### 8.7 Data Model (BlueprintValidationReport)

The `BlueprintValidationReport` contains:
- Layer results (pass/fail/warning for each layer).
- Conflicts detected.
- Quality score.
- Approval status.

### 8.8 Output

| Artefact | Type | Description |
|----------|------|-------------|
| `validation_report` | `BlueprintValidationReport` | Validation results across 6 layers. |

---

## 9. Engine 06 — Structure Generation Engine

### 9.1 Overview

| Property | Value |
|----------|-------|
| **Specification** | 006 |
| **Priority** | 60 |
| **Dependencies** | `["blueprint_validator"]` |
| **Output Artefact** | `structure_map` |
| **Tags** | `["structure", "folders", "files"]` |
| **Tests** | 61/61 ✅ |

The **Structure Generation Engine** generates the complete project folder and
file structure map. It plans the folder hierarchy, the file layout, and the
naming conventions. It produces a `ProjectStructureMap` but does not create
any files on disk.

### 9.2 Internal Steps

1. Read the blueprint and validation report.
2. Plan the folder hierarchy using `FolderPlanner`.
3. Plan the file layout using `FilePlanner`.
4. Apply naming conventions using `NamingEngine`.
5. Validate the structure using `StructureValidator`.
6. Assemble the `ProjectStructureMap`.

### 9.3 Sub-Modules

| File | Responsibility |
|------|----------------|
| `folder_planner.py` | Plans the folder hierarchy. |
| `file_planner.py` | Plans the file layout. |
| `naming_engine.py` | Applies naming conventions. |
| `structure_validator.py` | Validates the structure. |
| `structure_map.py` | `ProjectStructureMap` data model. |
| `structure_generation_engine.py` | `StructureGenerationEngine`. |

### 9.4 Data Model (ProjectStructureMap)

The `ProjectStructureMap` contains:
- Folders (hierarchy with paths).
- Files (with paths, types, and content descriptions).
- Naming conventions applied.

### 9.5 Output

| Artefact | Type | Description |
|----------|------|-------------|
| `structure_map` | `ProjectStructureMap` | Complete folder and file structure. |

---

## 10. Engine 07 — Component Detection Engine

### 10.1 Overview

| Property | Value |
|----------|-------|
| **Specification** | 007 |
| **Priority** | 70 |
| **Dependencies** | `["structure_generator"]` |
| **Output Artefact** | `component_registry` |
| **Tags** | `["components", "detection", "registry"]` |

The **Component Detection Engine** scans the blueprint and structure map to
detect every software component. It produces a `ComponentRegistry` with
component types, responsibilities, relations, build order, and quality
validation. It does not write code.

### 10.2 Internal Steps

1. Detect component types using `TypeDetector`.
2. Analyse relations using `RelationAnalyzer`.
3. Compute build order using `BuildOrderComputer`.
4. Check compatibility using `CompatibilityChecker`.
5. Detect duplicates using `DuplicateDetector`.
6. Validate responsibilities using `ResponsibilityValidator`.
7. Check scalability using `ScalabilityChecker`.
8. Validate quality using `QualityValidator`.
9. Assemble the `ComponentRegistry`.

### 10.3 Sub-Modules

| File | Responsibility |
|------|----------------|
| `type_detector.py` | Detects component types. |
| `relation_analyzer.py` | Analyses component relations. |
| `build_order_computer.py` | Computes build order. |
| `compatibility_checker.py` | Checks component compatibility. |
| `duplicate_detector.py` | Detects duplicate components. |
| `responsibility_validator.py` | Validates component responsibilities. |
| `scalability_checker.py` | Checks scalability. |
| `quality_validator.py` | Validates quality. |
| `registry.py` | `ComponentRegistry` data model. |
| `detection_engine.py` | `ComponentDetectionEngine`. |

### 10.4 Output

| Artefact | Type | Description |
|----------|------|-------------|
| `component_registry` | `ComponentRegistry` | All detected components with types, relations, and build order. |

---

## 11. Engine 08 — File Generation Planning Engine

### 11.1 Overview

| Property | Value |
|----------|-------|
| **Specification** | 008 |
| **Priority** | 80 |
| **Dependencies** | `["component_detector"]` |
| **Output Artefact** | `file_generation_plan` |
| **Tags** | `["files", "planning", "generation"]` |
| **Tests** | 78/78 ✅ |

The **File Generation Planning Engine** plans every file the project will
contain before any file is created on disk. It reads the blueprint, validation
report, structure map, and component registry, and produces a
`FileGenerationPlan`. It does not write code.

### 11.2 Internal Steps

1. Analyse components using `ComponentAnalyzer`.
2. Determine files using `FileDeterminer`.
3. Resolve relationships using `RelationshipResolver`.
4. Compute generation order using `GenerationOrderComputer`.
5. Detect conflicts using `ConflictDetector`.
6. Validate the plan using `PlanValidator`.
7. Assemble the `FileGenerationPlan`.

### 11.3 Sub-Modules

| File | Responsibility |
|------|----------------|
| `component_analyzer.py` | Analyses components for file planning. |
| `file_determiner.py` | Determines which files to create. |
| `relationship_resolver.py` | Resolves file relationships. |
| `generation_order_computer.py` | Computes the file generation order. |
| `conflict_detector.py` | Detects file conflicts. |
| `plan_validator.py` | Validates the file plan. |
| `plan_data.py` | `FileGenerationPlan` data model. |
| `file_planning_engine.py` | `FileGenerationPlanningEngine`. |

### 11.4 Output

| Artefact | Type | Description |
|----------|------|-------------|
| `file_generation_plan` | `FileGenerationPlan` | Complete file plan with order, content, and dependencies. |

---

## 12. Engine 09 — Dependency Resolution Engine

### 12.1 Overview

| Property | Value |
|----------|-------|
| **Specification** | 009 |
| **Priority** | 95 |
| **Dependencies** | `["file_planner"]` |
| **Output Artefact** | `dependency_resolution_report` |
| **Tags** | `["dependencies", "resolution", "libraries"]` |
| **Tests** | 99/99 ✅ |

The **Dependency Resolution Engine** builds the complete dependency map for
the project. It reads the blueprint, validation report, structure map,
component registry, and file generation plan, and produces a
`DependencyResolutionReport`. It determines required libraries, checks
compatibility, detects conflicts, optimises the dependency tree, and checks
security. It does not write code, create files, or install libraries.

> **Note:** The original Spec 009 referred to a PDFX Visual Page
> Reconstruction Engine. That engine was removed because it was added by
> mistake. The Spec 009 slot is now occupied by the Dependency Resolution
> Engine.

### 12.2 Internal Steps

1. Analyse components using `ComponentAnalyzer`.
2. Build the dependency graph using `DependencyGraphBuilder`.
3. Determine libraries using `LibraryDeterminer`.
4. Check compatibility using `CompatibilityChecker`.
5. Detect conflicts using `ConflictDetector`.
6. Optimise the dependency tree using `Optimizer`.
7. Validate the plan using `PlanValidator`.
8. Check security using `SecurityChecker`.
9. Assemble the `DependencyResolutionReport`.

### 12.3 Sub-Modules

| File | Responsibility |
|------|----------------|
| `component_analyzer.py` | Analyses components for dependency resolution. |
| `dependency_graph_builder.py` | Builds the dependency graph. |
| `library_determiner.py` | Determines required libraries. |
| `compatibility_checker.py` | Checks library compatibility. |
| `conflict_detector.py` | Detects dependency conflicts. |
| `optimizer.py` | Optimises the dependency tree. |
| `plan_validator.py` | Validates the dependency plan. |
| `security_checker.py` | Checks dependency security. |
| `report_data.py` | `DependencyResolutionReport` data model. |
| `dependency_resolution_engine.py` | `DependencyResolutionEngine`. |

### 12.4 Output

| Artefact | Type | Description |
|----------|------|-------------|
| `dependency_resolution_report` | `DependencyResolutionReport` | Complete dependency map with libraries, compatibility, and security. |

---

## 13. Engine 10 — Project Context Engine

### 13.1 Overview

| Property | Value |
|----------|-------|
| **Specification** | 010 |
| **Priority** | 96 |
| **Dependencies** | `["dependency_resolver"]` |
| **Output Artefact** | `project_context` |
| **Tags** | `["context", "unification", "indices"]` |
| **Tests** | 125/125 ✅ |

The **Project Context Engine** builds the complete, unified project context by
merging the Project Blueprint, Blueprint Validation Report, Project Structure
Map, Component Registry, File Generation Plan, and Dependency Resolution
Report. It produces a `ProjectContext` artefact with precomputed O(1) look-up
indices.

### 13.2 Internal Steps

1. Read the blueprint using `BlueprintReader`.
2. Read the validation report using `ValidationReader`.
3. Read the structure map using `StructureReader`.
4. Read the component registry using `RegistryReader`.
5. Read the file plan using `FilePlanReader`.
6. Read the dependency report using `DependencyReader`.
7. Assemble the context using `ContextAssembler`.
8. Link components using `ContextLinker`.
9. Validate the context using `ContextValidator`.
10. Assemble the `ProjectContext`.

### 13.3 Sub-Modules

| File | Responsibility |
|------|----------------|
| `blueprint_reader.py` | Reads the project blueprint. |
| `validation_reader.py` | Reads the validation report. |
| `structure_reader.py` | Reads the structure map. |
| `registry_reader.py` | Reads the component registry. |
| `file_plan_reader.py` | Reads the file generation plan. |
| `dependency_reader.py` | Reads the dependency report. |
| `context_assembler.py` | Assembles the unified context. |
| `context_linker.py` | Links components in the context. |
| `context_validator.py` | Validates the context. |
| `context_data.py` | `ProjectContext` data model. |
| `project_context_engine.py` | `ProjectContextEngine`. |

### 13.4 Output

| Artefact | Type | Description |
|----------|------|-------------|
| `project_context` | `ProjectContext` | Unified context with O(1) look-up indices. |

---

## 14. Engine 11 — Intelligence Graph Engine

### 14.1 Overview

| Property | Value |
|----------|-------|
| **Specification** | 011 |
| **Priority** | 97 |
| **Dependencies** | `["project_context"]` |
| **Output Artefact** | `intelligence_graph` |
| **Tags** | `["graph", "intelligence", "navigation"]` |
| **Tests** | 127/127 ✅ |

The **Intelligence Graph Engine** converts the seven upstream artefacts into a
single `ProjectIntelligenceGraph` with **19 node types** and **12 edge
kinds**. It produces O(1) look-up indices for fast navigation and detects
circular dependencies, broken references, unused components, orphan files, and
dead components.

### 14.2 Internal Steps

1. Build the graph using `GraphBuilder`.
2. Validate the graph using `GraphValidator`.
3. Detect circular dependencies using `CircularDetector`.
4. Build navigation indices using `GraphNavigator`.
5. Assemble the `ProjectIntelligenceGraph`.

### 14.3 Sub-Modules

| File | Responsibility |
|------|----------------|
| `graph_builder.py` | Builds the intelligence graph. |
| `graph_validator.py` | Validates the graph. |
| `circular_detector.py` | Detects circular dependencies. |
| `graph_navigator.py` | Builds O(1) navigation indices. |
| `graph_data.py` | `ProjectIntelligenceGraph` data model (19 node types, 12 edge kinds). |
| `intelligence_graph_engine.py` | `IntelligenceGraphEngine`. |

### 14.4 Output

| Artefact | Type | Description |
|----------|------|-------------|
| `intelligence_graph` | `ProjectIntelligenceGraph` | Complete graph with 19 node types, 12 edge kinds, and O(1) look-up indices. |

---

## 15. Engine 12 — Requirement Intelligence Engine

### 15.1 Overview

| Property | Value |
|----------|-------|
| **Specification** | 012 |
| **Priority** | 98 |
| **Dependencies** | `["intelligence_graph"]` |
| **Output Artefact** | `requirement_intelligence_report` |
| **Tags** | `["requirements", "intelligence", "intent"]` |
| **Tests** | 103/103 ✅ |

The **Requirement Intelligence Engine** understands the user's request with
the highest possible precision and converts it into a precise set of
engineering requirements. It reads four data sources (user request, project
context, intelligence graph, and knowledge base), performs intent analysis
across five dimensions, classifies requirements into nine categories, detects
missing information, ambiguity points, and conflicts, assigns priorities,
validates quality, and produces a `RequirementIntelligenceReport`.

### 15.2 The Five Intent Dimensions

| Dimension | Description |
|-----------|-------------|
| Wants | What the user wants to achieve. |
| Does Not Want | What the user explicitly excludes. |
| Final Goal | The ultimate objective. |
| Quality Level | The expected quality/complexity. |
| Confidence | The confidence in the understanding. |

### 15.3 The Nine Requirement Categories

1. Functional — what the bot should do.
2. Non-functional — performance, security, usability.
3. Technical — specific technologies.
4. Business — business rules and constraints.
5. User — user-facing requirements.
6. Integration — third-party integrations.
7. Data — database and data requirements.
8. Security — security requirements.
9. Deployment — deployment and infrastructure.

### 15.4 Internal Steps

1. Read the user request using `RequestReader`.
2. Read the project context using `ContextReader`.
3. Read the intelligence graph using `GraphReader`.
4. Read the knowledge base using `KnowledgeReader`.
5. Perform intent analysis using `IntentAnalyzer`.
6. Classify requirements using `RequirementClassifier`.
7. Detect missing information using `MissingDetector`.
8. Detect conflicts using `ConflictDetector`.
9. Assign priorities using `PriorityAssigner`.
10. Validate quality using `QualityValidator`.
11. Assemble the `RequirementIntelligenceReport` using `ReportAssembler`.

### 15.5 Sub-Modules

| File | Responsibility |
|------|----------------|
| `request_reader.py` | Reads the user request. |
| `context_reader.py` | Reads the project context. |
| `graph_reader.py` | Reads the intelligence graph. |
| `knowledge_reader.py` | Reads the knowledge base. |
| `intent_analyzer.py` | Performs intent analysis across 5 dimensions. |
| `requirement_classifier.py` | Classifies requirements into 9 categories. |
| `missing_detector.py` | Detects missing information. |
| `conflict_detector.py` | Detects conflicts. |
| `priority_assigner.py` | Assigns priorities. |
| `quality_validator.py` | Validates quality. |
| `report_assembler.py` | Assembles the report. |
| `report_data.py` | `RequirementIntelligenceReport` data model. |
| `requirement_intelligence_engine.py` | `RequirementIntelligenceEngine`. |

### 15.6 Data Model (RequirementIntelligenceReport)

The `RequirementIntelligenceReport` contains:
- `intent_wants` — what the user wants.
- `intent_does_not_want` — what the user does not want.
- `final_goal` — the ultimate objective.
- `quality_level` — the expected quality.
- `intent_confidence` — the confidence in the understanding.
- `requirements` — list of `RawRequirement` objects.
- `required_questions` — questions that need clarification.
- `ambiguities` — detected ambiguity points.
- `conflicts` — detected conflicts.
- `summary` — a summary of the analysis.
- `ready` — whether the requirements are ready for the next stage.

### 15.7 Output

| Artefact | Type | Description |
|----------|------|-------------|
| `requirement_intelligence_report` | `RequirementIntelligenceReport` | Precise engineering requirements with intent, categories, and conflicts. |

---

## 16. Engine 13 — Semantic Understanding Engine

### 16.1 Overview

| Property | Value |
|----------|-------|
| **Specification** | 013 |
| **Priority** | 99 |
| **Dependencies** | `["requirement_intelligence"]` |
| **Output Artefact** | `semantic_understanding_report` |
| **Tags** | `["semantic", "understanding", "meaning"]` |
| **Tests** | 76/76 ✅ |

The **Semantic Understanding Engine** understands the TRUE meaning of the
user's request — not just keywords, but intent, context, and meaning. It reads
five data sources (user request, requirement intelligence report, project
context, knowledge base, and built-in language rules), performs full sentence
analysis (dialect normalization, spell correction, abbreviation expansion,
synonym resolution), extracts the true intent, maps all variations to a
unified intent, detects ambiguities and requests clarification, understands
relationships between the parts of the request, calculates a confidence score,
and produces a `SemanticUnderstandingReport`.

### 16.2 Internal Steps

1. Read the user request using `RequestReader`.
2. Read the requirement intelligence report using `RequirementReportReader`.
3. Read the project context using `ContextReader`.
4. Read the knowledge base using `KnowledgeReader`.
5. Load language rules using `LanguageRules`.
6. Analyse sentences using `SentenceAnalyzer`.
7. Normalize dialects using `DialectNormalizer`.
8. Correct spelling using `SpellCorrector`.
9. Expand abbreviations using `AbbreviationExpander`.
10. Resolve synonyms using `SynonymResolver`.
11. Extract the true intent using `IntentExtractor`.
12. Map intent variations using `IntentMapper`.
13. Detect ambiguities using `AmbiguityDetector`.
14. Apply context awareness using `ContextAwareness`.
15. Calculate confidence using `ConfidenceCalculator`.
16. Validate quality using `QualityGate`.
17. Assemble the `SemanticUnderstandingReport` using `ReportAssembler`.

### 16.3 Sub-Modules

| File | Responsibility |
|------|----------------|
| `request_reader.py` | Reads the user request. |
| `requirement_report_reader.py` | Reads the requirement intelligence report. |
| `context_reader.py` | Reads the project context. |
| `knowledge_reader.py` | Reads the knowledge base. |
| `language_rules.py` | Built-in language rules. |
| `sentence_analyzer.py` | Analyses sentences. |
| `dialect_normalizer.py` | Normalizes dialects. |
| `spell_corrector.py` | Corrects spelling. |
| `abbreviation_expander.py` | Expands abbreviations. |
| `synonym_resolver.py` | Resolves synonyms. |
| `intent_extractor.py` | Extracts the true intent. |
| `intent_mapper.py` | Maps intent variations to a unified intent. |
| `ambiguity_detector.py` | Detects ambiguities. |
| `context_awareness.py` | Applies context awareness. |
| `confidence_calculator.py` | Calculates confidence score. |
| `quality_gate.py` | Validates quality. |
| `report_assembler.py` | Assembles the report. |
| `report_data.py` | `SemanticUnderstandingReport` data model. |
| `semantic_understanding_engine.py` | `SemanticUnderstandingEngine`. |

### 16.4 Output

| Artefact | Type | Description |
|----------|------|-------------|
| `semantic_understanding_report` | `SemanticUnderstandingReport` | The true meaning of the request with unified intent and confidence. |

---

## 17. Engine 14 — Requirement Normalization Engine

### 17.1 Overview

| Property | Value |
|----------|-------|
| **Specification** | 014 |
| **Priority** | 100 |
| **Dependencies** | `["semantic_understanding"]` |
| **Output Artefact** | `normalization_report` |
| **Tags** | `["normalization", "canonical", "unification"]` |
| **Tests** | 103/103 ✅ |

The **Requirement Normalization Engine** transforms ALL user requirements into
a unified, canonical model that every downstream engine can understand. It
reads five data sources (user request, requirement intelligence report,
semantic understanding report, project context, and knowledge base), unifies
all names into canonical snake_case keys, unifies all terminology into a
single vocabulary, removes duplicates using Jaccard similarity, validates
consistency (detecting conflicts, terminology variations, and lost
requirements), links each requirement to its feature, component, priority,
dependencies, and expected output, caches the normalized model for
re-normalization, enforces quality rules, and produces a `NormalizationReport`.

### 17.2 The 14-Step Execute Method

1. Read the user request using `RequestReader`.
2. Read the requirement intelligence report using `RequirementIntelligenceReader`.
3. Read the semantic understanding report using `SemanticUnderstandingReader`.
4. Read the project context using `ContextReader`.
5. Read the knowledge base using `KnowledgeReader`.
6. Normalize names into canonical snake_case using `NameNormalizer`.
7. Normalize terminology into a single vocabulary using `TerminologyNormalizer`.
8. Remove duplicates using `DeduplicationRemover` (Jaccard similarity, threshold 0.85).
9. Validate consistency using `ConsistencyValidator`.
10. Link requirements to features, components, priorities, dependencies, and expected output using `RequirementLinker`.
11. Get cache info using `CacheManager`.
12. Validate quality using `QualityGate`.
13. Calculate confidence and confidence level.
14. Assemble the `NormalizationReport` using `ReportAssembler`.

### 17.3 Deduplication (Jaccard Similarity)

The `DeduplicationRemover` uses Jaccard similarity to detect duplicate
requirements. The similarity weights are:

| Component | Weight |
|-----------|--------|
| Name | 40% |
| Description | 40% |
| Category | 20% |

The similarity threshold is **0.85** — if two requirements have a Jaccard
similarity above 0.85, the second one is considered a duplicate and removed.

### 17.4 Sub-Modules

| File | Responsibility |
|------|----------------|
| `request_reader.py` | Reads the user request. |
| `requirement_intelligence_reader.py` | Reads the requirement intelligence report. |
| `semantic_understanding_reader.py` | Reads the semantic understanding report. |
| `context_reader.py` | Reads the project context. |
| `knowledge_reader.py` | Reads the knowledge base. |
| `name_normalizer.py` | Normalizes names into canonical snake_case. |
| `terminology_normalizer.py` | Normalizes terminology into a single vocabulary. |
| `deduplication_remover.py` | Removes duplicates using Jaccard similarity. |
| `consistency_validator.py` | Validates consistency (conflicts, terminology, lost requirements). |
| `requirement_linker.py` | Links requirements to features, components, priorities, dependencies, expected output. |
| `cache_manager.py` | Caches the normalized model (SHA-256 hash key). |
| `quality_gate.py` | Validates quality. |
| `report_assembler.py` | Assembles the `NormalizationReport`. Also has `build_notes()` and `build_provenance()`. |
| `report_data.py` | All constants and dataclasses. |
| `requirement_normalization_engine.py` | `RequirementNormalizationEngine`. |

### 17.5 Data Model (NormalizationReport)

The `NormalizationReport` contains:
- `requirements` — list of `NormalizedRequirement` objects (canonical model).
- `canonical_names` — list of `CanonicalName` objects.
- `terminology_mappings` — list of `TerminologyMapping` objects.
- `links` — list of `RequirementLink` objects.
- `duplicates` — list of `DuplicateRecord` objects.
- `conflicts` — list of `ConflictRecord` objects.
- `cache_info` — cache information (hit/miss, size).
- `findings` — list of `NormalizationFinding` objects.
- `confidence` — confidence score (float).
- `confidence_level` — confidence level (string).
- `original_request` — the original user request.
- `normalized_request` — the normalized request text.
- `provenance` — traceability information.
- `notes` — additional notes.

### 17.6 Output

| Artefact | Type | Description |
|----------|------|-------------|
| `normalization_report` | `NormalizationReport` | Unified, canonical model with normalized names, terminology, deduplication, consistency, and links. |

---

## 18. Pipeline Architecture & Data Flow

### 18.1 Engine Execution Order

| # | Engine ID | Priority | Dependencies | Output Artefact |
|---|-----------|----------|-------------|-----------------|
| 1 | `analyzer` | 10 | `[]` | `analysis_report` |
| 2 | `intent_parser` | 20 | `["analyzer"]` | `intent` |
| 3 | `blueprint_composer` | 30 | `["analyzer", "intent_parser"]` | `blueprint` (draft) |
| 4 | `project_planner` | 40 | `["analyzer"]` | `project_blueprint` |
| 5 | `blueprint_validator` | 50 | `["project_planner"]` | `validation_report` |
| 6 | `structure_generator` | 60 | `["blueprint_validator"]` | `structure_map` |
| 7 | `component_detector` | 70 | `["structure_generator"]` | `component_registry` |
| 8 | `file_planner` | 80 | `["component_detector"]` | `file_generation_plan` |
| 9 | `dependency_resolver` | 95 | `["file_planner"]` | `dependency_resolution_report` |
| 10 | `project_context` | 96 | `["dependency_resolver"]` | `project_context` |
| 11 | `intelligence_graph` | 97 | `["project_context"]` | `intelligence_graph` |
| 12 | `requirement_intelligence` | 98 | `["intelligence_graph"]` | `requirement_intelligence_report` |
| 13 | `semantic_understanding` | 99 | `["requirement_intelligence"]` | `semantic_understanding_report` |
| 14 | `requirement_normalization` | 100 | `["semantic_understanding"]` | `normalization_report` |

### 18.2 Artefact Flow Diagram

```
User Request
    │
    ▼
[Engine 01: Analyzer] ──────────── → analysis_report
    │
    ▼
[Engine 02: Intent Parser] ─────── → intent
    │
    ▼
[Engine 03: Blueprint Composer] ── → blueprint (draft)
    │
    ▼
[Engine 04: Project Planner] ───── → project_blueprint
    │
    ▼
[Engine 05: Blueprint Validator] ─ → validation_report
    │
    ▼
[Engine 06: Structure Generator] ── → structure_map
    │
    ▼
[Engine 07: Component Detector] ── → component_registry
    │
    ▼
[Engine 08: File Planner] ──────── → file_generation_plan
    │
    ▼
[Engine 09: Dependency Resolver] ── → dependency_resolution_report
    │
    ▼
[Engine 10: Project Context] ────── → project_context
    │
    ▼
[Engine 11: Intelligence Graph] ── → intelligence_graph
    │
    ▼
[Engine 12: Requirement Intelligence] → requirement_intelligence_report
    │
    ▼
[Engine 13: Semantic Understanding] → semantic_understanding_report
    │
    ▼
[Engine 14: Requirement Normalization] → normalization_report
    │
    ▼
[Building Phase — future]
```

### 18.3 The GenerationContext as the Communication Bus

All engines read from and write to the `GenerationContext`. The context is the
**only** way engines communicate. No engine imports or directly calls another
engine.

### 18.4 The Pipeline Orchestrator

The `PipelineOrchestrator` (in `pipeline/orchestrator.py`) drives the full
pipeline. It is the only place that knows the stage order. It creates a
`GenerationContext`, runs each stage, and handles fail-fast semantics.

---

## 19. Core Engine Manager

### 19.1 Overview

The `CoreEngineManager` (Specification 003) is the executive brain that governs
every engine's lifecycle, dependencies, execution order, and error handling.
It is wired in `core/bootstrap.py` and uses the same engine instances already
registered with the `EngineRegistry`.

| Property | Value |
|----------|-------|
| **Specification** | 003 |
| **Tests** | 53/53 ✅ |
| **Engines managed** | 14 |

### 19.2 Lifecycle States

```
Registered → Loaded → Initialized → Ready → Running → Completed
                                                   └→ Failed
```

| State | Description |
|-------|-------------|
| `Registered` | The engine has been registered with the manager. |
| `Loaded` | The engine's code has been loaded. |
| `Initialized` | The engine's `initialize()` method has been called. |
| `Ready` | The engine is ready to run. |
| `Running` | The engine is currently executing. |
| `Completed` | The engine finished successfully. |
| `Failed` | The engine failed (terminal state). |

### 19.3 Manager vs Registry

| Component | Role |
|-----------|------|
| `EngineRegistry` | Dumb container — maps names to component instances. No logic. |
| `CoreEngineManager` | Executive brain — lifecycle, dependencies, execution queue, security. |

### 19.4 Manager Sub-Modules

| File | Responsibility |
|------|----------------|
| `engine_manager.py` | `CoreEngineManager` — the executive brain. |
| `engine_entry.py` | `EngineEntry` — metadata for each registered engine. |
| `execution_queue.py` | Builds the ordered execution queue. |
| `lifecycle.py` | Enforces lifecycle state transitions. |
| `errors.py` | Manager-specific exceptions. |

### 19.5 Security Rules

- Only registered engines can run.
- Only enabled engines can run.
- Unknown engines raise `UnknownEngineError`.
- Lifecycle transitions are enforced — no skipping states.
- Dependencies must be registered and completed before an engine runs.

---

## 20. Test Suite Summary

### 20.1 Test Files

| File | Tests | Status |
|------|-------|--------|
| `tests/test_manager.py` | 53 | ✅ All pass |
| `tests/test_project_planner.py` | 288 | ✅ All pass |
| `tests/test_blueprint_validator.py` | 27 | ✅ All pass |
| `tests/test_structure_generator.py` | 61 | ✅ All pass |
| `tests/test_file_planner.py` | 78 | ✅ All pass |
| `tests/test_dependency_resolver.py` | 99 | ✅ All pass |
| `tests/test_project_context.py` | 125 | ✅ All pass |
| `tests/test_intelligence_graph.py` | 127 | ✅ All pass |
| `tests/test_requirement_intelligence.py` | 103 | ✅ All pass |
| `tests/test_semantic_understanding.py` | 76 | ✅ All pass |
| `tests/test_requirement_normalization.py` | 103 | ✅ All pass |

### 20.2 Test Coverage

**Total: 1,140+ tests across 11 test suites, all passing.**

Each test suite covers:
- Data model construction and validation.
- Reader tolerant behaviour (missing data → `available=False`).
- Helper/processor logic (normalization, classification, detection).
- Quality gate / quality validator behaviour.
- Report assembler output structure.
- Bootstrap registration and priority/dependency enforcement.

---

## 21. Technology Stack

### 21.1 Programming Language

| Property | Value |
|----------|-------|
| **Language** | Python 3.11+ |
| **Type hints** | Used throughout |
| **Dataclasses** | Used for all data models |

### 21.2 Libraries and Frameworks

The engine is **dependency-free** — it uses only the Python standard library.
No external packages are required for the understanding phase.

### 21.3 Design Patterns and Techniques

| Pattern | Description |
|---------|-------------|
| Engine-per-Responsibility | Each engine has one job. |
| Context-Only Communication | Engines communicate only through `GenerationContext`. |
| Tolerant Readers | Readers return `available=False` when data is missing. |
| BaseEngine Pattern | All engines inherit from `BaseEngine` with `ok()`/`failed()`. |
| Quality Gates | Each engine has a quality gate that can block on errors. |
| Bootstrap Registration | All engines registered in `core/bootstrap.py`. |
| CacheManager | SHA-256 hash for cache key computation (Spec 014). |
| Jaccard Similarity | Deduplication using weighted Jaccard similarity (Spec 014). |
| Topological Sort | Dependency graph ordering (Spec 004). |

### 21.4 Error Handling

| Mechanism | Description |
|-----------|-------------|
| `StageResult` | Every engine returns a `StageResult` with success/errors. |
| Fail-Fast | The pipeline stops on the first failure. |
| Tolerant Readers | Missing data → `available=False`, not an exception. |
| `DependencyError` | Raised when dependencies are missing or not completed. |
| `LifecycleError` | Raised on illegal lifecycle transitions. |
| `SecurityError` | Raised on security violations. |

### 21.5 Logging

Every step is logged using the `EngineLogger` facade with structured logging.
Logs include:
- Engine registration and lifecycle transitions.
- Engine start, completion, and failure.
- Dependency validation.
- Execution queue building.
- Managed run start and stop.

---

## 22. Design Principles

### 22.1 Single Responsibility

No file is responsible for everything. Every module has a single, clearly
defined job.

### 22.2 No Direct Communication

Engines communicate only through `GenerationContext`. No engine imports or
directly calls another engine.

### 22.3 Tolerant Readers

Every reader returns a `*Data` object with `available=False` when the upstream
artefact is missing. This allows the pipeline to continue gracefully.

### 22.4 No Code Generation Before Planning

No code is generated before the complete plan is built and validated. The
understanding phase (Engines 1–14) produces only plans, reports, and models.

### 22.5 Traceability

Every artefact has provenance information. The `ReportAssembler` in Engine 14
includes `build_provenance()` to track the origin of each piece of data.

### 22.6 Fail-Fast

The pipeline stops on the first failure. No subsequent engines are run.

### 22.7 Deterministic Execution Order

Engines run in a fixed order determined by priority and dependencies. Same
input always produces the same output.

### 22.8 Read-Only for Downstream

No engine modifies another engine's output. If post-processing is needed, a
dedicated engine is required.

### 22.9 Scalability

New engines can be added by creating a new directory in `engines/generators/`
and registering in `core/bootstrap.py`. No other file changes needed.

### 22.10 Testability

Each engine is tested independently with its own test suite. The test suites
cover data models, readers, helpers, quality gates, and bootstrap.

### 22.11 Arabic Language Support

The engine handles Arabic text normalization, slugification, and dialect
differences. This is critical for the target audience.

---

## 23. Project Statistics

### 23.1 Code Statistics

| Metric | Value |
|--------|-------|
| **Python files** | 192 (engine) + 12 (tests) |
| **Directories** | 29 |
| **Engines** | 14 |
| **Test suites** | 11 |
| **Total tests** | 1,140+ |
| **Specifications implemented** | 001–014 |

### 23.2 Per-Engine Statistics

| Engine | ID | Priority | Files | Tests | Output |
|--------|----|----------|-------|-------|--------|
| Analyzer | `analyzer` | 10 | 13 | 6 stages | `analysis_report` |
| Intent Parser | `intent_parser` | 20 | 1 | — | `intent` |
| Blueprint Composer | `blueprint_composer` | 30 | 1 | — | `blueprint` (draft) |
| Project Planner | `project_planner` | 40 | 8 | 288 | `project_blueprint` |
| Blueprint Validator | `blueprint_validator` | 50 | 10 | 27 | `validation_report` |
| Structure Generator | `structure_generator` | 60 | 7 | 61 | `structure_map` |
| Component Detector | `component_detector` | 70 | 11 | — | `component_registry` |
| File Planner | `file_planner` | 80 | 9 | 78 | `file_generation_plan` |
| Dependency Resolver | `dependency_resolver` | 95 | 11 | 99 | `dependency_resolution_report` |
| Project Context | `project_context` | 96 | 12 | 125 | `project_context` |
| Intelligence Graph | `intelligence_graph` | 97 | 6 | 127 | `intelligence_graph` |
| Requirement Intelligence | `requirement_intelligence` | 98 | 14 | 103 | `requirement_intelligence_report` |
| Semantic Understanding | `semantic_understanding` | 99 | 19 | 76 | `semantic_understanding_report` |
| Requirement Normalization | `requirement_normalization` | 100 | 16 | 103 | `normalization_report` |

### 23.3 Data Model Class Count

Each engine has its own data model with dataclasses:

| Engine | Key Dataclasses |
|--------|----------------|
| Analyzer | `AnalysisReport` |
| Intent Parser | (dict-based) |
| Blueprint Composer | `Blueprint`, `BotMeta`, `CommandSpec`, `HandlerSpec`, etc. |
| Project Planner | `ProjectBlueprint`, `FeatureUnit`, `DependencyGraph`, `ExecutionPlan` |
| Blueprint Validator | `BlueprintValidationReport` |
| Structure Generator | `ProjectStructureMap` |
| Component Detector | `ComponentRegistry` |
| File Planner | `FileGenerationPlan` |
| Dependency Resolver | `DependencyResolutionReport` |
| Project Context | `ProjectContext` |
| Intelligence Graph | `ProjectIntelligenceGraph` (19 node types, 12 edge kinds) |
| Requirement Intelligence | `RequirementIntelligenceReport`, `RawRequirement` |
| Semantic Understanding | `SemanticUnderstandingReport` |
| Requirement Normalization | `NormalizationReport`, `NormalizedRequirement`, `CanonicalName`, `TerminologyMapping`, `RequirementLink`, `DuplicateRecord`, `ConflictRecord`, `NormalizationFinding` |

---

## Document Information

| Field | Value |
|-------|-------|
| **Document** | Complete Technical Documentation — All 14 Engines |
| **Project** | AI Agent 7h Bot — Telegram Bot Generation Engine |
| **Specifications** | 001–014 (14 engines) |
| **Last updated** | 2026-07-25 |
| **Status** | Active development — Spec 015 is next |
