"""Power Git Engine package — performance, security, honest verify, safe workflow, self-heal."""
from .result import GitEngineResult
from .engine import PowerGitEngine, get_engine
from .strategies import clone_multi_strategy
from .security import ensure_strict_gitignore, scan_files_for_secrets, assert_inside_sandbox, redact_text
from .verify import structural_validate
from .workflow import atomic_commit, create_ephemeral_branch, rollback_hard, merge_ephemeral_to
from .maintenance import unique_workdir, prepare_dest_dir, git_gc, gc_mirrors
from .mirror import ensure_bare_mirror, materialize_from_mirror, mirror_root

__all__ = [
    "GitEngineResult",
    "PowerGitEngine",
    "get_engine",
    "clone_multi_strategy",
    "ensure_strict_gitignore",
    "scan_files_for_secrets",
    "assert_inside_sandbox",
    "redact_text",
    "structural_validate",
    "atomic_commit",
    "create_ephemeral_branch",
    "rollback_hard",
    "merge_ephemeral_to",
    "unique_workdir",
    "prepare_dest_dir",
    "git_gc",
    "gc_mirrors",
    "ensure_bare_mirror",
    "materialize_from_mirror",
    "mirror_root",
]
