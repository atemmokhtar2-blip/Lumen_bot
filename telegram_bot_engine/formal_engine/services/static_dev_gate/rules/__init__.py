"""Static analysis rules — each rule is independent and registrable."""

from .base import Rule
from .registry import all_rules, rules_by_id

__all__ = ["Rule", "all_rules", "rules_by_id"]
