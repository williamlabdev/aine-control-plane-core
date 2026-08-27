"""Dependency-free reference adapters for the public AINE core."""

from .local import SQLiteEvidenceSinkAdapter
from .reference import (
    AIRT_CHAIN_PROJECTION_SCHEMA,
    AirtChainProjectionAdapter,
    JsonlEvidenceSinkAdapter,
    StaticIdentityAdapter,
)

__all__ = [
    "AIRT_CHAIN_PROJECTION_SCHEMA",
    "AirtChainProjectionAdapter",
    "JsonlEvidenceSinkAdapter",
    "SQLiteEvidenceSinkAdapter",
    "StaticIdentityAdapter",
]
