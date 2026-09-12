"""Ready-made bot templates (bounded context).

Phase 0–1: catalog + policy + store only. UI and hosting adapters come later.
"""
from lumen.templates.catalog import get_template, list_templates
from lumen.templates.models import (
    TemplateInstance,
    TemplateInstanceStatus,
    TemplateLaunchMode,
    TemplateSpec,
)
from lumen.templates.policy import (
    FREE_MAX_RUNNING_TEMPLATES,
    PERMANENT_TTL_DAYS,
    TRIAL_MAX_MINUTES,
    can_launch,
    clamp_trial_minutes,
)
from lumen.templates.store import list_instances, reserve_instance

__all__ = [
    "TemplateSpec",
    "TemplateInstance",
    "TemplateInstanceStatus",
    "TemplateLaunchMode",
    "list_templates",
    "get_template",
    "FREE_MAX_RUNNING_TEMPLATES",
    "TRIAL_MAX_MINUTES",
    "PERMANENT_TTL_DAYS",
    "can_launch",
    "clamp_trial_minutes",
    "list_instances",
    "reserve_instance",
]
