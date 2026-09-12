"""Ready-made bot templates — bounded context (hexagonal).

Layering
--------
ports.py      Protocols only (Catalog / Store)
models.py     Immutable domain types
policy.py     Pure decisions (no I/O)
catalog.py    JSON adapter
store_*       Memory / Redis adapters
service.py    Application use-cases

Forbidden imports from this package: lumen.bot.*, hosting side-effects.
UI (Phase 2) and hosting adapter (Phase 3–4) live outside and call TemplateService.
"""
from lumen.templates.catalog import get_template, list_templates
from lumen.templates.models import (
    TemplateInstance,
    TemplateInstanceStatus,
    TemplateLaunchMode,
    TemplateSpec,
)
from lumen.templates.policy import (
    FREE_MAX_RUNNING,
    FREE_MAX_RUNNING_TEMPLATES,
    PERMANENT_TTL_DAYS,
    TRIAL_MAX_MINUTES,
    evaluate_launch,
    clamp_trial_minutes,
)
from lumen.templates.service import ReserveResult, TemplateService, default_service
from lumen.templates.store import list_instances, reserve_instance

# alias
can_launch = evaluate_launch

__all__ = [
    "TemplateSpec",
    "TemplateInstance",
    "TemplateInstanceStatus",
    "TemplateLaunchMode",
    "list_templates",
    "get_template",
    "FREE_MAX_RUNNING",
    "FREE_MAX_RUNNING_TEMPLATES",
    "TRIAL_MAX_MINUTES",
    "PERMANENT_TTL_DAYS",
    "evaluate_launch",
    "can_launch",
    "clamp_trial_minutes",
    "TemplateService",
    "ReserveResult",
    "default_service",
    "list_instances",
    "reserve_instance",
]
