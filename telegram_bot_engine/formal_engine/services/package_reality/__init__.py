"""Package Reality Engine — live ecosystem truth for Python bot dependencies."""

from .service import (
    PackageRealityEngine,
    PackageHealthReport,
    PackageStatus,
    assess_repo_packages,
)

__all__ = [
    "PackageRealityEngine",
    "PackageHealthReport",
    "PackageStatus",
    "assess_repo_packages",
]
