"""Lumen — platform foundation.

Public layout:
  lumen.identity   brand / product identity (single source of truth)
  lumen.engine     generation, tools, LLM, hosting
  lumen.platform   credits, tenants, billing, metering
  lumen.bot        Telegram consumer interface
  lumen.api        B2B HTTP API
"""
from lumen.identity import PRODUCT_NAME, PRODUCT_ID, REPO_NAME

__all__ = ["PRODUCT_NAME", "PRODUCT_ID", "REPO_NAME"]
