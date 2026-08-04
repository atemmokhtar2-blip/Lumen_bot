"""Intelligent File System Engine package (Specification 048)."""

from .file_system_engine import FileSystemEngine
from .report_data import (
    FileSystemReport, FileOperation, PathCheck, PermissionCheck,
    BackupRecord, IntegrityResult, DuplicateInfo, FSFinding,
    CacheInfo, FSProvenance,
    ALL_SOURCES, ALL_QUALITY_RULES, ALL_VERDICTS, ALL_OPERATIONS,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY, VERDICT_DENIED,
)

__all__ = [
    "FileSystemEngine",
    "FileSystemReport",
    "FileOperation",
    "PathCheck",
    "PermissionCheck",
    "BackupRecord",
    "IntegrityResult",
    "DuplicateInfo",
    "FSFinding",
    "CacheInfo",
    "FSProvenance",
    "ALL_SOURCES",
    "ALL_QUALITY_RULES",
    "ALL_VERDICTS",
    "ALL_OPERATIONS",
    "VERDICT_READY",
    "VERDICT_READY_WITH_WARNINGS",
    "VERDICT_NOT_READY",
    "VERDICT_DENIED",
]
