from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from aine_control_plane_core.config import AdapterConfig
from aine_control_plane_core.contracts import AdapterContext, AdapterError, AdapterMetadata
from aine_control_plane_core.outcomes import AdapterOutcome
from aine_control_plane_core.validation import canonical_digest, validate_context, validate_record


def _portable_record_id(record: Mapping[str, Any]) -> str | None:
    for field in ("evidence_id", "approval_id", "handoff_id", "snapshot_id"):
        value = record.get(field)
        if value:
            return str(value)
    return None


def _outcome(
    *,
    adapter_id: str,
    operation: str,
    context: AdapterContext,
    status: str,
    result: Mapping[str, Any] | None = None,
    error_code: str | None = None,
    reasons: Iterable[str] = (),
    evidence_ids: Iterable[str] = (),
    conflict_ids: Iterable[str] = (),
) -> Mapping[str, Any]:
    return AdapterOutcome(
        status=status,
        adapter_id=adapter_id,
        operation=operation,
        request_id=context.request_id,
        read_only=context.read_only,
        result=result,
        error_code=error_code,
        reasons=tuple(reasons),
        evidence_ids=tuple(evidence_ids),
        conflict_ids=tuple(conflict_ids),
    ).as_dict()


class JsonlEvidenceSinkAdapter:
    """A dependency-free evidence sink backed by an explicit JSONL file.

    The sink writes only to its configured evidence destination and has no
    repository handle, command execution, or network integration. Callers must
    configure that destination outside scanned repositories. The path is runtime
    configuration and is intentionally excluded from portable config.
    """

    def __init__(self, path: str | Path, adapter_id: str = "reference.jsonl-evidence") -> None:
        self._path = Path(path)
        self._metadata = AdapterMetadata(
            adapter_id=adapter_id,
            kind="evidence_sink",
            capabilities=("put", "get", "list"),
        )
        self._config = AdapterConfig(
            adapter_id=adapter_id,
            kind="evidence_sink",
            options={"format": "jsonl"},
        )

    @property
    def metadata(self) -> AdapterMetadata:
        return self._metadata

    @property
    def config(self) -> AdapterConfig:
        return self._config

    def put(self, record: Mapping[str, Any], context: AdapterContext) -> Mapping[str, Any]:
        context_errors = validate_context(context)
        record_errors = validate_record(record)
        if context_errors or record_errors:
            return _outcome(
                adapter_id=self.metadata.adapter_id,
                operation="put",
                context=context,
                status="failure",
                error_code="invalid_input",
                reasons=(*context_errors, *record_errors),
            )

        record_id = _portable_record_id(record)
        if record_id is None:
            return _outcome(
                adapter_id=self.metadata.adapter_id,
                operation="put",
                context=context,
                status="failure",
                error_code="missing_portable_identity",
                reasons=("record must contain a portable identity",),
            )

        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(dict(record), ensure_ascii=False, sort_keys=True))
                handle.write("\n")
        except OSError as exc:
            return _outcome(
                adapter_id=self.metadata.adapter_id,
                operation="put",
                context=context,
                status="failure",
                error_code="sink_write_failed",
                reasons=(str(exc),),
            )

        return _outcome(
            adapter_id=self.metadata.adapter_id,
            operation="put",
            context=context,
            status="success",
            result={"record_id": record_id, "digest": canonical_digest(record)},
        )

    def get(self, record_id: str, context: AdapterContext) -> Mapping[str, Any] | None:
        self._require_context(context)
        for record in self.list(context):
            if _portable_record_id(record) == record_id:
                return record
        return None

    def list(self, context: AdapterContext) -> Iterable[Mapping[str, Any]]:
        self._require_context(context)
        if not self._path.exists():
            return iter(())
        return self._read_records()

    def _read_records(self) -> Iterable[Mapping[str, Any]]:
        try:
            with self._path.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise AdapterError(f"invalid JSONL evidence at line {line_number}") from exc
                    if not isinstance(record, Mapping):
                        raise AdapterError(f"evidence at line {line_number} must be an object")
                    yield record
        except OSError as exc:
            raise AdapterError("evidence sink cannot be read") from exc

    @staticmethod
    def _require_context(context: AdapterContext) -> None:
        errors = validate_context(context)
        if errors:
            raise AdapterError("invalid adapter context: " + "; ".join(errors))


class StaticIdentityAdapter:
    """A deterministic identity adapter for fixtures and local conformance tests."""

    def __init__(
        self,
        subjects: Mapping[str, Mapping[str, Any]],
        adapter_id: str = "reference.static-identity",
    ) -> None:
        self._subjects = {str(subject_id): dict(profile) for subject_id, profile in subjects.items()}
        self._metadata = AdapterMetadata(
            adapter_id=adapter_id,
            kind="identity",
            capabilities=("resolve",),
        )
        self._config = AdapterConfig(
            adapter_id=adapter_id,
            kind="identity",
            options={"source": "fixture"},
        )

    @property
    def metadata(self) -> AdapterMetadata:
        return self._metadata

    @property
    def config(self) -> AdapterConfig:
        return self._config

    def resolve(self, subject_id: str, context: AdapterContext) -> Mapping[str, Any]:
        context_errors = validate_context(context)
        if context_errors:
            return _outcome(
                adapter_id=self.metadata.adapter_id,
                operation="resolve",
                context=context,
                status="failure",
                error_code="invalid_context",
                reasons=context_errors,
            )
        if not subject_id:
            return _outcome(
                adapter_id=self.metadata.adapter_id,
                operation="resolve",
                context=context,
                status="failure",
                error_code="invalid_subject_id",
                reasons=("subject_id is required",),
            )

        profile = self._subjects.get(subject_id)
        if profile is None:
            return _outcome(
                adapter_id=self.metadata.adapter_id,
                operation="resolve",
                context=context,
                status="unknown",
                result={"subject_id": subject_id},
                reasons=("subject_not_found",),
            )

        attributes = profile.get("attributes", {})
        if not isinstance(attributes, Mapping):
            return _outcome(
                adapter_id=self.metadata.adapter_id,
                operation="resolve",
                context=context,
                status="failure",
                error_code="invalid_identity_profile",
                reasons=("attributes must be an object",),
            )

        identity = {
            "schema": "aine.control-plane.identity-context.v1",
            "subject_id": subject_id,
            "roles": list(profile.get("roles", [])),
            "teams": list(profile.get("teams", [])),
            "attributes": dict(attributes),
            "evidence_ids": list(profile.get("evidence_ids", [])),
        }
        conflict_ids = tuple(str(value) for value in profile.get("conflict_ids", []))
        if conflict_ids:
            return _outcome(
                adapter_id=self.metadata.adapter_id,
                operation="resolve",
                context=context,
                status="conflict",
                result=identity,
                reasons=("identity_sources_conflict",),
                evidence_ids=identity["evidence_ids"],
                conflict_ids=conflict_ids,
            )
        return _outcome(
            adapter_id=self.metadata.adapter_id,
            operation="resolve",
            context=context,
            status="success",
            result=identity,
            evidence_ids=identity["evidence_ids"],
        )
