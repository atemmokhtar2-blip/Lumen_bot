"""User-facing hosting ops package (paths requested by product).

Re-exports engine implementations so imports like
``lumen.hosting.log_aggregator`` work.
"""
from lumen.engine.services.hosting.log_aggregator import (  # noqa: F401
    aggregate_and_ship,
    collect_instance_logs,
    ship_to_loki,
)
from lumen.engine.services.hosting.alerter import alert_instance_failed  # noqa: F401
from lumen.engine.services.hosting.backup_manager import (  # noqa: F401
    backup_all_running,
    backup_project,
    interval_hours,
)
from lumen.engine.services.hosting.rate_limiter import (  # noqa: F401
    check_can_start,
    max_concurrent,
    record_start,
)
from lumen.engine.services.hosting.orchestration import (  # noqa: F401
    resolve_backend_name,
    start_host,
    stop_host,
)

__all__ = [
    "aggregate_and_ship",
    "collect_instance_logs",
    "ship_to_loki",
    "alert_instance_failed",
    "backup_all_running",
    "backup_project",
    "interval_hours",
    "check_can_start",
    "max_concurrent",
    "record_start",
    "resolve_backend_name",
    "start_host",
    "stop_host",
]
