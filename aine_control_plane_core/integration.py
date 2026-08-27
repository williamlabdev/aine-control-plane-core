"""Portable report-only integration observations.

The contract links a native producer run to one Control Plane correlation
without changing the producer's evidence format.  It deliberately carries a
digest and normalized claims instead of raw files, paths, credentials, or
provider payloads.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping


INTEGRATION_OBSERVATION_SCHEMA = "aine.control-plane.integration-observation.v1"
INTEGRATION_STATUSES = ("success", "failure", "unknown", "conflict")
PRODUCER_PROJECTS = {"orvena": "aine.orvena", "airt": "aine.airt"}

_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_FIELDS = {
    "schema",
    "evidence_id",
    "correlation_id",
    "producer",
    "project_id",
    "run_id",
    "snapshot_id",
    "native_schema",
    "native_digest",
    "status",
    "claims",
    "evidence_refs",
    "read_only",
}


def _canonical_digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _id_error(value: Any, field: str) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return f"{field} must be a non-empty portable identifier"
    if not _ID_PATTERN.fullmatch(value):
        return f"{field} must contain only portable identifier characters"
    return None


def validate_correlation_id(value: Any) -> list[str]:
    """Validate the portable identifier shared by producer and runner records."""

    error = _id_error(value, "correlation_id")
    return [error] if error else []


def validate_integration_observation(record: Mapping[str, Any]) -> list[str]:
    """Validate the shared cross-project report-only observation contract."""

    errors: list[str] = []
    if not isinstance(record, Mapping):
        return ["integration observation must be an object"]
    errors.extend(
        f"integration observation contains unsupported field: {field}"
        for field in sorted(set(record) - _FIELDS)
    )
    if record.get("schema") != INTEGRATION_OBSERVATION_SCHEMA:
        errors.append(f"unsupported integration observation schema: {record.get('schema')}")
    for field in ("evidence_id", "correlation_id", "producer", "project_id", "run_id", "snapshot_id", "native_schema"):
        error = _id_error(record.get(field), field)
        if error:
            errors.append(error)
    producer = record.get("producer")
    project_id = record.get("project_id")
    if isinstance(producer, str):
        expected_project = PRODUCER_PROJECTS.get(producer)
        if expected_project is None:
            errors.append(f"unsupported integration producer: {producer}")
        elif project_id != expected_project:
            errors.append(f"producer {producer} must use project_id {expected_project}")
    if not isinstance(record.get("native_digest"), str) or not _DIGEST_PATTERN.fullmatch(str(record.get("native_digest"))):
        errors.append("native_digest must be a sha256 digest")
    if record.get("status") not in INTEGRATION_STATUSES:
        errors.append("integration observation status is unsupported")
    if not isinstance(record.get("claims"), Mapping):
        errors.append("claims must be an object")
    if "evidence_refs" in record and (
        not isinstance(record.get("evidence_refs"), list)
        or not all(isinstance(item, str) and item.strip() for item in record.get("evidence_refs", []))
    ):
        errors.append("evidence_refs must be an array of non-empty strings")
    if record.get("read_only") is not True:
        errors.append("integration observations must remain read_only")

    # Import lazily to keep the contract module dependency-free and avoid a
    # validation.py <-> integration.py import cycle.
    from .validation import find_local_paths

    for path in find_local_paths(record, "integration_observation"):
        errors.append(f"runtime-local path is not allowed: {path}")
    return errors


def build_integration_observation(
    *,
    producer: str,
    correlation_id: str,
    run_id: str,
    snapshot_id: str,
    native_schema: str,
    status: str,
    claims: Mapping[str, Any],
    native: Mapping[str, Any],
    evidence_refs: list[str] | tuple[str, ...] = (),
) -> dict[str, Any]:
    """Build a deterministic observation without embedding the native payload.

    `native_schema` is supplied by the adapter rather than looked up here. Only
    the adapter knows which format it digested, and a producer that publishes
    no portable export has no identifier for this core to assert on its behalf.
    """

    project_id = PRODUCER_PROJECTS.get(producer, "")
    native_digest = _canonical_digest(native)
    identity = _canonical_digest(
        {
            "producer": producer,
            "correlation_id": correlation_id,
            "run_id": run_id,
            "snapshot_id": snapshot_id,
            "native_schema": native_schema,
            "native_digest": native_digest,
        }
    )
    record = {
        "schema": INTEGRATION_OBSERVATION_SCHEMA,
        "evidence_id": f"integration.{producer}.{identity[7:23]}",
        "correlation_id": correlation_id,
        "producer": producer,
        "project_id": project_id,
        "run_id": run_id,
        "snapshot_id": snapshot_id,
        "native_schema": native_schema,
        "native_digest": native_digest,
        "status": status,
        "claims": dict(claims),
        "evidence_refs": list(evidence_refs),
        "read_only": True,
    }
    errors = validate_integration_observation(record)
    if errors:
        raise ValueError("invalid integration observation: " + "; ".join(errors))
    return record
