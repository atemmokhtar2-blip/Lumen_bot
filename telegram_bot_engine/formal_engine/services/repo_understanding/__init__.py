"""Repo understanding — scan a cloned repository into RepoContract + intelligence."""

from .scanner import RepoUnderstandingService, understand_repo as _scan_understand

def understand_repo(root_path, remote_url: str = ""):
    """Structural scan then Repo Intelligence enrichment."""
    contract = _scan_understand(root_path, remote_url=remote_url)
    try:
        from ..repo_intelligence import enrich_repo_contract
        return enrich_repo_contract(contract)
    except Exception:
        return contract

__all__ = ["RepoUnderstandingService", "understand_repo"]
