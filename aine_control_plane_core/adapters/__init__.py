"""Dependency-free reference adapters for the public AINE core."""

from .local import SQLiteEvidenceSinkAdapter
from .reference import JsonlEvidenceSinkAdapter, StaticIdentityAdapter

__all__ = [
    "JsonlEvidenceSinkAdapter",
    "SQLiteEvidenceSinkAdapter",
    "StaticIdentityAdapter",
]
