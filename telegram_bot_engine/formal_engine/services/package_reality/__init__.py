"""Package Reality Engine — live ecosystem truth for Python bot dependencies."""

from .service import (
    PackageRealityEngine,
    PackageHealthReport,
    PackageStatus,
    UpgradeRecommendation,
    assess_repo_packages,
    recommend_upgrades,
    apply_safe_upgrades,
    format_recommendations,
)

__all__ = [
    "PackageRealityEngine",
    "PackageHealthReport",
    "PackageStatus",
    "UpgradeRecommendation",
    "assess_repo_packages",
    "recommend_upgrades",
    "apply_safe_upgrades",
    "format_recommendations",
]
