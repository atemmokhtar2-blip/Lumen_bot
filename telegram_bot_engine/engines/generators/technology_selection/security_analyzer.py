"""
SecurityAnalyzer — Specification 016

Verifies each candidate technology for:
    - Known insecure libraries
    - Deprecated / abandoned libraries
    - Known vulnerabilities (CVEs)
"""

from __future__ import annotations


class SecurityAnalyzer:
    """Analyzes security characteristics of candidate technologies."""

    def analyze(self, candidates):
        """Analyze security of the given candidate technologies.

        Args:
            candidates: dict mapping technology category to candidate list.

        Returns:
            Security analysis result.

        Raises:
            NotImplementedError: Implementation deferred until Spec 017.
        """
        raise NotImplementedError(
            "SecurityAnalyzer.analyze() — "
            "implementation deferred until Specification 017."
        )
