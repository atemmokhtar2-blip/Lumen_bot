"""Compatibility shim — use lumen.platform.sanitize."""
from lumen.platform.sanitize import *  # noqa: F403
from lumen.platform.sanitize import (  # noqa: F401
    sanitize_error,
    sanitize_for_storage,
    sanitize_log_text,
    assert_safe_fs_path,
    install_secret_log_filter,
    user_facing_generation_error,
)
