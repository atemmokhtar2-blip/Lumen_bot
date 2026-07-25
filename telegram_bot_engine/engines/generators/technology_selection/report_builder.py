"""
ReportBuilder — Specification 016

Builds the Technology Selection Report containing:
    - Selected technologies
    - Selection reasons
    - Alternatives
    - Pros and cons of each decision
"""

from __future__ import annotations


class ReportBuilder:
    """Builds the Technology Selection Report."""

    def build(self, selected, alternatives):
        """Build the Technology Selection Report.

        Args:
            selected: dict mapping technology category to the chosen technology.
            alternatives: dict mapping technology category to alternative candidates.

        Returns:
            Technology Selection Report.

        Raises:
            NotImplementedError: Implementation deferred until Spec 017.
        """
        raise NotImplementedError(
            "ReportBuilder.build() — "
            "implementation deferred until Specification 017."
        )
