"""
ResourceEstimator — Specification 017

Estimates the resources the project will consume: files, directories,
total project size, database size, memory consumption, CPU
consumption, and runtime resources (build time, test time).

The resource estimator does not write code, create files, or make
build decisions.  It only estimates and classifies the resource
requirements.
"""

from __future__ import annotations

import logging
from typing import List

from .data_readers import (
    ArchitectureDecisionData,
    TechnologySelectionData,
    RequirementNormalizationData,
    IntelligenceGraphData,
    KnowledgeData,
)
from .report_data import (
    ResourceEstimation,
    CapabilityFinding,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    SIZE_TINY,
    SIZE_SMALL,
    SIZE_MEDIUM,
    SIZE_LARGE,
    SIZE_VERY_LARGE,
    SIZE_THRESHOLD_TINY,
    SIZE_THRESHOLD_SMALL,
    SIZE_THRESHOLD_MEDIUM,
    SIZE_THRESHOLD_LARGE,
)

_log = logging.getLogger("engine.capability_analyzer.resources")


class ResourceEstimator:
    """Estimates the resources the project will consume.

    Estimates files, directories, project size, database size,
    memory, CPU, and runtime resources based on the architectural
    elements, technology selections, and requirements.
    """

    def __init__(self) -> None:
        self.findings: List[CapabilityFinding] = []

    def estimate(
        self,
        arch_data: ArchitectureDecisionData,
        tech_data: TechnologySelectionData,
        req_data: RequirementNormalizationData,
        graph_data: IntelligenceGraphData,
        kb_data: KnowledgeData,
    ) -> ResourceEstimation:
        """Perform the resource estimation.

        Args:
            arch_data: Architecture decision data.
            tech_data: Technology selection data.
            req_data: Requirement normalization data.
            graph_data: Intelligence graph data.
            kb_data: Knowledge base data.

        Returns:
            A :class:`ResourceEstimation` instance.
        """
        self.findings = []

        # ---- File count ----
        file_count = self._estimate_file_count(
            arch_data, graph_data, req_data
        )

        # ---- Directory count ----
        directory_count = self._estimate_directory_count(
            arch_data, file_count
        )

        # ---- Project size (KB) ----
        project_size_kb = self._estimate_project_size(file_count)

        # ---- Database size (MB) ----
        database_size_mb = self._estimate_database_size(req_data)

        # ---- Memory (MB) ----
        memory_mb = self._estimate_memory(
            tech_data, graph_data, file_count
        )

        # ---- CPU cores ----
        cpu_cores = self._estimate_cpu(
            tech_data, graph_data, req_data
        )

        # ---- Build time ----
        build_time = self._estimate_build_time(file_count)

        # ---- Test time ----
        test_time = self._estimate_test_time(file_count)

        # ---- Size level ----
        size_level = self._classify_size(file_count)

        # ---- Score (0.0-1.0, higher = more resources) ----
        score = self._calculate_score(file_count)

        # ---- Summary and details ----
        details = [
            f"{file_count} files (estimated)",
            f"{directory_count} directories (estimated)",
            f"{project_size_kb} KB project size (estimated)",
            f"{database_size_mb} MB database size (estimated)",
            f"{memory_mb} MB memory (estimated)",
            f"{cpu_cores} CPU cores (estimated)",
            f"{build_time:.1f} min build time (estimated)",
            f"{test_time:.1f} min test time (estimated)",
        ]

        summary = (
            f"Project size: {size_level} "
            f"({file_count} files, {project_size_kb} KB)."
        )

        # ---- Findings ----
        if file_count > SIZE_THRESHOLD_LARGE:
            self.findings.append(CapabilityFinding(
                severity=SEVERITY_WARNING,
                code="large_project_resources",
                message=(
                    f"Project is very large ({file_count} files, "
                    f"{project_size_kb} KB). This will require "
                    f"significant build and test time."
                ),
                affected="resources",
                resolution_hint=(
                    "Consider incremental builds and parallel "
                    "test execution."
                ),
                category="resources",
            ))
        elif file_count == 0:
            self.findings.append(CapabilityFinding(
                severity=SEVERITY_INFO,
                code="no_resource_data",
                message=(
                    "No files detected. Resource estimation "
                    "is based on defaults."
                ),
                affected="resources",
                resolution_hint=(
                    "Ensure the architecture decision and "
                    "intelligence graph are available."
                ),
                category="resources",
            ))

        return ResourceEstimation(
            file_count=file_count,
            directory_count=directory_count,
            project_size_kb=project_size_kb,
            database_size_mb=database_size_mb,
            memory_mb=memory_mb,
            cpu_cores=cpu_cores,
            estimated_build_time_minutes=build_time,
            estimated_test_time_minutes=test_time,
            project_size_level=size_level,
            score=score,
            summary=summary,
            details=details,
        )

    # ----------------------------------------------------------------- #
    # Private helpers
    # ----------------------------------------------------------------- #

    def _estimate_file_count(
        self,
        arch_data: ArchitectureDecisionData,
        graph_data: IntelligenceGraphData,
        req_data: RequirementNormalizationData,
    ) -> int:
        """Estimate the number of files.

        Files are estimated from modules, services, components, and
        requirements.  Each module produces ~3-8 files, each service
        ~5-12 files, each component ~2-4 files, and each requirement
        ~1-2 files.
        """
        module_files = arch_data.module_count * 6
        service_files = arch_data.service_count * 8
        component_files = graph_data.component_count * 3
        req_files = req_data.requirement_count * 2

        # Base files: configuration, tests, docs, etc.
        base_files = 10

        total = (
            module_files + service_files + component_files
            + req_files + base_files
        )
        return total

    def _estimate_directory_count(
        self,
        arch_data: ArchitectureDecisionData,
        file_count: int,
    ) -> int:
        """Estimate the number of directories.

        Directories are estimated from modules, services, and a
        rough ratio of files per directory (~5-8 files per dir).
        """
        module_dirs = arch_data.module_count
        service_dirs = arch_data.service_count
        # Each layer typically has its own directory.
        layer_dirs = max(len(arch_data.layers), 1)

        # Estimate from file count: ~6 files per directory.
        file_dirs = max(file_count // 6, 1)

        total = module_dirs + service_dirs + layer_dirs + file_dirs
        return max(total, 5)  # At least 5 base directories.

    def _estimate_project_size(self, file_count: int) -> int:
        """Estimate the total project size in KB.

        Average file size is ~5 KB (mix of Python, config, docs).
        """
        return file_count * 5

    def _estimate_database_size(
        self,
        req_data: RequirementNormalizationData,
    ) -> int:
        """Estimate the database size in MB.

        Database size depends on the number of requirements (which
        roughly correlates with the number of tables/entities).
        Each entity with a moderate user base needs ~10-50 MB.
        """
        entity_count = max(req_data.requirement_count, 1)
        return entity_count * 20  # 20 MB per entity.

    def _estimate_memory(
        self,
        tech_data: TechnologySelectionData,
        graph_data: IntelligenceGraphData,
        file_count: int,
    ) -> int:
        """Estimate the runtime memory consumption in MB.

        Memory depends on the number of loaded modules, technologies,
        and the number of components in the graph.
        """
        # Base memory for a Python process: ~50 MB.
        base = 50

        # Each technology selection adds ~10-30 MB.
        tech_memory = tech_data.selection_count * 15

        # Each component in the graph adds ~2-5 MB.
        component_memory = graph_data.component_count * 3

        # File count contributes ~0.1 MB per file.
        file_memory = file_count // 10

        return base + tech_memory + component_memory + file_memory

    def _estimate_cpu(
        self,
        tech_data: TechnologySelectionData,
        graph_data: IntelligenceGraphData,
        req_data: RequirementNormalizationData,
    ) -> float:
        """Estimate the CPU cores needed.

        CPU depends on the number of background tasks, components,
        and the concurrency requirements.
        """
        # Base: 1 core for a single-threaded bot.
        base = 1.0

        # Each technology that implies a background service adds
        # ~0.5 cores.
        for tech_name in tech_data.selected_technologies:
            name_lower = tech_name.lower()
            if any(
                kw in name_lower
                for kw in ("redis", "rabbitmq", "kafka", "celery")
            ):
                base += 0.5

        # High concurrency requirements add more cores.
        for req in req_data.non_functional:
            if isinstance(req, dict):
                desc = str(req.get("description", "")).lower()
                name = str(req.get("name", "")).lower()
                if "concurr" in desc or "concurr" in name:
                    base += 0.5
                if "realtime" in desc or "realtime" in name:
                    base += 0.5

        return base

    def _estimate_build_time(self, file_count: int) -> float:
        """Estimate the build time in minutes.

        Build time is roughly proportional to file count.
        ~0.02 minutes per file (1.2 seconds).
        """
        return file_count * 0.02

    def _estimate_test_time(self, file_count: int) -> float:
        """Estimate the test time in minutes.

        Test time is roughly proportional to file count.
        ~0.05 minutes per file (3 seconds).
        """
        return file_count * 0.05

    def _classify_size(self, file_count: int) -> str:
        """Classify the project size by file count.

        Args:
            file_count: The estimated number of files.

        Returns:
            The size level string.
        """
        if file_count <= SIZE_THRESHOLD_TINY:
            return SIZE_TINY
        if file_count <= SIZE_THRESHOLD_SMALL:
            return SIZE_SMALL
        if file_count <= SIZE_THRESHOLD_MEDIUM:
            return SIZE_MEDIUM
        if file_count <= SIZE_THRESHOLD_LARGE:
            return SIZE_LARGE
        return SIZE_VERY_LARGE

    def _calculate_score(self, file_count: int) -> float:
        """Calculate the resource score (0.0-1.0).

        Higher score means more resources needed.

        Args:
            file_count: The estimated number of files.

        Returns:
            The resource score.
        """
        if file_count <= 0:
            return 0.0
        # Logarithmic scale: score = log10(file_count + 1) / 3.
        import math
        score = math.log10(file_count + 1) / 3.0
        return max(0.0, min(1.0, score))


__all__ = ["ResourceEstimator"]
