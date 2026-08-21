from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping, Any

from aine_control_plane_core.config import AdapterConfig
from aine_control_plane_core.contracts import AdapterContext, AdapterError, AdapterMetadata
from aine_control_plane_core.store import LocalRecordStore
from aine_control_plane_core.validation import validate_context


class SQLiteEvidenceSinkAdapter:
    """Local self-hosted evidence sink using the append-only record store."""

    def __init__(self, path: str | Path, adapter_id: str = "local.sqlite-evidence") -> None:
        self.store = LocalRecordStore(path)
        self._metadata = AdapterMetadata(
            adapter_id=adapter_id,
            kind="evidence_sink",
            capabilities=("put", "get", "list", "append_event", "export"),
        )
        self._config = AdapterConfig(
            adapter_id=adapter_id,
            kind="evidence_sink",
            options={"format": "sqlite", "append_only": True},
        )

    @property
    def metadata(self) -> AdapterMetadata:
        return self._metadata

    @property
    def config(self) -> AdapterConfig:
        return self._config

    def put(self, record: Mapping[str, Any], context: AdapterContext) -> Mapping[str, Any]:
        return self.store.put(record, context, record_type="evidence")

    def get(self, record_id: str, context: AdapterContext) -> Mapping[str, Any] | None:
        self._require_context(context)
        return self.store.get(record_id)

    def list(self, context: AdapterContext) -> Iterable[Mapping[str, Any]]:
        self._require_context(context)
        return iter(self.store.list_records("evidence"))

    @staticmethod
    def _require_context(context: AdapterContext) -> None:
        errors = validate_context(context)
        if errors:
            raise AdapterError("invalid adapter context: " + "; ".join(errors))
