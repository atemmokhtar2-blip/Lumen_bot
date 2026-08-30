"""Lumen — clean architecture foundation.

Layers:
  lumen.domain          pure entities, value objects, repository ports
  lumen.application     commands, queries, handlers (use cases)
  lumen.interfaces      Telegram / API presentation façades
  lumen.infrastructure  persistence, cache, AI, orchestration adapters

Legacy packages (still supported during migration):
  lumen.bot             Telegram implementation
  lumen.api             B2B HTTP implementation
  lumen.platform        operational services (billing, jobs, metering)
  lumen.engine          generation / tools / Cline agent
"""
from lumen.identity import PRODUCT_NAME, PRODUCT_ID, REPO_NAME

__all__ = ["PRODUCT_NAME", "PRODUCT_ID", "REPO_NAME"]
