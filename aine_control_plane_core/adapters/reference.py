from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from aine_control_plane_core.config import AdapterConfig
from aine_control_plane_core.contracts import AdapterContext, AdapterError, AdapterMetadata
from aine_control_plane_core.integration import build_integration_observation
from aine_control_plane_core.outcomes import AdapterOutcome
from aine_control_plane_core.validation import canonical_digest, validate_context, validate_record


AIRT_CHAIN_PROJECTION_SCHEMA = "aine.control-plane.airt-chain-projection.v1"


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


class AirtChainProjectionAdapter:
    """Project an airt run into a portable shape this core is entitled to name.

    airt records a signed hash chain locally and publishes no portable evidence
    export, so an integration observation for an airt run has no producer-owned
    format identifier to carry. This adapter supplies its own:
    `aine.control-plane.airt-chain-projection.v1`. The name says control plane
    rather than airt on purpose — the shape belongs to this core, and claiming
    otherwise would repeat the mistake of asserting a format on a producer's
    behalf.

    The identifier is a constant here because it is part of the observation's
    identity: `evidence_id` is derived from `native_schema` along with the run,
    correlation, snapshot, and digest, so a projection rebuilt under a
    different name would not be recognizable as the same evidence.

    The adapter never opens airt's event database. Callers read the run
    themselves and pass it in, which keeps this core free of airt's storage
    format, its file locations, and its version timeline. Only chain-level
    fields survive projection: sequence, direction, method, argument digest,
    and event hash. Tool arguments, working directories, transcripts, and
    filesystem paths are dropped by allow-list rather than trusted to be
    absent, and what was dropped is reported in the outcome.
    """

    _EVENT_FIELDS = ("seq", "direction", "method", "args_hash", "hash")

    def __init__(self, adapter_id: str = "reference.airt-chain-projection") -> None:
        self._metadata = AdapterMetadata(
            adapter_id=adapter_id,
            kind="evidence_source",
            capabilities=("collect",),
        )
        self._config = AdapterConfig(
            adapter_id=adapter_id,
            kind="evidence_source",
            options={"source": "airt", "projection": "hash-chain"},
        )

    @property
    def metadata(self) -> AdapterMetadata:
        return self._metadata

    @property
    def config(self) -> AdapterConfig:
        return self._config

    def project(self, run: Mapping[str, Any]) -> tuple[dict[str, Any], list[str]]:
        """Return the portable projection of a run and the fields it dropped."""

        events: list[dict[str, Any]] = []
        dropped: set[str] = set()
        for event in run.get("events", ()):
            if not isinstance(event, Mapping):
                raise AdapterError("every airt event must be an object")
            dropped.update(key for key in event if key not in self._EVENT_FIELDS)
            events.append({field: event[field] for field in self._EVENT_FIELDS if field in event})
        events.sort(key=lambda event: event.get("seq", 0))
        projection = {
            "schema": AIRT_CHAIN_PROJECTION_SCHEMA,
            "run_id": run.get("run_id"),
            "events": events,
            "final_hash": run.get("final_hash"),
            "public_key": run.get("public_key"),
            "sealed": bool(run.get("sealed")),
        }
        return projection, sorted(dropped)

    def collect(self, request: Mapping[str, Any], context: AdapterContext) -> Mapping[str, Any]:
        context_errors = validate_context(context)
        if context_errors:
            return self._failure(context, "invalid_context", context_errors)

        run = request.get("run")
        snapshot_id = request.get("snapshot_id")
        if not isinstance(run, Mapping):
            return self._failure(context, "invalid_input", ["request must carry an airt run object"])

        reasons = [
            f"{field} is required"
            for field, value in (
                ("run_id", run.get("run_id")),
                ("correlation_id", run.get("correlation_id")),
                ("final_hash", run.get("final_hash")),
                ("snapshot_id", snapshot_id),
            )
            if not isinstance(value, str) or not value
        ]
        if not run.get("events"):
            reasons.append("a run with no events has no chain to observe")
        if reasons:
            return self._failure(context, "invalid_input", reasons)

        try:
            projection, dropped = self.project(run)
        except AdapterError as exc:
            return self._failure(context, "invalid_input", [str(exc)])

        observed, notes = self._observed_status(run, projection)
        observation = build_integration_observation(
            producer="airt",
            correlation_id=str(run["correlation_id"]),
            run_id=str(run["run_id"]),
            snapshot_id=str(snapshot_id),
            native_schema=AIRT_CHAIN_PROJECTION_SCHEMA,
            status=observed,
            claims=self._claims(run, projection),
            native=projection,
            evidence_refs=[f"airt://runs/{run['run_id']}"],
        )
        record_errors = validate_record(observation)
        if record_errors:
            return self._failure(context, "invalid_observation", record_errors)

        if dropped:
            notes.append("dropped non-portable event fields: " + ", ".join(dropped))
        # The outcome reports the collection; the observation reports the run.
        # A denied tool call is a run that failed, not a collection that
        # failed, so it does not become a failure outcome. `conflict` is the
        # one status both layers share: a source that contradicts itself is
        # also a fact about reading it.
        return _outcome(
            adapter_id=self.metadata.adapter_id,
            operation="collect",
            context=context,
            status="conflict" if observed == "conflict" else "success",
            result=observation,
            reasons=notes,
            evidence_ids=(observation["evidence_id"],),
            conflict_ids=(str(run["run_id"]),) if observed == "conflict" else (),
        )

    def _observed_status(self, run: Mapping[str, Any], projection: Mapping[str, Any]) -> tuple[str, list[str]]:
        # A run that claims a signed anchor it cannot show is not merely
        # unknown: two of its own statements disagree.
        if projection["sealed"] and not projection.get("public_key"):
            return "conflict", ["run is sealed but carries no public key"]
        verdict = run.get("verdict")
        if verdict == "deny":
            return "failure", []
        if verdict == "allow":
            return "success", []
        # The adapter reports what the run carried, and reports nothing when
        # the run carried no decision.
        return "unknown", ["run carries no recorded verdict"]

    def _claims(self, run: Mapping[str, Any], projection: Mapping[str, Any]) -> dict[str, Any]:
        claims: dict[str, Any] = {
            "events": len(projection["events"]),
            "sealed": projection["sealed"],
        }
        for claim, value in (
            ("verdict", run.get("verdict")),
            ("rule", run.get("rule")),
            ("tool", run.get("tool")),
        ):
            if isinstance(value, str) and value:
                claims[claim] = value
        # Chain verification is airt's own operation. This adapter recomputes
        # no hashes, so it repeats that result only when the caller supplies it
        # and asserts nothing when the caller does not.
        if isinstance(run.get("chain_verified"), bool):
            claims["chain_verified"] = run["chain_verified"]
        return claims

    def _failure(self, context: AdapterContext, error_code: str, reasons: Iterable[str]) -> Mapping[str, Any]:
        return _outcome(
            adapter_id=self.metadata.adapter_id,
            operation="collect",
            context=context,
            status="failure",
            error_code=error_code,
            reasons=reasons,
        )
