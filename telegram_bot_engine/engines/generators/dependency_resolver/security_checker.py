"""
Security Checker — flags security risks in the dependency list
(Specification 009).

The :class:`SecurityChecker` is a stateless helper that the
:class:`DependencyResolutionEngine` calls during the *security*
phase.  It analyses the list of :class:`DependencyEntry` objects and
flags security risks:

1. **Bad reputation.**  Flags dependencies with a reputation of
   ``"bad"`` — libraries with a known history of security issues,
   poor maintenance, or community distrust.
2. **Untrusted sources.**  Flags dependencies with a trust level of
   ``"untrusted"`` — libraries from unverified or untrusted sources.
3. **Known-vulnerable versions.**  Flags dependencies that are
   known to have security vulnerabilities in their suggested version
   (using a curated list of known-vulnerable versions).
4. **Unknown reputation.**  Flags dependencies with an unknown
   reputation as warnings — these have not been vetted.
5. **Unknown trust.**  Flags dependencies with an unknown trust
   level as warnings.

The security checker does **not** modify the dependencies — it only
records findings.

Data source
-----------
The security checker reads **only** the list of :class:`DependencyEntry`
objects.  It does **not** read the user's request.
"""

from __future__ import annotations

from typing import Dict, List, Set, Tuple

from .report_data import (
    DependencyEntry,
    ResolutionFinding,
    REPUTATION_BAD,
    REPUTATION_GOOD,
    REPUTATION_NEUTRAL,
    REPUTATION_UNKNOWN,
    SEVERITY_ERROR,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    STABILITY_ABANDONED,
    TRUST_OFFICIAL,
    TRUST_COMMUNITY,
    TRUST_UNTRUSTED,
    TRUST_UNKNOWN,
)


# ---------------------------------------------------------------------------#
# Known-vulnerable versions
# ---------------------------------------------------------------------------#
#
# A curated list of (library_name, vulnerable_version_range) pairs.  If
# a dependency's suggested_version matches one of these ranges, it is
# flagged as a known-vulnerable version.
#
# The version range is a simple string that is compared against the
# suggested_version using a lightweight matching rule:
#   * If the range starts with "==" the suggested_version must match
#     exactly.
#   * If the range starts with "<=" the suggested_version must be less
#     than or equal to the range version.
#   * If the range starts with "<" the suggested_version must be less
#     than the range version.
#   * Otherwise the range is treated as an exact match.
#
# This is a simplified check — a real implementation would use a
# proper vulnerability database (e.g. PyUp, Snyk, OSV).

_KNOWN_VULNERABLE_VERSIONS: List[Tuple[str, str, str]] = [
    # (library, vulnerable_range, description)
    ("python-telegram-bot", "<13.0", "Versions before 13.0 have known security issues."),
    ("aiohttp", "<3.7.4", "Versions before 3.7.4 have known security vulnerabilities."),
    ("requests", "<2.20.0", "Versions before 2.20.0 have known security vulnerabilities."),
    ("urllib3", "<1.24.2", "Versions before 1.24.2 have known security vulnerabilities."),
    ("cryptography", "<3.3.2", "Versions before 3.3.2 have known security vulnerabilities."),
    ("pyyaml", "<5.4", "Versions before 5.4 have known security vulnerabilities."),
    ("django", "<3.2.0", "Versions before 3.2 have known security vulnerabilities."),
    ("flask", "<1.0", "Versions before 1.0 have known security issues."),
    ("jinja2", "<2.11.3", "Versions before 2.11.3 have known security vulnerabilities."),
    ("sqlalchemy", "<1.3.0", "Versions before 1.3.0 have known security issues."),
    ("pillow", "<8.0.0", "Versions before 8.0.0 have known security vulnerabilities."),
    ("twisted", "<21.7", "Versions before 21.7 have known security vulnerabilities."),
]


# ---------------------------------------------------------------------------#
# Libraries with known bad reputation
# ---------------------------------------------------------------------------#
#
# A curated list of libraries that are known to have a bad reputation
# in the Python ecosystem.  These may be abandoned, insecure, or
# superseded by better alternatives.  If a dependency's reputation is
# not explicitly set (i.e. it is ``REPUTATION_UNKNOWN``), the checker
# consults this table to infer a bad reputation.

_LIBRARIES_BAD_REPUTATION: Set[str] = {
    # Examples of libraries with known issues (for illustration)
}


# ---------------------------------------------------------------------------#
# Libraries from untrusted sources
# ---------------------------------------------------------------------------#
#
# A curated list of libraries that come from untrusted or unverified
# sources.  If a dependency's trust is not explicitly set (i.e. it is
# ``TRUST_UNKNOWN``), the checker consults this table to infer an
# untrusted status.

_LIBRARIES_UNTRUSTED: Set[str] = {
    # Examples of untrusted libraries (for illustration)
}


class SecurityChecker:
    """Stateless helper that flags security risks in the dependency list.

    The security checker is called by the
    :class:`DependencyResolutionEngine` after the optimizer has run.
    It performs the security checks on the complete list of
    dependencies.

    The checker does **not** modify the dependencies — it only
    records findings.
    """

    def check(
        self,
        dependencies: List[DependencyEntry],
    ) -> List[ResolutionFinding]:
        """Check the dependency list for security risks.

        Parameters:
            dependencies: The list of :class:`DependencyEntry`
                objects to check.

        Returns:
            A list of :class:`ResolutionFinding` objects describing
            all security risks found.
        """
        findings: List[ResolutionFinding] = []

        findings.extend(self._check_bad_reputation(dependencies))
        findings.extend(self._check_untrusted_sources(dependencies))
        findings.extend(self._check_known_vulnerable_versions(dependencies))
        findings.extend(self._check_unknown_reputation(dependencies))
        findings.extend(self._check_unknown_trust(dependencies))
        findings.extend(self._check_abandoned_security(dependencies))

        return findings

    # -----------------------------------------------------------------#
    # Security checks
    # -----------------------------------------------------------------#

    @staticmethod
    def _check_bad_reputation(
        dependencies: List[DependencyEntry],
    ) -> List[ResolutionFinding]:
        """Flag dependencies with a bad reputation.

        A dependency with a reputation of ``"bad"`` is flagged as an
        error — it has a known history of security issues, poor
        maintenance, or community distrust.
        """
        findings: List[ResolutionFinding] = []

        for dep in dependencies:
            # Check explicit reputation.
            if dep.reputation == REPUTATION_BAD:
                findings.append(ResolutionFinding(
                    severity=SEVERITY_ERROR,
                    code="bad_reputation",
                    message=(
                        f"Dependency '{dep.name}' has a bad "
                        f"reputation.  This library has a known "
                        f"history of security issues, poor "
                        f"maintenance, or community distrust."
                    ),
                    affected=dep.name,
                    resolution_hint=(
                        f"Replace '{dep.name}' with a reputable "
                        f"alternative or verify that the current "
                        f"version is safe to use."
                    ),
                    category="security",
                ))
            # Check inferred reputation from the table.
            elif (
                dep.reputation == REPUTATION_UNKNOWN
                and dep.name.lower() in _LIBRARIES_BAD_REPUTATION
            ):
                findings.append(ResolutionFinding(
                    severity=SEVERITY_ERROR,
                    code="bad_reputation_inferred",
                    message=(
                        f"Dependency '{dep.name}' appears in the "
                        f"known-bad-reputation list but its "
                        f"reputation was not explicitly set."
                    ),
                    affected=dep.name,
                    resolution_hint=(
                        f"Replace '{dep.name}' with a reputable "
                        f"alternative."
                    ),
                    category="security",
                ))

        return findings

    @staticmethod
    def _check_untrusted_sources(
        dependencies: List[DependencyEntry],
    ) -> List[ResolutionFinding]:
        """Flag dependencies from untrusted sources.

        A dependency with a trust level of ``"untrusted"`` is flagged
        as an error — it comes from an unverified or untrusted source.
        """
        findings: List[ResolutionFinding] = []

        for dep in dependencies:
            # Check explicit trust.
            if dep.trust == TRUST_UNTRUSTED:
                findings.append(ResolutionFinding(
                    severity=SEVERITY_ERROR,
                    code="untrusted_source",
                    message=(
                        f"Dependency '{dep.name}' comes from an "
                        f"untrusted source.  Untrusted libraries "
                        f"may contain malicious code or "
                        f"backdoors."
                    ),
                    affected=dep.name,
                    resolution_hint=(
                        f"Replace '{dep.name}' with a trusted "
                        f"alternative from an official or "
                        f"community-verified source."
                    ),
                    category="security",
                ))
            # Check inferred trust from the table.
            elif (
                dep.trust == TRUST_UNKNOWN
                and dep.name.lower() in _LIBRARIES_UNTRUSTED
            ):
                findings.append(ResolutionFinding(
                    severity=SEVERITY_ERROR,
                    code="untrusted_source_inferred",
                    message=(
                        f"Dependency '{dep.name}' appears in the "
                        f"untrusted-source list but its trust "
                        f"level was not explicitly set."
                    ),
                    affected=dep.name,
                    resolution_hint=(
                        f"Replace '{dep.name}' with a trusted "
                        f"alternative."
                    ),
                    category="security",
                ))

        return findings

    @staticmethod
    def _check_known_vulnerable_versions(
        dependencies: List[DependencyEntry],
    ) -> List[ResolutionFinding]:
        """Flag dependencies with known-vulnerable versions.

        Checks each dependency's suggested_version against a curated
        list of known-vulnerable version ranges.
        """
        findings: List[ResolutionFinding] = []

        for dep in dependencies:
            for lib_name, version_range, description in _KNOWN_VULNERABLE_VERSIONS:
                if dep.name.lower() != lib_name.lower():
                    continue

                if SecurityChecker._is_version_vulnerable(
                    dep.suggested_version, version_range,
                ):
                    findings.append(ResolutionFinding(
                        severity=SEVERITY_ERROR,
                        code="known_vulnerable_version",
                        message=(
                            f"Dependency '{dep.name}' version "
                            f"'{dep.suggested_version}' is "
                            f"known to be vulnerable.  {description}"
                        ),
                        affected=dep.name,
                        resolution_hint=(
                            f"Upgrade '{dep.name}' to a version "
                            f"outside the vulnerable range "
                            f"'{version_range}'."
                        ),
                        category="security",
                    ))

        return findings

    @staticmethod
    def _check_unknown_reputation(
        dependencies: List[DependencyEntry],
    ) -> List[ResolutionFinding]:
        """Flag dependencies with an unknown reputation as warnings.

        Dependencies with an unknown reputation have not been vetted
        and should be reviewed before use.
        """
        findings: List[ResolutionFinding] = []

        for dep in dependencies:
            if dep.reputation == REPUTATION_UNKNOWN:
                findings.append(ResolutionFinding(
                    severity=SEVERITY_WARNING,
                    code="unknown_reputation",
                    message=(
                        f"Dependency '{dep.name}' has an unknown "
                        f"reputation.  It has not been vetted for "
                        f"security or community trust."
                    ),
                    affected=dep.name,
                    resolution_hint=(
                        f"Research '{dep.name}' to confirm its "
                        f"reputation before using it in production."
                    ),
                    category="security",
                ))

        return findings

    @staticmethod
    def _check_unknown_trust(
        dependencies: List[DependencyEntry],
    ) -> List[ResolutionFinding]:
        """Flag dependencies with an unknown trust level as warnings.

        Dependencies with an unknown trust level have not been
        verified and should be reviewed before use.
        """
        findings: List[ResolutionFinding] = []

        for dep in dependencies:
            if dep.trust == TRUST_UNKNOWN:
                findings.append(ResolutionFinding(
                    severity=SEVERITY_WARNING,
                    code="unknown_trust",
                    message=(
                        f"Dependency '{dep.name}' has an unknown "
                        f"trust level.  Its source has not been "
                        f"verified."
                    ),
                    affected=dep.name,
                    resolution_hint=(
                        f"Verify the source of '{dep.name}' before "
                        f"using it in production."
                    ),
                    category="security",
                ))

        return findings

    @staticmethod
    def _check_abandoned_security(
        dependencies: List[DependencyEntry],
    ) -> List[ResolutionFinding]:
        """Flag abandoned dependencies as security risks.

        Abandoned dependencies are no longer maintained and may
        contain unpatched security vulnerabilities.
        """
        findings: List[ResolutionFinding] = []

        for dep in dependencies:
            if dep.stability == STABILITY_ABANDONED:
                findings.append(ResolutionFinding(
                    severity=SEVERITY_ERROR,
                    code="abandoned_security_risk",
                    message=(
                        f"Dependency '{dep.name}' is abandoned.  "
                        f"Abandoned libraries are no longer "
                        f"maintained and may contain unpatched "
                        f"security vulnerabilities."
                    ),
                    affected=dep.name,
                    resolution_hint=(
                        f"Replace '{dep.name}' with a maintained "
                        f"alternative."
                    ),
                    category="security",
                ))

        return findings

    # -----------------------------------------------------------------#
    # Helpers
    # -----------------------------------------------------------------#

    @staticmethod
    def _is_version_vulnerable(
        suggested_version: str,
        vulnerable_range: str,
    ) -> bool:
        """Check if a suggested version falls within a vulnerable range.

        This is a simplified version comparison.  It handles the
        following range formats:

        * ``"==X.Y.Z"`` — exact match.
        * ``"<=X.Y.Z"`` — less than or equal.
        * ``"<X.Y.Z"`` — strictly less than.
        * ``"X.Y.Z"`` — treated as exact match.

        For versions that cannot be parsed (e.g. ``"latest"``), the
        method returns ``False`` (no vulnerability flag).
        """
        if not suggested_version or not vulnerable_range:
            return False

        # Normalise the suggested version — strip common prefixes.
        suggested = SecurityChecker._normalise_version(suggested_version)
        if suggested is None:
            return False

        range_str = vulnerable_range.strip()

        if range_str.startswith("=="):
            threshold = SecurityChecker._normalise_version(range_str[2:])
            if threshold is None:
                return False
            return suggested == threshold

        if range_str.startswith("<="):
            threshold = SecurityChecker._normalise_version(range_str[2:])
            if threshold is None:
                return False
            return suggested <= threshold

        if range_str.startswith("<"):
            threshold = SecurityChecker._normalise_version(range_str[1:])
            if threshold is None:
                return False
            return suggested < threshold

        # No prefix — exact match.
        threshold = SecurityChecker._normalise_version(range_str)
        if threshold is None:
            return False
        return suggested == threshold

    @staticmethod
    def _normalise_version(version: str) -> Tuple[int, ...] | None:
        """Parse a version string into a comparable tuple.

        Extracts the leading numeric components from a version string
        and returns them as a tuple of integers.  Returns ``None`` if
        the version cannot be parsed.

        Examples:
            ``"2.1.3"`` -> ``(2, 1, 3)``
            ``">=2.0,<3.0"`` -> ``(2, 0)`` (first constraint)
            ``"21.x"`` -> ``(21,)``
            ``"latest"`` -> ``None``
        """
        if not version:
            return None

        # Strip common prefixes.
        cleaned = version.strip()
        for prefix in (">=", "<=", "==", ">", "<", "~=", "^"):
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):]
                break

        # Take the first constraint if there are multiple.
        if "," in cleaned:
            cleaned = cleaned.split(",")[0]

        # Strip non-numeric suffixes (e.g. "x", "rc1", "a1").
        parts: List[int] = []
        for part in cleaned.split("."):
            # Extract the leading numeric portion.
            numeric = ""
            for ch in part:
                if ch.isdigit():
                    numeric += ch
                else:
                    break
            if numeric:
                parts.append(int(numeric))
            else:
                break

        if not parts:
            return None

        return tuple(parts)


__all__ = ["SecurityChecker"]
