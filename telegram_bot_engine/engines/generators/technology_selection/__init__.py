"""
Technology Selection Engine — Specification 016.

This engine is responsible for selecting all appropriate technologies
for the project based on the Architecture Decision Report, Normalized
Requirement Model, Project Intelligence Graph, Knowledge Base, and
Quality Rules.

The engine performs:
    - Compatibility Analysis
    - Performance Analysis
    - Security Analysis
    - Quality Gate validation

It selects all ten technology categories:
    - Programming Language
    - Framework
    - Database
    - ORM
    - Cache
    - Queue
    - Storage
    - Logging System
    - Testing Framework
    - Deployment Requirements

Status: Fully implemented per Specification 016.
"""

from .technology_selection_engine import TechnologySelectionEngine

__all__ = ["TechnologySelectionEngine"]
