"""Compatibility shim — use lumen.platform.entitlement."""
from lumen.platform.entitlement import *  # noqa: F403
from lumen.platform.entitlement import (  # noqa: F401
    PlanLimits,
    ProEntitlement,
    resolve_plan_limits,
    resolve_pro_entitlement,
)
