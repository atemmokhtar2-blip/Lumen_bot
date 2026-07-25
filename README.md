# AI Agent 7h Bot — Telegram Bot Generation Engine

> **This project is under active development — iterating through numbered Specifications.**
>
> Each specification adds one complete, tested engine to the generation pipeline.
> Implemented so far: **001 through 014** (14 engines). Specification **015** is next.

---

## What Is This Project?

This project is **not** a Telegram bot. It is a **Generation Engine** — a system
that takes a natural-language request from the user and generates a complete,
ready-to-run Telegram bot project.

The system is built in a modular (engine-per-responsibility) architecture where
each engine has one clearly defined job. All engines communicate exclusively
through `GenerationContext` artefacts — no engine reads or modifies another
engine's outputs directly.

---

## Current Status

| Spec | Engine | Priority | Description | Tests |
|------|--------|----------|-------------|-------|
| 001 | Core Architecture | — | Foundation (configuration, logging, blueprint, core, registry, builders, validators, pipeline) | — |
| 002 | Request Analyzer | 10 | Parses the user's natural-language request through 10 stages and produces an `AnalysisReport` | 6 stages ✅ |
| 003 | Core Engine Manager | — | Manages engine lifecycle, dependencies, execution order, security, and error handling | 53/53 ✅ |
| 004 | Project Planning Engine | 40 | Builds the `ProjectBlueprint`, dependency graph, 8-phase execution plan, and risk detection | 288/288 ✅ |
| 005 | Intent Parser Engine | 20 | Parses the request into a structured intent | — |
| 006 | Structure Generation Engine | 60 | Generates the complete project folder and file structure map | 61/61 ✅ |
| 007 | Component Detection Engine | 70 | Detects every software component and produces a Component Registry | — |
| 008 | File Generation Planning Engine | 80 | Plans every file the project will contain before any code is written | 78/78 ✅ |
| 009 | Dependency Resolution Engine | 95 | Builds the complete dependency map and determines required libraries | 99/99 ✅ |
| 010 | Project Context Engine | 96 | Unifies all upstream artefacts into a single `ProjectContext` with O(1) look-up indices | 125/125 ✅ |
| 011 | Intelligence Graph Engine | 97 | Converts all artefacts into a `ProjectIntelligenceGraph` with 19 node types and 12 edge kinds | 127/127 ✅ |
| 012 | Requirement Intelligence Engine | 98 | Understands the user's request with precision, classifies requirements into 9 categories, detects missing info and conflicts | 103/103 ✅ |
| 013 | Semantic Understanding Engine | 99 | Understands the TRUE meaning of the request — dialect normalization, spell correction, abbreviation expansion, synonym resolution, intent extraction | 76/76 ✅ |
| 014 | Requirement Normalization Engine | 100 | Transforms all requirements into a unified, canonical model — name normalization, terminology unification, deduplication, consistency validation, requirement linking | 103/103 ✅ |
| **015** | **Next — not started** | ⏳ | | — |

**Total: 14 engines in the pipeline (Specs 001–014).**

> **Note:** Spec 009 in the original plan referred to a PDFX Visual Page
> Reconstruction Engine. That engine was removed because it was added by
> mistake. The Specification 009 slot is now occupied by the Dependency
> Resolution Engine, which is the correct engine for this pipeline stage.

---

## The 14-Engine Pipeline

```
User Request (natural language)
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│                   UNDERSTANDING PHASE                    │
│                                                          │
│  1. Analyzer (p=10)        → AnalysisReport             │
│  2. Intent Parser (p=20)    → Structured Intent          │
│  3. Blueprint Composer (p=30) → Draft Blueprint          │
│  4. Project Planner (p=40)  → ProjectBlueprint           │
│  5. Blueprint Validator (p=50) → ValidationReport       │
│  6. Structure Generator (p=60) → ProjectStructureMap    │
│  7. Component Detector (p=70) → ComponentRegistry        │
│  8. File Planner (p=80)     → FileGenerationPlan         │
│  9. Dependency Resolver (p=95) → DependencyResolution   │
│ 10. Project Context (p=96)  → ProjectContext             │
│ 11. Intelligence Graph (p=97) → ProjectIntelligenceGraph│
│ 12. Requirement Intelligence (p=98) → ReqIntelReport    │
│ 13. Semantic Understanding (p=99) → SemanticReport     │
│ 14. Requirement Normalization (p=100) → NormalizationReport│
└─────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│                    BUILDING PHASE                         │
│  (future engines — code generation, packaging, output)   │
└─────────────────────────────────────────────────────────┘
        │
        ▼
    Generated Bot Project (.zip)
```

Each engine reads only what it needs from the `GenerationContext` and produces
its own artefact. No engine modifies another engine's output. If an engine's
input is missing, it returns a tolerant "not available" result rather than
crashing.

---

## Architectural Tree

```
telegram_bot_engine/
├── __init.py__                    # High-level entry point
├── ARCHITECTURE.md                # This project's architecture document
├── blueprint/                     # Data model (Blueprint, BotMeta, etc.)
├── builders/                      # The ONLY components that write to disk
│   ├── directory_builder.py
│   ├── file_builder.py
│   └── python_module_builder.py
├── configuration/                 # Centralised, schema-validated config
│   ├── config.py
│   ├── defaults.py
│   └── schema.py
├── core/                          # The heart of the system
│   ├── bootstrap.py               # The single wiring point for ALL engines
│   ├── context.py                 # GenerationContext — shared state
│   ├── contracts.py               # Abstract interfaces (Engine, Builder, etc.)
│   ├── errors.py                  # Exception hierarchy
│   └── result.py                  # StageResult, ValidationReport, etc.
├── engines/
│   ├── base/
│   │   ├── base_engine.py         # Shared boilerplate (logger, ok/failed)
│   │   └── base_generator.py      # Shared boilerplate for generators
│   └── generators/                # ALL 14 generation engines
│       ├── analyzer/              # Spec 002 — 10-stage request analyzer
│       ├── intent_parser_engine.py     # Spec 005
│       ├── blueprint_composer_engine.py# Spec 005
│       ├── project_planner/       # Spec 004 — blueprint, execution plan
│       ├── blueprint_validator/   # Spec 004 — 6-layer validation
│       ├── structure_generator/   # Spec 006
│       ├── component_detector/    # Spec 007
│       ├── file_planner/          # Spec 008
│       ├── dependency_resolver/   # Spec 009
│       ├── project_context/       # Spec 010
│       ├── intelligence_graph/    # Spec 011
│       ├── requirement_intelligence/  # Spec 012
│       ├── semantic_understanding/    # Spec 013
│       └── requirement_normalization/ # Spec 014
├── logging/                       # EngineLogger facade
├── manager/                       # CoreEngineManager (lifecycle, deps, queue)
│   ├── engine_entry.py
│   ├── engine_manager.py
│   ├── errors.py
│   ├── execution_queue.py
│   └── lifecycle.py
├── output/                        # OutputManager — final packaging
├── pipeline/                      # PipelineOrchestrator + 6 stages
│   ├── base_stage.py
│   ├── orchestrator.py
│   └── stages/
├── registry/                      # EngineRegistry — dumb container
└── validators/                    # Blueprint & structure validators
```

---

## How It Works

1. **The user** writes a request in natural language (e.g., "I want a Telegram
   store bot that manages products and orders using SQLite").
2. **The Analyzer** (Spec 002) parses the request through 10 stages and
   produces an `AnalysisReport` with keywords, features, technologies, and
   detected conflicts.
3. **The Intent Parser** (Spec 005) structures the request into a formal
   intent.
4. **The Blueprint Composer** (Spec 005) composes a draft blueprint from the
   intent using bot-type profiles.
5. **The Project Planner** (Spec 004) builds the full `ProjectBlueprint` with
   features, dependency graph, 8-phase execution plan, and risk detection.
6. **The Blueprint Validator** (Spec 004) validates the blueprint across 6
   layers (basic data, features, relationships, execution plan, dependencies,
   buildability).
7. **The Structure Generator** (Spec 006) generates the complete folder and
   file structure map.
8. **The Component Detector** (Spec 007) detects every software component
   and produces a Component Registry.
9. **The File Planner** (Spec 008) plans every file the project will contain
   before any code is written.
10. **The Dependency Resolver** (Spec 009) builds the complete dependency map
    and determines the required libraries.
11. **The Project Context Engine** (Spec 010) unifies all upstream artefacts
    into a single `ProjectContext` with O(1) look-up indices.
12. **The Intelligence Graph Engine** (Spec 011) converts all artefacts into a
    `ProjectIntelligenceGraph` with 19 node types and 12 edge kinds, detecting
    circular dependencies, broken references, and dead components.
13. **The Requirement Intelligence Engine** (Spec 012) understands the user's
    request with the highest precision — intent analysis across 5 dimensions,
    9-category classification, missing-info detection, and conflict detection.
14. **The Semantic Understanding Engine** (Spec 013) understands the TRUE
    meaning of the request — dialect normalization, spell correction,
    abbreviation expansion, synonym resolution, and intent mapping.
15. **The Requirement Normalization Engine** (Spec 014) transforms all
    requirements into a unified, canonical model — name normalization,
    terminology unification, deduplication (Jaccard similarity), consistency
    validation, and requirement linking.

Each engine reads only what it needs from the `GenerationContext` and produces
its own artefact. No engine modifies another engine's output — if
post-processing is needed, a dedicated engine is required.

---

## Key Design Patterns

### Engine-per-Responsibility
Every engine has exactly one job. No file is responsible for everything. This
makes the system testable, maintainable, and extensible.

### Context-Only Communication
Engines communicate exclusively through `GenerationContext` artefacts. No
engine imports or directly calls another engine.

### Tolerant Readers
Every reader returns a `*Data` object with `available=False` when the upstream
artefact is missing. This allows the pipeline to continue gracefully rather
than crashing.

### BaseEngine Pattern
All engines inherit from `BaseEngine`, which provides a logger and `ok()` /
`failed()` helpers that return `StageResult` objects.

### Quality Gates
Each engine has a quality gate or quality validator that checks the report
quality and can block the pipeline on errors.

### Bootstrap Registration
All 14 engines are registered in `core/bootstrap.py` with a priority and a
list of dependencies. The `CoreEngineManager` uses these to build the
execution queue and enforce the correct order.

### CoreEngineManager
The manager (`Spec 003`) governs every engine's lifecycle (Registered → Loaded
→ Initialized → Ready → Running → Completed/Failed), validates dependencies,
enforces security rules, and stops the pipeline on the first failure.

---

## Running the Tests

```bash
# Run all test suites
PYTHONPATH=. python tests/test_manager.py
PYTHONPATH=. python tests/test_project_planner.py
PYTHONPATH=. python tests/test_structure_generator.py
PYTHONPATH=. python tests/test_file_planner.py
PYTHONPATH=. python tests/test_dependency_resolver.py
PYTHONPATH=. python tests/test_project_context.py
PYTHONPATH=. python tests/test_intelligence_graph.py
PYTHONPATH=. python tests/test_blueprint_validator.py
PYTHONPATH=. python tests/test_requirement_intelligence.py
PYTHONPATH=. python tests/test_semantic_understanding.py
PYTHONPATH=. python tests/test_requirement_normalization.py

# Or run them all at once
PYTHONPATH=. python tests/test_manager.py && \
PYTHONPATH=. python tests/test_project_planner.py && \
PYTHONPATH=. python tests/test_structure_generator.py && \
PYTHONPATH=. python tests/test_file_planner.py && \
PYTHONPATH=. python tests/test_dependency_resolver.py && \
PYTHONPATH=. python tests/test_project_context.py && \
PYTHONPATH=. python tests/test_intelligence_graph.py && \
PYTHONPATH=. python tests/test_blueprint_validator.py && \
PYTHONPATH=. python tests/test_requirement_intelligence.py && \
PYTHONPATH=. python tests/test_semantic_understanding.py && \
PYTHONPATH=. python tests/test_requirement_normalization.py
```

**Test Summary:** 1,010+ tests across 11 test suites, all passing.

---

## Documentation

- `telegram_bot_engine/ARCHITECTURE.md` — Full architecture document with the
  14-engine pipeline and layer breakdown.
- `docs/ALL_ENGINES_COMPLETE_DOCUMENTATION.md` — Complete documentation for
  every engine in the pipeline.

---

## Note for Any AI Working on This Project

This project is built through numbered specifications. Each specification:
- Is implemented **completely** before moving to the next.
- Is tested **fully** before being accepted.
- **No** additional components are added outside the specification scope.
- **No** architectural changes are made without a clear specification.

**The next specification is 015.** Start from there. Do not modify what was
previously implemented unless fixing urgent bugs only.

---

## License

Private project — under active development.
