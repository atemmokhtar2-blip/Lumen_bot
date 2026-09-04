"""Hosting ops plane — canonical package (product paths)."""
from lumen.hosting.orchestration import resolve_backend_name, start_host, stop_host
from lumen.hosting.log_aggregator import aggregate_and_ship, collect_instance_logs, ship_to_loki
from lumen.hosting.alerter import alert_instance_failed
from lumen.hosting.backup_manager import (
    backup_all_running,
    backup_platform_database,
    backup_project,
    interval_hours,
    list_backups,
    restore_project,
)
from lumen.hosting.rate_limiter import check_can_start, max_concurrent, record_start
from lumen.hosting.secrets_env import seal_project_secrets, inject_secrets_env, load_project_secrets
from lumen.hosting.usage_billing import compute_session_usage, settle_instance, record_request
from lumen.hosting.ops_scheduler import start_ops_scheduler
from lumen.hosting.project_manifest import write_manifest_for_instance, load_manifest
from lumen.hosting.webhook_manager import apply_to_instance, webhook_url_for
from lumen.hosting.gateway import write_routes_for_instance
from lumen.hosting.project_space import (
    ensure_project_space,
    write_runtime_manifest,
    load_runtime_manifest,
    ProjectSpace,
)

__all__ = [
    "resolve_backend_name", "start_host", "stop_host",
    "aggregate_and_ship", "collect_instance_logs", "ship_to_loki",
    "alert_instance_failed",
    "backup_all_running", "backup_project", "backup_platform_database", "restore_project", "list_backups", "interval_hours",
    "check_can_start", "max_concurrent", "record_start",
    "seal_project_secrets", "inject_secrets_env", "load_project_secrets",
    "compute_session_usage", "settle_instance", "record_request",
    "start_ops_scheduler",
    "ensure_project_space",
    "write_runtime_manifest",
    "load_runtime_manifest",
    "ProjectSpace",
]
