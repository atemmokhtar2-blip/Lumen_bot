"""QualityGate — Specification 030"""

from __future__ import annotations

from typing import List, Tuple

from .report_data import (
    InitializedProjectReport, BuildFinding,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM,
    RULE_PROJECT_INITIALIZED, RULE_FOLDERS_CREATED, RULE_FILES_CREATED,
    RULE_NO_DUPLICATES, RULE_MANIFEST_COMPLETE, RULE_SUFFICIENT_CONFIDENCE,
    ALL_QUALITY_RULES, CONFLICT_DUPLICATE_PATH, CONFLICT_EMPTY_PROJECT,
    CONFIDENCE_MEDIUM_THRESHOLD,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY,
)


class QualityGate:
    def validate(self, report: InitializedProjectReport) -> Tuple[List[BuildFinding], bool, str]:
        findings: List[BuildFinding] = []
        critical = False
        warnings = 0

        if report.is_empty:
            findings.append(BuildFinding(
                severity=SEVERITY_CRITICAL, code="empty_report",
                message="Initialized Project Report is empty.",
                affected="report", category="quality",
            ))
            return findings, False, VERDICT_NOT_READY

        for rule in ALL_QUALITY_RULES:
            ok = True
            if rule == RULE_PROJECT_INITIALIZED:
                if not report.identity.project_id:
                    findings.append(BuildFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Project identity not initialized.",
                        affected="identity", category="init"))
                    ok = False
            elif rule == RULE_FOLDERS_CREATED:
                if report.folder_count == 0:
                    findings.append(BuildFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="No folders scaffolded.",
                        affected="folders", category="structure"))
                    ok = False
            elif rule == RULE_FILES_CREATED:
                if report.file_count == 0:
                    findings.append(BuildFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="No files scaffolded.",
                        affected="files", category="structure"))
                    ok = False
            elif rule == RULE_NO_DUPLICATES:
                dups = [c for c in report.conflicts if c.conflict_type == CONFLICT_DUPLICATE_PATH]
                # Duplicates were collapsed — warn only if many
                if len(dups) > 5:
                    findings.append(BuildFinding(
                        severity=SEVERITY_MEDIUM, code=rule,
                        message=f"{len(dups)} duplicate path(s) were collapsed.",
                        affected="paths", category="structure"))
                    ok = False
            elif rule == RULE_MANIFEST_COMPLETE:
                if not report.manifest.files and not report.manifest.folders:
                    findings.append(BuildFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Manifest is empty.",
                        affected="manifest", category="manifest"))
                    ok = False
            elif rule == RULE_SUFFICIENT_CONFIDENCE:
                if report.provenance.confidence < CONFIDENCE_MEDIUM_THRESHOLD:
                    findings.append(BuildFinding(
                        severity=SEVERITY_MEDIUM, code=rule,
                        message=f"Confidence {report.provenance.confidence:.2f} below threshold.",
                        affected="provenance", category="quality"))
                    ok = False

            if not ok:
                if rule in (RULE_PROJECT_INITIALIZED, RULE_FOLDERS_CREATED,
                            RULE_FILES_CREATED, RULE_MANIFEST_COMPLETE):
                    critical = True
                else:
                    warnings += 1

        empty = [c for c in report.conflicts if c.conflict_type == CONFLICT_EMPTY_PROJECT]
        if empty:
            critical = True
            findings.append(BuildFinding(
                severity=SEVERITY_CRITICAL, code="empty_project",
                message="Project scaffold is empty.",
                affected="project", category="structure"))

        if critical:
            return findings, False, VERDICT_NOT_READY
        if warnings:
            return findings, True, VERDICT_READY_WITH_WARNINGS
        return findings, True, VERDICT_READY


__all__ = ["QualityGate"]
