# Telegram Bot Generation Engine — Architecture

This document describes the architecture of the **Telegram Bot Generation
Engine**, a modular system that generates complete Telegram bot projects
from a natural-language description.

The engine is **not a bot**. It is a *generation engine* that builds bots. Every
file in the generated project is produced by a chain of independent generation
engines, each with a single responsibility.

---

## 1. Design Principles

### 1.1 One Responsibility Per File

No file is responsible for everything. Every module has a single, clearly
defined job. This makes the system testable, maintainable, and extensible.

### 1.2 No Hardcoded Values

No engine, builder, or validator hardcodes configuration values. All settings
live in the centralised `Configuration` system and are passed to components at
construction time.

### 1.3 No Static Templates

The engine does not copy pre-built projects or use fixed templates. Every file
is generated at run time by a generation engine that reads a structured
blueprint.

### 1.4 Reproducibility

Given the same input and the same engine versions, the engine produces the
same output. Determinism is preserved by sorting, ordered stages, and
explicit metadata.

### 1.5 Independence

Every engine knows nothing about other engines except through the formal
interfaces and the shared `GenerationContext`. Engines communicate only by
reading from and writing to the context.

### 1.6 Tolerant Readers

Every reader returns a `*Data` object with `available=False` when the upstream
artefact is missing. This allows the pipeline to continue gracefully rather
than crashing.

---

## 2. High-Level Architecture

The system has **14 generation engines** organised in a single pipeline. The
pipeline has two logical phases:

1. **Understanding Phase** (Engines 1–14) — the engines parse, understand,
   plan, and normalise the user's request into a complete, canonical model
   that every downstream engine can use.

2. **Building Phase** (future) — generator engines will read the canonical
   model and materialise the project files using builders. Validators check
   the output at each stage.

```
┌──────────────────────────────────────────────────────────────────┐
│                        User Request                              │
│              "I want a Telegram store bot with SQLite"           │
└──────────────────────────┬───────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│                    Pipeline Orchestrator                         │
│         (drives the ordered stages, fail-fast on errors)        │
└──────────────────────────┬───────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│                    UNDERSTANDING PHASE                           │
│                                                                  │
│  ┌─── Engine 1: Analyzer (priority=10)                          │
│  │     10-stage request analyzer → AnalysisReport               │
│  │                                                               │
│  ├─── Engine 2: Intent Parser (priority=20)                     │
│  │     Parses request into structured intent                     │
│  │                                                               │
│  ├─── Engine 3: Blueprint Composer (priority=30)                │
│  │     Composes draft blueprint from intent                      │
│  │                                                               │
│  ├─── Engine 4: Project Planner (priority=40)                   │
│  │     Builds ProjectBlueprint + execution plan + risks         │
│  │                                                               │
│  ├─── Engine 5: Blueprint Validator (priority=50)               │
│  │     6-layer validation of the blueprint                      │
│  │                                                               │
│  ├─── Engine 6: Structure Generator (priority=60)              │
│  │     Generates folder + file structure map                     │
│  │                                                               │
│  ├─── Engine 7: Component Detector (priority=70)               │
│  │     Detects all components → ComponentRegistry                │
│  │                                                               │
│  ├─── Engine 8: File Planner (priority=80)                      │
│  │     Plans every file → FileGenerationPlan                     │
│  │                                                               │
│  ├─── Engine 9: Dependency Resolver (priority=95)               │
│  │     Builds dependency map → DependencyResolutionReport        │
│  │                                                               │
│  ├─── Engine 10: Project Context (priority=96)                  │
│  │     Unifies all artefacts → ProjectContext (O(1) lookups)    │
│  │                                                               │
│  ├─── Engine 11: Intelligence Graph (priority=97)             │
│  │     Converts to graph → ProjectIntelligenceGraph              │
│  │     (19 node types, 12 edge kinds)                           │
│  │                                                               │
│  ├─── Engine 12: Requirement Intelligence (priority=98)        │
│  │     Intent analysis, 9-cat classification, conflicts         │
│  │                                                               │
│  ├─── Engine 13: Semantic Understanding (priority=99)          │
│  │     True meaning: dialect, spell, abbrev, synonyms, intent   │
│  │                                                               │
│  └─── Engine 14: Requirement Normalization (priority=100)      │
│        Canonical model: names, terminology, dedup, links         │
│                                                                  │
└──────────────────────────┬───────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│                     BUILDING PHASE (future)                      │
│   Code generation, file creation, packaging, output              │
└──────────────────────────┬───────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│                     Generated Bot Project (.zip)                 │
└──────────────────────────────────────────────────────────────────┘
```

---

## 3. The 14 Engines in Detail

### 3.1 Analyzer Engine (Specification 002, priority=10)

Parses the user's natural-language request through **10 stages** and produces
an `AnalysisReport`. The stages are:

1. **Cleaner** — normalises whitespace, removes noise.
2. **Segmenter** — splits the request into sentences and phrases.
3. **Keyword Extractor** — extracts keywords from the text.
4. **Classifier** — classifies the bot type (store, support, game, etc.).
5. **Feature Extractor** — identifies features the bot should have.
6. **Technology Extractor** — identifies technologies (database, AI, etc.).
7. **Relationship Analyzer** — analyses relationships between features.
8. **Conflict Detector** — detects conflicting requirements.
9. **Missing Info Detector** — detects missing information.
10. **Report Builder** — assembles the final `AnalysisReport`.

**Directory:** `engines/generators/analyzer/`

### 3.2 Intent Parser Engine (Specification 005, priority=20)

Parses the natural-language request into a structured intent dictionary that
the blueprint composer can use.

**File:** `engines/generators/intent_parser_engine.py`

### 3.3 Blueprint Composer Engine (Specification 005, priority=30)

Composes a draft blueprint from the structured intent using bot-type profiles.
This is the first pass of the blueprint; the Project Planner (Engine 4) will
build the full blueprint.

**File:** `engines/generators/blueprint_composer_engine.py`

### 3.4 Project Planning Engine (Specification 004, priority=40)

Builds the full `ProjectBlueprint` from the `AnalysisReport`. It contains:

- **Blueprint data model** — `ProjectBlueprint`, `FeatureUnit`, etc.
- **Dependency graph** — topological sort of features and components.
- **Execution plan** — 8-phase plan with tasks for each phase.
- **Risk detection** — identifies risks in the blueprint.
- **Validation** — validates the blueprint before it leaves the engine.

**Directory:** `engines/generators/project_planner/`

**Tests:** 288/288 passing.

### 3.5 Blueprint Validator Engine (Specification 004, priority=50)

Validates the blueprint across **6 layers**:

1. Basic data — checks for missing or empty fields.
2. Features — validates feature definitions.
3. Relationships — checks relationship integrity.
4. Execution plan — validates the plan phases.
5. Dependencies — checks dependency graph consistency.
6. Buildability — assesses whether the project can be built.

Also includes a `QualityScorer` that scores the blueprint quality and a
`ConflictDetector` that detects conflicts between features.

**Directory:** `engines/generators/blueprint_validator/`

**Tests:** 27/27 passing.

### 3.6 Structure Generation Engine (Specification 006, priority=60)

Generates the complete project folder and file structure map. It plans the
folder hierarchy, the file layout, and the naming conventions. It produces a
`ProjectStructureMap` but does not create any files on disk.

**Directory:** `engines/generators/structure_generator/`

**Tests:** 61/61 passing.

### 3.7 Component Detection Engine (Specification 007, priority=70)

Scans the blueprint and structure map to detect every software component. It
produces a `ComponentRegistry` with component types, responsibilities,
relations, build order, and quality validation. It does not write code.

**Directory:** `engines/generators/component_detector/`

### 3.8 File Generation Planning Engine (Specification 008, priority=80)

Plans every file the project will contain before any file is created on disk.
It reads the blueprint, validation report, structure map, and component
registry, and produces a `FileGenerationPlan`. It does not write code.

**Directory:** `engines/generators/file_planner/`

**Tests:** 78/78 passing.

### 3.9 Dependency Resolution Engine (Specification 009, priority=95)

Builds the complete dependency map for the project. It reads the blueprint,
validation report, structure map, component registry, and file generation plan,
and produces a `DependencyResolutionReport`. It determines required libraries,
checks compatibility, detects conflicts, optimises the dependency tree, and
checks security. It does not write code, create files, or install libraries.

**Directory:** `engines/generators/dependency_resolver/`

**Tests:** 99/99 passing.

> **Note:** The original Spec 009 referred to a PDFX Visual Page
> Reconstruction Engine. That engine was removed because it was added by
> mistake. The Spec 009 slot is now occupied by the Dependency Resolution
> Engine.

### 3.10 Project Context Engine (Specification 010, priority=96)

Builds the complete, unified project context by merging the Project Blueprint,
Blueprint Validation Report, Project Structure Map, Component Registry, File
Generation Plan, and Dependency Resolution Report. It produces a
`ProjectContext` artefact with precomputed O(1) look-up indices.

**Directory:** `engines/generators/project_context/`

**Tests:** 125/125 passing.

### 3.11 Intelligence Graph Engine (Specification 011, priority=97)

Converts the seven upstream artefacts into a single `ProjectIntelligenceGraph`
with 19 node types and 12 edge kinds. It produces O(1) look-up indices for
fast navigation and detects circular dependencies, broken references, unused
components, orphan files, and dead components.

**Directory:** `engines/generators/intelligence_graph/`

**Tests:** 127/127 passing.

### 3.12 Requirement Intelligence Engine (Specification 012, priority=98)

Understands the user's request with the highest possible precision and converts
it into a precise set of engineering requirements. It reads four data sources
(user request, project context, intelligence graph, and knowledge base),
performs intent analysis across five dimensions, classifies requirements into
nine categories, detects missing information, ambiguity points, and conflicts,
assigns priorities, validates quality, and produces a `RequirementIntelligence
Report`.

**Directory:** `engines/generators/requirement_intelligence/`

**Tests:** 103/103 passing.

### 3.13 Semantic Understanding Engine (Specification 013, priority=99)

Understands the TRUE meaning of the user's request — not just keywords, but
intent, context, and meaning. It reads five data sources (user request,
requirement intelligence report, project context, knowledge base, and built-in
language rules), performs full sentence analysis (dialect normalization, spell
correction, abbreviation expansion, synonym resolution), extracts the true
intent, maps all variations to a unified intent, detects ambiguities and
requests clarification, understands relationships between the parts of the
request, calculates a confidence score, and produces a `SemanticUnderstanding
Report`.

**Directory:** `engines/generators/semantic_understanding/`

**Tests:** 76/76 passing.

### 3.14 Requirement Normalization Engine (Specification 014, priority=100)

Transforms ALL user requirements into a unified, canonical model that every
downstream engine can understand. It reads five data sources (user request,
requirement intelligence report, semantic understanding report, project
context, and knowledge base), unifies all names into canonical snake_case
keys, unifies all terminology into a single vocabulary, removes duplicates
using Jaccard similarity, validates consistency (detecting conflicts,
terminology variations, and lost requirements), links each requirement to its
feature, component, priority, dependencies, and expected output, caches the
normalized model for re-normalization, enforces quality rules, and produces a
`NormalizationReport`.

**Directory:** `engines/generators/requirement_normalization/`

**Tests:** 103/103 passing.

---

## 4. The CoreEngineManager (Specification 003)

The `CoreEngineManager` is the executive brain that governs every engine's
lifecycle, dependencies, execution order, and error handling. It is wired in
`core/bootstrap.py` and uses the same engine instances already registered with
the `EngineRegistry`.

### 4.1 Engine Lifecycle

Every engine goes through the following states:

```
Registered → Loaded → Initialized → Ready → Running → Completed
                                                   └→ Failed
```

- **Registered** — the engine has been registered with the manager.
- **Loaded** — the engine's code has been loaded.
- **Initialized** — the engine's `initialize()` method has been called.
- **Ready** — the engine is ready to run.
- **Running** — the engine is currently executing.
- **Completed** — the engine finished successfully.
- **Failed** — the engine failed (terminal state).

### 4.2 Dependency Enforcement

The manager checks that all dependencies are registered and completed before
running an engine. If a dependency is missing or not completed, the engine
is not run and a `DependencyError` is raised.

### 4.3 Execution Queue

The manager builds the execution queue by sorting engines by priority and
respecting dependencies. Lower priority numbers run first.

### 4.4 Security Rules

- Only registered engines can run.
- Only enabled engines can run.
- Unknown engines raise `UnknownEngineError`.
- Lifecycle transitions are enforced — no skipping states.

### 4.5 Fail-Fast

If any engine fails, the pipeline stops. No subsequent engines are run.

**Tests:** 53/53 passing.

---

## 5. Layer Breakdown

### 5.1 Configuration (`configuration/`)

Centralised, schema-validated configuration. No engine hardcodes values.

| File | Responsibility |
|------|---------------|
| `schema.py` | Defines the configuration schema (sections, fields, types, defaults). |
| `config.py` | Implements `Configuration` container and `ConfigSource` abstractions. |
| `defaults.py` | Assembles the default schema used by the whole engine. |

### 5.2 Logging (`logging/`)

Every step is recorded for traceability.

| File | Responsibility |
|------|---------------|
| `logger.py` | `EngineLogger` facade + `get_logger()` helper. |

### 5.3 Blueprint (`blueprint/`)

The intermediate representation of a bot — the contract between the
understanding and building phases.

| File | Responsibility |
|------|---------------|
| `blueprint.py` | All data classes: `Blueprint`, `BotMeta`, `CommandSpec`, `HandlerSpec`, `ConversationSpec`, `DatabaseSpec`, `MiddlewareSpec`, `IntegrationSpec`, `ProjectSpec`. |

### 5.4 Core (`core/`)

The heart of the system. Manages the build lifecycle but contains no
generation logic.

| File | Responsibility |
|------|---------------|
| `contracts.py` | Abstract interfaces: `Engine`, `Builder`, `Validator`, `PipelineStage`, `Component`. |
| `context.py` | `GenerationContext` — the shared state that flows through the pipeline. |
| `result.py` | `StageResult`, `ValidationReport`, `GenerationResult`, `Severity`. |
| `errors.py` | Exception hierarchy. |
| `bootstrap.py` | The single place that wires all 14 engines, builders, validators, and the manager together. |

### 5.5 Registry (`registry/`)

Central catalogue of all components.

| File | Responsibility |
|------|---------------|
| `registry.py` | `EngineRegistry` — maps names to component instances. Dumb container, no logic. |

### 5.6 Manager (`manager/`)

The `CoreEngineManager` and its components.

| File | Responsibility |
|------|---------------|
| `engine_manager.py` | `CoreEngineManager` — the executive brain. |
| `engine_entry.py` | `EngineEntry` — metadata for each registered engine. |
| `execution_queue.py` | Builds the ordered execution queue. |
| `lifecycle.py` | Enforces lifecycle state transitions. |
| `errors.py` | Manager-specific exceptions. |

### 5.7 Engines (`engines/`)

All generation engines. Each engine has a single responsibility.

| File/Directory | Responsibility |
|------|---------------|
| `base/base_engine.py` | Shared boilerplate for engines (logger, `ok()`/`failed()` helpers). |
| `base/base_generator.py` | Shared boilerplate for generators (builder references, file helpers). |
| `generators/analyzer/` | Spec 002 — 10-stage request analyzer. |
| `generators/intent_parser_engine.py` | Spec 005 — intent parser. |
| `generators/blueprint_composer_engine.py` | Spec 005 — blueprint composer. |
| `generators/project_planner/` | Spec 004 — project planning (blueprint, execution plan, risks). |
| `generators/blueprint_validator/` | Spec 004 — 6-layer blueprint validation. |
| `generators/structure_generator/` | Spec 006 — structure generation. |
| `generators/component_detector/` | Spec 007 — component detection. |
| `generators/file_planner/` | Spec 008 — file generation planning. |
| `generators/dependency_resolver/` | Spec 009 — dependency resolution. |
| `generators/project_context/` | Spec 010 — project context unification. |
| `generators/intelligence_graph/` | Spec 011 — intelligence graph. |
| `generators/requirement_intelligence/` | Spec 012 — requirement intelligence. |
| `generators/semantic_understanding/` | Spec 013 — semantic understanding. |
| `generators/requirement_normalization/` | Spec 014 — requirement normalization. |

### 5.8 Builders (`builders/`)

The **only** components that write files to disk.

| File | Responsibility |
|------|---------------|
| `directory_builder.py` | Creates directory structures. |
| `file_builder.py` | Writes individual files. |
| `python_module_builder.py` | Writes Python modules with a standardised header. |

### 5.9 Validators (`validators/`)

Verify artefacts at each stage.

| File | Responsibility |
|------|---------------|
| `base_validator.py` | Shared boilerplate for validators. |
| `blueprint_validator.py` | Validates blueprint consistency. |
| `structure_validator.py` | Validates generated file structure and Python syntax. |

### 5.10 Pipeline (`pipeline/`)

The ordered path a request follows.

| File | Responsibility |
|------|---------------|
| `base_stage.py` | Shared boilerplate for stages. |
| `orchestrator.py` | Drives the full pipeline. The only place that knows stage order. |
| `stages/parse_stage.py` | Parses the request. |
| `stages/compose_blueprint_stage.py` | Composes the blueprint. |
| `stages/validate_blueprint_stage.py` | Validates the blueprint. |
| `stages/generate_stage.py` | Runs all generator engines. |
| `stages/validate_output_stage.py` | Validates the generated output. |
| `stages/package_stage.py` | Packages the final deliverable. |

### 5.11 Output (`output/`)

Assembles and packages the final deliverable after validation.

| File | Responsibility |
|------|---------------|
| `output_manager.py` | Finalises the project directory, creates zip archive, returns `PackageInfo`. |

---

## 6. The Generation Flow

### 6.1 Step by Step

1. **User calls `generate_bot("description")`**.
2. **Bootstrap** assembles the registry, builders, all 14 engines, validators,
   the `CoreEngineManager`, and the orchestrator.
3. **Orchestrator** creates a `GenerationContext` with the request.
4. **Engine 1 (Analyzer)** — parses the request through 10 stages and
   produces an `AnalysisReport`.
5. **Engine 2 (Intent Parser)** — structures the request into a formal intent.
6. **Engine 3 (Blueprint Composer)** — composes a draft blueprint.
7. **Engine 4 (Project Planner)** — builds the full `ProjectBlueprint` with
   features, dependency graph, execution plan, and risks.
8. **Engine 5 (Blueprint Validator)** — validates the blueprint across 6
   layers.
9. **Engine 6 (Structure Generator)** — generates the folder and file
   structure map.
10. **Engine 7 (Component Detector)** — detects all components and produces
    a `ComponentRegistry`.
11. **Engine 8 (File Planner)** — plans every file the project will contain.
12. **Engine 9 (Dependency Resolver)** — builds the dependency map and
    determines required libraries.
13. **Engine 10 (Project Context)** — unifies all upstream artefacts into a
    `ProjectContext`.
14. **Engine 11 (Intelligence Graph)** — converts all artefacts into a
    `ProjectIntelligenceGraph`.
15. **Engine 12 (Requirement Intelligence)** — understands the request with
    precision, classifies requirements, detects conflicts.
16. **Engine 13 (Semantic Understanding)** — understands the true meaning of
    the request.
17. **Engine 14 (Requirement Normalization)** — transforms all requirements
    into a unified, canonical model.
18. **Building Phase** (future) — code generation, file creation, packaging.
19. **Result** — a `GenerationResult` with the project path and metadata.

### 6.2 Fail-Fast Semantics

By default, the pipeline stops at the first failing engine. This behaviour is
configurable via `pipeline.fail_fast` in the configuration.

---

## 7. Extension Points

### 7.1 Adding a New Generator Engine

1. Create a new directory in `engines/generators/` with the engine and its
   helper components.
2. Implement a class inheriting from `BaseEngine`.
3. Register the engine in `core/bootstrap.py` with `registry.register_engine()`
   and `manager.register()` with a priority and dependencies.
4. No other file changes — the pipeline automatically picks it up.

### 7.2 Adding a New Validator

1. Create a new file in `validators/` inheriting from `BaseValidator`.
2. Set `applies_to` metadata to `"blueprint"` or `"output"`.
3. Register in `core/bootstrap.py`.

### 7.3 Adding a New Builder

1. Create a new file in `builders/` inheriting from `Builder`.
2. Register in `core/bootstrap.py`.

### 7.4 Adding a New Configuration Option

1. Add a `FieldSchema` to the appropriate section in
   `configuration/defaults.py`.
2. Read it in the component that needs it via `config.get()`.

---

## 8. Current Status

### Implemented (14 engines)

- ✅ Configuration system (schema, sources, validation).
- ✅ Logging system.
- ✅ Blueprint data model.
- ✅ Core contracts, context, result, errors.
- ✅ Engine registry.
- ✅ CoreEngineManager (lifecycle, dependencies, execution queue, security).
- ✅ Builders (directory, file, python module).
- ✅ Validators (blueprint, structure).
- ✅ Pipeline stages (all six stages) + orchestrator.
- ✅ Output manager.
- ✅ Bootstrap wiring (all 14 engines).
- ✅ Engine 1: Analyzer (10 stages) — Spec 002.
- ✅ Engine 2: Intent Parser — Spec 005.
- ✅ Engine 3: Blueprint Composer — Spec 005.
- ✅ Engine 4: Project Planner — Spec 004 (288 tests).
- ✅ Engine 5: Blueprint Validator — Spec 004 (27 tests).
- ✅ Engine 6: Structure Generator — Spec 006 (61 tests).
- ✅ Engine 7: Component Detector — Spec 007.
- ✅ Engine 8: File Planner — Spec 008 (78 tests).
- ✅ Engine 9: Dependency Resolver — Spec 009 (99 tests).
- ✅ Engine 10: Project Context — Spec 010 (125 tests).
- ✅ Engine 11: Intelligence Graph — Spec 011 (127 tests).
- ✅ Engine 12: Requirement Intelligence — Spec 012 (103 tests).
- ✅ Engine 13: Semantic Understanding — Spec 013 (76 tests).
- ✅ Engine 14: Requirement Normalization — Spec 014 (103 tests).

**Total: 1,010+ tests across 11 test suites, all passing.**

### To Be Implemented (Future — Building Phase)

- ⬜ Code generation engines (bot core, handlers, conversations, database,
  middleware, config, requirements.txt, Dockerfile, etc.).
- ⬜ Engine auto-discovery (scan packages for registered engines).
- ⬜ CLI entry point.
- ⬜ API keys for developers (product vision).

---

## 9. Directory Structure

```
telegram_bot_engine/
├── __init__.py                      # High-level entry point
├── ARCHITECTURE.md                  # This document
├── blueprint/
│   ├── __init__.py
│   └── blueprint.py                  # Data model
├── builders/
│   ├── __init__.py
│   ├── directory_builder.py
│   ├── file_builder.py
│   └── python_module_builder.py
├── configuration/
│   ├── __init__.py
│   ├── config.py
│   ├── defaults.py
│   └── schema.py
├── core/
│   ├── __init__.py
│   ├── bootstrap.py                  # THE wiring point for all 14 engines
│   ├── context.py                    # GenerationContext
│   ├── contracts.py                  # Abstract interfaces
│   ├── errors.py                     # Exception hierarchy
│   └── result.py                     # StageResult, ValidationReport, etc.
├── engines/
│   ├── __init__.py
│   ├── base/
│   │   ├── __init__.py
│   │   ├── base_engine.py            # Shared boilerplate (logger, ok/failed)
│   │   └── base_generator.py         # Shared boilerplate for generators
│   └── generators/
│       ├── __init__.py               # Exports all 14 engine classes
│       ├── analyzer/                 # Spec 002 — 10-stage analyzer
│       │   ├── __init__.py
│       │   ├── analysis_report.py
│       │   ├── analyzer_engine.py
│       │   └── stages/
│       │       ├── stage1_cleaner.py
│       │       ├── stage2_segmenter.py
│       │       ├── stage3_keyword_extractor.py
│       │       ├── stage4_classifier.py
│       │       ├── stage5_feature_extractor.py
│       │       ├── stage6_technology_extractor.py
│       │       ├── stage7_relationship_analyzer.py
│       │       ├── stage8_conflict_detector.py
│       │       ├── stage9_missing_info_detector.py
│       │       └── stage10_report_builder.py
│       ├── intent_parser_engine.py          # Spec 005
│       ├── blueprint_composer_engine.py     # Spec 005
│       ├── project_planner/                # Spec 004
│       ├── blueprint_validator/            # Spec 004
│       ├── structure_generator/            # Spec 006
│       ├── component_detector/             # Spec 007
│       ├── file_planner/                   # Spec 008
│       ├── dependency_resolver/            # Spec 009
│       ├── project_context/                # Spec 010
│       ├── intelligence_graph/             # Spec 011
│       ├── requirement_intelligence/       # Spec 012
│       ├── semantic_understanding/         # Spec 013
│       └── requirement_normalization/      # Spec 014
├── logging/
│   ├── __init__.py
│   └── logger.py
├── manager/
│   ├── __init__.py
│   ├── engine_entry.py
│   ├── engine_manager.py               # CoreEngineManager
│   ├── errors.py
│   ├── execution_queue.py
│   └── lifecycle.py
├── output/
│   ├── __init__.py
│   └── output_manager.py
├── pipeline/
│   ├── __init__.py
│   ├── base_stage.py
│   ├── orchestrator.py
│   └── stages/
│       ├── __init__.py
│       ├── compose_blueprint_stage.py
│       ├── generate_stage.py
│       ├── package_stage.py
│       ├── parse_stage.py
│       ├── validate_blueprint_stage.py
│       └── validate_output_stage.py
├── registry/
│   ├── __init__.py
│   └── registry.py
└── validators/
    ├── __init__.py
    ├── base_validator.py
    ├── blueprint_validator.py
    └── structure_validator.py
```

**29 directories, 192 Python files.**
