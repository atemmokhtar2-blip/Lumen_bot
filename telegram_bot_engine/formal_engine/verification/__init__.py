"""Formal Verification — static + logical checks on generated code."""
from .verifier import VerificationReport, verify_project

__all__ = ["VerificationReport", "verify_project"]
