"""Hosting ops plane — canonical package (product paths)."""
from lumen.hosting.orchestration import resolve_backend_name, start_host, stop_host
from lumen.hosting.log_aggregator import aggregate_and_ship, collect_instance_logs, ship_to_loki
from lumen.hosting.alerter import alert_instance_failed
from lumen.hosting.backup_manager import backup_all_running, backup_project, interval_hours
from lumen.hosting.rate_limiter import check_can_start, max_concurrent, record_start
from lumen.hosting.secrets_env import seal_project_secrets, inject_secrets_env, load_project_secrets
from lumen.hosting.usage_billing import compute_session_usage, settle_instance, record_request
from lumen.hosting.ops_scheduler import start_ops_scheduler

__all__ = [
    "resolve_backend_name", "start_host", "stop_host",
    "aggregate_and_ship", "collect_instance_logs", "ship_to_loki",
    "alert_instance_failed",
    "backup_all_running", "backup_project", "interval_hours",
    "check_can_start", "max_concurrent", "record_start",
    "seal_project_secrets", "inject_secrets_env", "load_project_secrets",
    "compute_session_usage", "settle_instance", "record_request",
    "start_ops_scheduler",
]
