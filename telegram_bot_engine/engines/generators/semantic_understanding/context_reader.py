"""
Context reader — reads the project context from the generation context.

The :class:`ContextReader` is responsible for obtaining the
``project_context`` artefact (produced by the
:class:`~telegram_bot_engine.engines.generators.project_context.ProjectContextEngine`)
and returning a normalised :class:`ContextData` object.

The reader is tolerant: it never raises when the project context is
not available.  It returns a :class:`ContextData` with
``available=False`` in that case.

This module is a pure reader: it has no side effects and does not
modify the generation context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from ....core.context import GenerationContext
from .report_data import SOURCE_PROJECT_CONTEXT


# ---------------------------------------------------------------------------#
# Context data
# ---------------------------------------------------------------------------#

@dataclass
class ContextData:
    """Normalised view of the project context.

    This is a lightweight container that holds the information the
    Semantic Understanding Engine needs from the Project Context.

    Attributes:
        project_name: The machine-friendly project name.
        display_name: The human-readable project name.
        bot_type: The detected bot type.
        primary_goal: A one-sentence description of what the
            project does.
        language: The programming language.
        language_version: The language version.
        framework: The Telegram bot framework.
        database: The chosen database backend.
        feature_names: The list of feature names.
        component_names: The list of component names.
        file_paths: The list of file paths.
        dependency_names: The list of dependency names.
        stage_names: The list of stage names.
        expansion_areas: The list of expansion-point areas.
        available: Whether the project context was available.
    """

    project_name: str = ""
    display_name: str = ""
    bot_type: str = "general"
    primary_goal: str = ""
    language: str = "python"
    language_version: str = "3.11"
    framework: str = "python-telegram-bot"
    database: str = ""
    feature_names: List[str] = field(default_factory=list)
    component_names: List[str] = field(default_factory=list)
    file_paths: List[str] = field(default_factory=list)
    dependency_names: List[str] = field(default_factory=list)
    stage_names: List[str] = field(default_factory=list)
    expansion_areas: List[str] = field(default_factory=list)
    available: bool = False

    @property
    def source_artefact(self) -> str:
        return SOURCE_PROJECT_CONTEXT

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_name": self.project_name,
            "display_name": self.display_name,
            "bot_type": self.bot_type,
            "primary_goal": self.primary_goal,
            "language": self.language,
            "language_version": self.language_version,
            "framework": self.framework,
            "database": self.database,
            "feature_names": list(self.feature_names),
            "component_names": list(self.component_names),
            "file_paths": list(self.file_paths),
            "dependency_names": list(self.dependency_names),
            "stage_names": list(self.stage_names),
            "expansion_areas": list(self.expansion_areas),
            "available": self.available,
        }


class ContextReader:
    """Reads the project context from the generation context.

    The reader looks for the ``project_context`` artefact.  When
    present, it extracts the goal, features, components, files,
    dependencies, stages, and expansion points.  When absent, it
    returns a :class:`ContextData` with ``available=False``.
    """

    def read(self, context: GenerationContext) -> ContextData:
        """Read the project context and return a :class:`ContextData`."""
        project_context = context.get("project_context")
        if project_context is None:
            return ContextData(available=False)

        return self._read_from_project_context(project_context)

    # ----------------------------------------------------------------- #
    # Internal helpers
    # ----------------------------------------------------------------- #

    def _read_from_project_context(
        self, project_context: Any,
    ) -> ContextData:
        """Extract context data from the project context artefact."""
        def get_attr(name: str, default: Any = None) -> Any:
            if hasattr(project_context, name):
                return getattr(project_context, name)
            if isinstance(project_context, dict):
                return project_context.get(name, default)
            return default

        # Goal
        goal = get_attr("goal")
        if goal is not None:
            project_name = str(getattr(goal, "name", "") or
                               (goal.get("name", "") if isinstance(goal, dict) else ""))
            display_name = str(getattr(goal, "display_name", "") or
                               (goal.get("display_name", "") if isinstance(goal, dict) else ""))
            bot_type = str(getattr(goal, "bot_type", "general") or
                           (goal.get("bot_type", "general") if isinstance(goal, dict) else "general"))
            primary_goal = str(getattr(goal, "primary_goal", "") or
                               (goal.get("primary_goal", "") if isinstance(goal, dict) else ""))
            language = str(getattr(goal, "language", "python") or
                           (goal.get("language", "python") if isinstance(goal, dict) else "python"))
            language_version = str(getattr(goal, "language_version", "3.11") or
                                   (goal.get("language_version", "3.11") if isinstance(goal, dict) else "3.11"))
            framework = str(getattr(goal, "framework", "python-telegram-bot") or
                            (goal.get("framework", "python-telegram-bot") if isinstance(goal, dict) else "python-telegram-bot"))
            database = str(getattr(goal, "database", "") or
                           (goal.get("database", "") if isinstance(goal, dict) else ""))
        else:
            project_name = ""
            display_name = ""
            bot_type = "general"
            primary_goal = ""
            language = "python"
            language_version = "3.11"
            framework = "python-telegram-bot"
            database = ""

        # Features
        feature_names = self._extract_field(
            get_attr("features", []), "name",
        )
        # Components
        component_names = self._extract_field(
            get_attr("components", []), "name",
        )
        # Files
        file_paths = self._extract_field(
            get_attr("files", []), "path",
        )
        # Dependencies
        dependency_names = self._extract_field(
            get_attr("dependencies", []), "name",
        )
        # Stages
        stage_names = self._extract_field(
            get_attr("stages", []), "name",
        )
        # Expansion points
        expansion_areas = self._extract_field(
            get_attr("expansion_points", []), "area",
        )

        return ContextData(
            project_name=project_name,
            display_name=display_name,
            bot_type=bot_type,
            primary_goal=primary_goal,
            language=language,
            language_version=language_version,
            framework=framework,
            database=database,
            feature_names=feature_names,
            component_names=component_names,
            file_paths=file_paths,
            dependency_names=dependency_names,
            stage_names=stage_names,
            expansion_areas=expansion_areas,
            available=True,
        )

    @staticmethod
    def _extract_field(items: Any, attr: str) -> List[str]:
        """Extract the ``attr`` field from a list of objects/dicts."""
        if not isinstance(items, (list, tuple)):
            return []
        result: List[str] = []
        for item in items:
            value: Any = None
            if isinstance(item, dict):
                value = item.get(attr)
            elif hasattr(item, attr):
                value = getattr(item, attr)
            if value:
                result.append(str(value))
        return result


__all__ = ["ContextReader", "ContextData"]
