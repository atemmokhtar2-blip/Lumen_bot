"""Post-generation verification only — codegen lives in services/codegen_service."""

from .post_verify import verify_generated_project

__all__ = ["verify_generated_project"]
