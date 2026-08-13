"""
Configuration package for the Telegram Bot Generation Engine.

This package centralizes all system configuration so that no engine,
builder, or validator ever hardcodes values.  Everything is driven by a
single :class:`Configuration` object that can be loaded from defaults,
files, and environment variables.
"""

from .config import Configuration, ConfigSource
from .schema import ConfigSchema, SectionSchema, FieldSchema

__all__ = [
    "Configuration",
    "ConfigSource",
    "ConfigSchema",
    "SectionSchema",
    "FieldSchema",
]
