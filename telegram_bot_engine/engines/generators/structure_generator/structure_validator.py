"""
Structure Validator — validates the project structure map before the
engine finishes (Specification 006).

The :class:`StructureValidator` is a stateless helper that performs the
final validation checks mandated by the specification:

* **No duplicate folders** — every folder path must be unique.
* **No duplicate files** — every file path must be unique.
* **No conflicting names** — no folder and file share the same path.
* **No empty folders without reason** — every folder must either have a
  reason or contain files/subfolders.
* **No files without responsibility** — every file must have a purpose.
* **No orphan folders** — every folder's parent must exist (except the
  root).
* **No orphan files** — every file's folder must exist in the folder
  map (except root-level files).
* **No conflicting component-to-folder mappings** — every mapped
  component folder must exist.

The validator does **not** modify the structure map.  It returns a
:class:`StructureValidationReport` with a list of errors and warnings.
When the report has no errors, the structure map is valid.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .structure_map import ProjectStructureMap


# ---------------------------------------------------------------------------#
# Validation result
# ---------------------------------------------------------------------------#

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"


@dataclass
class StructureIssue:
    """A single issue found during structure validation.

    Attributes:
        severity: ``"error"`` or ``"warning"``.
        code: A short, machine-readable code (e.g.
            ``"duplicate_folder"``).
        message: A human-readable description.
        path: The affected path (folder or file path).
    """

    severity: str = SEVERITY_ERROR
    code: str = ""
    message: str = ""
    path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "path": self.path,
        }


@dataclass
class StructureValidationReport:
    """The complete validation report for a structure map.

    Attributes:
        valid: ``True`` when no errors were found.
        issues: The list of :class:`StructureIssue` objects.
        error_count: The number of error-severity issues.
        warning_count: The number of warning-severity issues.
        summary: A human-readable summary.
    """

    valid: bool = True
    issues: List[StructureIssue] = field(default_factory=list)
    error_count: int = 0
    warning_count: int = 0
    summary: str = ""

    @property
    def has_errors(self) -> bool:
        return self.error_count > 0

    @property
    def has_warnings(self) -> bool:
        return self.warning_count > 0

    def add_error(self, code: str, message: str, path: str = "") -> None:
        self.issues.append(StructureIssue(
            severity=SEVERITY_ERROR, code=code,
            message=message, path=path,
        ))
        self.valid = False
        self.error_count += 1

    def add_warning(self, code: str, message: str, path: str = "") -> None:
        self.issues.append(StructureIssue(
            severity=SEVERITY_WARNING, code=code,
            message=message, path=path,
        ))
        self.warning_count += 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "summary": self.summary,
            "issues": [i.to_dict() for i in self.issues],
        }


# ---------------------------------------------------------------------------#
# The validator
# ---------------------------------------------------------------------------#

class StructureValidator:
    """Stateless helper that validates a :class:`ProjectStructureMap`.

    The validator runs a series of checks and returns a
    :class:`StructureValidationReport`.  It does not modify the structure
    map.
    """

    def validate(self, structure_map: ProjectStructureMap) -> StructureValidationReport:
        """Validate the structure map and return a report.

        Parameters:
            structure_map: The structure map to validate.

        Returns:
            A :class:`StructureValidationReport`.  ``valid`` is ``True``
            when no errors were found.
        """
        report = StructureValidationReport()

        self._check_duplicate_folders(structure_map, report)
        self._check_duplicate_files(structure_map, report)
        self._check_conflicting_names(structure_map, report)
        self._check_empty_folders(structure_map, report)
        self._check_files_without_purpose(structure_map, report)
        self._check_orphan_folders(structure_map, report)
        self._check_orphan_files(structure_map, report)
        self._check_component_to_folder(structure_map, report)
        self._check_root_package(structure_map, report)

        report.summary = self._build_summary(report)
        return report

    # ------------------------------------------------------------------#
    # Individual checks
    # ------------------------------------------------------------------#

    @staticmethod
    def _check_duplicate_folders(structure_map: ProjectStructureMap,
                                  report: StructureValidationReport) -> None:
        """Check for duplicate folder paths."""
        seen: Dict[str, int] = {}
        for folder in structure_map.folders:
            seen[folder.path] = seen.get(folder.path, 0) + 1
        for path, count in seen.items():
            if count > 1:
                report.add_error(
                    code="duplicate_folder",
                    message=(
                        f"Duplicate folder path '{path}' appears "
                        f"{count} times."
                    ),
                    path=path,
                )

    @staticmethod
    def _check_duplicate_files(structure_map: ProjectStructureMap,
                                report: StructureValidationReport) -> None:
        """Check for duplicate file paths."""
        seen: Dict[str, int] = {}
        for file in structure_map.files:
            seen[file.path] = seen.get(file.path, 0) + 1
        for path, count in seen.items():
            if count > 1:
                report.add_error(
                    code="duplicate_file",
                    message=(
                        f"Duplicate file path '{path}' appears "
                        f"{count} times."
                    ),
                    path=path,
                )

    @staticmethod
    def _check_conflicting_names(structure_map: ProjectStructureMap,
                                  report: StructureValidationReport) -> None:
        """Check that no folder and file share the same path."""
        folder_paths = set(structure_map.folder_paths())
        file_paths = set(structure_map.file_paths())
        conflicts = folder_paths & file_paths
        for path in sorted(conflicts):
            report.add_error(
                code="conflicting_name",
                message=(
                    f"Path '{path}' is both a folder and a file."
                ),
                path=path,
            )

    @staticmethod
    def _check_empty_folders(structure_map: ProjectStructureMap,
                              report: StructureValidationReport) -> None:
        """Check for folders that have no files, no subfolders, and no reason."""
        folder_paths = set(structure_map.folder_paths())
        file_folders = {f.folder for f in structure_map.files if f.folder}
        # Build a set of folders that have subfolders.
        for folder in structure_map.folders:
            has_files = folder.path in file_folders
            has_subfolders = bool(folder.subfolders)
            has_reason = bool(folder.reason)
            if not has_files and not has_subfolders and not has_reason:
                report.add_warning(
                    code="empty_folder",
                    message=(
                        f"Folder '{folder.path}' has no files, no "
                        f"subfolders, and no reason."
                    ),
                    path=folder.path,
                )

    @staticmethod
    def _check_files_without_purpose(structure_map: ProjectStructureMap,
                                      report: StructureValidationReport) -> None:
        """Check for files that have no purpose."""
        for file in structure_map.files:
            if not file.purpose or not file.purpose.strip():
                report.add_error(
                    code="file_without_purpose",
                    message=(
                        f"File '{file.path}' has no purpose."
                    ),
                    path=file.path,
                )

    @staticmethod
    def _check_orphan_folders(structure_map: ProjectStructureMap,
                               report: StructureValidationReport) -> None:
        """Check that every folder's parent exists (except the root)."""
        folder_paths = set(structure_map.folder_paths())
        for folder in structure_map.folders:
            if folder.parent and folder.parent not in folder_paths:
                report.add_error(
                    code="orphan_folder",
                    message=(
                        f"Folder '{folder.path}' has parent "
                        f"'{folder.parent}' which does not exist in the "
                        f"folder map."
                    ),
                    path=folder.path,
                )

    @staticmethod
    def _check_orphan_files(structure_map: ProjectStructureMap,
                             report: StructureValidationReport) -> None:
        """Check that every file's folder exists in the folder map."""
        folder_paths = set(structure_map.folder_paths())
        for file in structure_map.files:
            if file.folder and file.folder not in folder_paths:
                report.add_error(
                    code="orphan_file",
                    message=(
                        f"File '{file.path}' is in folder "
                        f"'{file.folder}' which does not exist in the "
                        f"folder map."
                    ),
                    path=file.path,
                )

    @staticmethod
    def _check_component_to_folder(structure_map: ProjectStructureMap,
                                    report: StructureValidationReport) -> None:
        """Check that every component-to-folder mapping points to an existing folder."""
        folder_paths = set(structure_map.folder_paths())
        for component, folder_path in structure_map.component_to_folder.items():
            if folder_path not in folder_paths:
                report.add_error(
                    code="invalid_component_folder",
                    message=(
                        f"Component '{component}' maps to folder "
                        f"'{folder_path}' which does not exist."
                    ),
                    path=folder_path,
                )

    @staticmethod
    def _check_root_package(structure_map: ProjectStructureMap,
                             report: StructureValidationReport) -> None:
        """Check that the root package folder exists and matches the project name."""
        if not structure_map.project_name:
            report.add_error(
                code="missing_project_name",
                message="The structure map has no project name.",
            )
            return

        root_exists = any(
            f.path == structure_map.root_path for f in structure_map.folders
        )
        if not root_exists:
            report.add_error(
                code="missing_root_folder",
                message=(
                    f"The root package folder '{structure_map.root_path}' "
                    f"does not exist in the folder map."
                ),
                path=structure_map.root_path,
            )

    # ------------------------------------------------------------------#
    # Summary
    # ------------------------------------------------------------------#

    @staticmethod
    def _build_summary(report: StructureValidationReport) -> str:
        """Build a human-readable summary of the validation."""
        if report.valid:
            return (
                f"VALID — {report.warning_count} warning(s), "
                f"no errors."
            )
        return (
            f"INVALID — {report.error_count} error(s), "
            f"{report.warning_count} warning(s)."
        )


__all__ = [
    "StructureValidator",
    "StructureValidationReport",
    "StructureIssue",
]
