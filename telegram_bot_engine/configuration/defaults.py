"""
Default configuration schema for the Telegram Bot Generation Engine.

This module assembles the :class:`~configuration.schema.ConfigSchema` that
describes every option the engine understands.  It is the single place
where new configuration knobs are declared.

Engines should never reference this module directly — they receive a
:class:`~configuration.config.Configuration` object at construction time.
"""

from __future__ import annotations

from .schema import ConfigSchema, FieldSchema, SectionSchema


def build_default_schema() -> ConfigSchema:
    """Construct and return the default engine configuration schema."""

    logging_section = SectionSchema(
        name="logging",
        description="Controls how the engine records every step it performs.",
        fields=[
            FieldSchema(
                name="level",
                type=str,
                default="INFO",
                description="Minimum severity of log messages to emit.",
                choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
            ),
            FieldSchema(
                name="format",
                type=str,
                default="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                description="Format string for log records.",
            ),
            FieldSchema(
                name="log_dir",
                type=str,
                default="logs",
                description="Directory where log files are written.",
            ),
            FieldSchema(
                name="to_file",
                type=bool,
                default=True,
                description="Whether to write logs to a file.",
            ),
            FieldSchema(
                name="to_console",
                type=bool,
                default=True,
                description="Whether to emit logs to the console.",
            ),
        ],
    )

    pipeline_section = SectionSchema(
        name="pipeline",
        description="Controls the generation pipeline behaviour.",
        fields=[
            FieldSchema(
                name="fail_fast",
                type=bool,
                default=True,
                description=(
                    "When True the pipeline stops at the first failing "
                    "stage.  When False it collects all errors."
                ),
            ),
            FieldSchema(
                name="max_parallel_stages",
                type=int,
                default=1,
                description=(
                    "Maximum number of stages that may run concurrently. "
                    "Most stages must run sequentially."
                ),
                validator=lambda v: v >= 1,
            ),
            FieldSchema(
                name="continue_on_validation_warning",
                type=bool,
                default=False,
                description=(
                    "When True the pipeline continues even if a validator "
                    "produces warnings (not errors)."
                ),
            ),
        ],
    )

    output_section = SectionSchema(
        name="output",
        description="Controls how the final generated project is packaged.",
        fields=[
            FieldSchema(
                name="base_dir",
                type=str,
                default="output",
                description=(
                    "Root directory where generated projects are written."
                ),
            ),
            FieldSchema(
                name="project_prefix",
                type=str,
                default="bot_project",
                description=(
                    "Prefix used when generating unique project directory "
                    "names."
                ),
            ),
            FieldSchema(
                name="clean_before_build",
                type=bool,
                default=True,
                description=(
                    "When True the target directory is removed before a "
                    "new build starts."
                ),
            ),
            FieldSchema(
                name="create_zip",
                type=bool,
                default=True,
                description="Whether to create a zip archive of the result.",
            ),
        ],
    )

    registry_section = SectionSchema(
        name="registry",
        description="Controls how engines and builders are discovered.",
        fields=[
            FieldSchema(
                name="auto_discover",
                type=bool,
                default=True,
                description=(
                    "When True the registry scans known packages for "
                    "registered components."
                ),
            ),
            FieldSchema(
                name="engine_packages",
                type=str,
                default="telegram_bot_engine.engines.generators",
                description=(
                    "Comma-separated list of packages to scan for engine "
                    "implementations."
                ),
            ),
        ],
    )

    engine_section = SectionSchema(
        name="engine",
        description="Global defaults applied to individual generation engines.",
        fields=[
            FieldSchema(
                name="default_language",
                type=str,
                default="python",
                description="Programming language of generated bots.",
                choices=["python"],
            ),
            FieldSchema(
                name="default_python_version",
                type=str,
                default="3.11",
                description="Python version targeted by generated projects.",
            ),
            FieldSchema(
                name="default_framework",
                type=str,
                default="python-telegram-bot",
                description="Telegram library used in generated projects.",
            ),
        ],
    )

    blueprint_validator_section = SectionSchema(
        name="blueprint_validator",
        description=(
            "Controls the Blueprint Validator Engine (Specification 005). "
            "These settings determine the quality thresholds and weights "
            "used to decide whether a blueprint is approved or rejected."
        ),
        fields=[
            FieldSchema(
                name="minimum_required_score",
                type=float,
                default=0.7,
                description=(
                    "The minimum overall quality score (0.0-1.0) "
                    "required for a blueprint to be approved."
                ),
                validator=lambda v: 0.0 <= v <= 1.0,
            ),
            FieldSchema(
                name="weight_structure_quality",
                type=float,
                default=0.25,
                description=(
                    "Weight of the structure-quality sub-score in the "
                    "overall quality score."
                ),
                validator=lambda v: 0.0 <= v <= 1.0,
            ),
            FieldSchema(
                name="weight_dependency_quality",
                type=float,
                default=0.30,
                description=(
                    "Weight of the dependency-quality sub-score in the "
                    "overall quality score."
                ),
                validator=lambda v: 0.0 <= v <= 1.0,
            ),
            FieldSchema(
                name="weight_feature_quality",
                type=float,
                default=0.20,
                description=(
                    "Weight of the feature-quality sub-score in the "
                    "overall quality score."
                ),
                validator=lambda v: 0.0 <= v <= 1.0,
            ),
            FieldSchema(
                name="weight_planning_quality",
                type=float,
                default=0.25,
                description=(
                    "Weight of the planning-quality sub-score in the "
                    "overall quality score."
                ),
                validator=lambda v: 0.0 <= v <= 1.0,
            ),
        ],
    )

    structure_generator_section = SectionSchema(
        name="structure_generator",
        description=(
            "Controls the Structure Generation Engine (Specification 006). "
            "These settings determine how the project structure map is "
            "built — the threshold for large projects and whether the "
            "engine proceeds even when the blueprint has warnings."
        ),
        fields=[
            FieldSchema(
                name="large_project_threshold",
                type=int,
                default=8,
                description=(
                    "The number of components above which the project "
                    "is considered 'large' and components are split "
                    "into independent package folders."
                ),
                validator=lambda v: v >= 1,
            ),
            FieldSchema(
                name="proceed_on_warning",
                type=bool,
                default=True,
                description=(
                    "When True the structure engine proceeds even if "
                    "the blueprint validation has warnings (not errors). "
                    "When False, only APPROVED blueprints proceed."
                ),
            ),
            FieldSchema(
                name="create_directories",
                type=bool,
                default=False,
                description=(
                    "When True the engine also physically creates the "
                    "directories on disk using the DirectoryBuilder. "
                    "When False (default), only the structure map is "
                    "produced; physical creation is deferred to a "
                    "later phase."
                ),
            ),
        ],
    )

    component_detector_section = SectionSchema(
        name="component_detector",
        description=(
            "Controls the Component Detection Engine (Specification 007). "
            "These settings determine how the component registry is "
            "built — whether the engine proceeds even when the blueprint "
            "has warnings, and whether error-level findings cause the "
            "engine to fail."
        ),
        fields=[
            FieldSchema(
                name="proceed_on_warning",
                type=bool,
                default=True,
                description=(
                    "When True the component detector proceeds even if "
                    "the blueprint validation has warnings (not errors). "
                    "When False, only APPROVED blueprints proceed."
                ),
            ),
            FieldSchema(
                name="fail_on_errors",
                type=bool,
                default=True,
                description=(
                    "When True the engine returns a failed StageResult "
                    "when any error-level findings are detected "
                    "(e.g. circular dependencies, self-dependencies, "
                    "incompatible components).  When False, the engine "
                    "records the findings but returns a successful "
                    "result."
                ),
            ),
            FieldSchema(
                name="detect_repositories",
                type=bool,
                default=True,
                description=(
                    "When True the engine detects repository and "
                    "database-model components for features that "
                    "require a database.  When False, these "
                    "components are not detected automatically."
                ),
            ),
        ],
    )

    file_planner_section = SectionSchema(
        name="file_planner",
        description=(
            "Controls the File Generation Planning Engine "
            "(Specification 008).  These settings determine how the "
            "file generation plan is built — whether the engine "
            "proceeds even when the blueprint has warnings, and "
            "whether error-level findings cause the engine to fail."
        ),
        fields=[
            FieldSchema(
                name="proceed_on_warning",
                type=bool,
                default=True,
                description=(
                    "When True the file planner proceeds even if "
                    "the blueprint validation has warnings (not "
                    "errors).  When False, only APPROVED blueprints "
                    "proceed."
                ),
            ),
            FieldSchema(
                name="fail_on_errors",
                type=bool,
                default=True,
                description=(
                    "When True the engine returns a failed "
                    "StageResult when any error-level findings are "
                    "detected (e.g. duplicate files, circular "
                    "dependencies, files without purpose).  When "
                    "False, the engine records the findings but "
                    "returns a successful result."
                ),
            ),
            FieldSchema(
                name="require_all_components_have_files",
                type=bool,
                default=False,
                description=(
                    "When True the engine treats it as an error if "
                    "any component in the registry has no planned "
                    "files.  When False (default), missing files "
                    "are recorded as warnings."
                ),
            ),
        ],
    )

    requirement_intelligence_section = SectionSchema(
        name="requirement_intelligence",
        description=(
            "Controls the Requirement Intelligence Engine "
            "(Specification 012).  These settings determine how the "
            "Requirement Intelligence Report is built — whether the "
            "engine proceeds even when upstream artefacts have "
            "warnings, whether error-level findings cause the engine "
            "to fail, and the thresholds used during quality "
            "validation and priority assignment."
        ),
        fields=[
            FieldSchema(
                name="proceed_on_warning",
                type=bool,
                default=True,
                description=(
                    "When True the requirement intelligence engine "
                    "proceeds even if upstream artefacts (analysis "
                    "report, project context, intelligence graph) "
                    "have warnings.  When False, the engine only "
                    "proceeds when all upstream artefacts are clean."
                ),
            ),
            FieldSchema(
                name="fail_on_errors",
                type=bool,
                default=True,
                description=(
                    "When True the engine returns a failed "
                    "StageResult when any error-level findings are "
                    "detected (e.g. requirement conflicts, quality "
                    "violations, contradictory technologies).  When "
                    "False, the engine records the findings but "
                    "returns a successful result."
                ),
            ),
            FieldSchema(
                name="fail_on_quality_violations",
                type=bool,
                default=True,
                description=(
                    "When True the engine returns a failed "
                    "StageResult when the quality validator detects "
                    "any quality violations (e.g. requirements "
                    "without a description, goal, reason, or "
                    "priority).  When False, quality violations are "
                    "recorded as findings but do not cause failure."
                ),
            ),
            FieldSchema(
                name="default_quality_level",
                type=str,
                default="standard",
                description=(
                    "The quality level assigned to the project when "
                    "the user's request does not explicitly specify "
                    "one."
                ),
                choices=["minimal", "standard", "high", "production"],
            ),
            FieldSchema(
                name="max_implicit_ratio",
                type=float,
                default=0.5,
                description=(
                    "The maximum allowed ratio of implicit "
                    "requirements to total requirements.  When the "
                    "implicit ratio exceeds this value, a warning "
                    "finding is emitted."
                ),
                validator=lambda v: 0.0 <= v <= 1.0,
            ),
            FieldSchema(
                name="min_intent_confidence",
                type=float,
                default=0.3,
                description=(
                    "The minimum overall intent-confidence score "
                    "(0.0-1.0) below which a warning finding is "
                    "emitted, indicating that the user's intent is "
                    "not understood with sufficient precision."
                ),
                validator=lambda v: 0.0 <= v <= 1.0,
            ),
        ],
    )

    return ConfigSchema(
        sections=[
            logging_section,
            pipeline_section,
            output_section,
            registry_section,
            engine_section,
            blueprint_validator_section,
            structure_generator_section,
            component_detector_section,
            file_planner_section,
            requirement_intelligence_section,
        ],
    )


__all__ = ["build_default_schema"]
