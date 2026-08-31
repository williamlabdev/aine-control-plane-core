from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from .contracts import AdapterContext
from .outcomes import AdapterOutcome
from .validation import canonical_digest, find_local_paths, validate_record


STORE_SCHEMA = "aine.control-plane.record-store.v1"
EXPORT_SCHEMA = "aine.control-plane.evidence-export.v1"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _portable_record_id(record: Mapping[str, Any]) -> str | None:
    for field in (
        "record_id",
        "evidence_id",
        "approval_id",
        "handoff_id",
        "snapshot_id",
        "event_id",
    ):
        value = record.get(field)
        if value:
            return str(value)
    return None


def _outcome(
    *,
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
        adapter_id="local.sqlite-record-store",
        operation=operation,
        request_id=context.request_id,
        read_only=context.read_only,
        result=result,
        error_code=error_code,
        reasons=tuple(reasons),
        evidence_ids=tuple(evidence_ids),
        conflict_ids=tuple(conflict_ids),
    ).as_dict()


class LocalRecordStore:
    """Append-only local persistence for portable Control Plane records.

    The store writes only its configured evidence database and has no source
    repository handle, command execution, or provider integration. Callers must
    configure the database outside scanned repositories. Records are immutable
    by id: a repeated identical write is idempotent and a different payload for
    an existing id is reported as a conflict.
    """

    def __init__(self, path: str | Path, clock: Callable[[], str] = _now) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._clock = clock
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.path), timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS records (
                    record_id TEXT PRIMARY KEY,
                    record_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    digest TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    aggregate_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    digest TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS records_by_type ON records(record_type);
                CREATE INDEX IF NOT EXISTS events_by_aggregate ON events(aggregate_id);
                """
            )

    def put(
        self,
        record: Mapping[str, Any],
        context: AdapterContext,
        record_type: str = "evidence",
        record_id: str | None = None,
    ) -> Mapping[str, Any]:
        if not context.request_id:
            return _outcome(
                operation="put",
                context=context,
                status="failure",
                error_code="invalid_context",
                reasons=("request_id is required",),
            )
        if not context.read_only:
            return _outcome(
                operation="put",
                context=context,
                status="failure",
                error_code="read_only_context_required",
                reasons=("Control Plane core context must be read_only",),
            )
        record_errors = [
            error
            for error in validate_record(record)
            # Portable identity is enforced below via _portable_record_id /
            # the explicit record_id parameter; private record types (e.g.
            # change requests, runner sessions) carry other identity fields.
            if error != "record must contain a portable identity"
        ]
        if record_errors:
            return _outcome(
                operation="put",
                context=context,
                status="failure",
                error_code="invalid_record",
                reasons=record_errors,
            )
        resolved_id = record_id or _portable_record_id(record)
        if not resolved_id:
            return _outcome(
                operation="put",
                context=context,
                status="failure",
                error_code="missing_record_id",
                reasons=("record must contain a portable identity",),
            )
        if not record_type:
            return _outcome(
                operation="put",
                context=context,
                status="failure",
                error_code="missing_record_type",
                reasons=("record_type is required",),
            )

        payload = json.dumps(dict(record), ensure_ascii=False, sort_keys=True)
        digest = canonical_digest(record)
        created_at = self._clock()
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT digest FROM records WHERE record_id = ?",
                (resolved_id,),
            ).fetchone()
            if existing is not None:
                if existing["digest"] == digest:
                    return _outcome(
                        operation="put",
                        context=context,
                        status="success",
                        result={"record_id": resolved_id, "digest": digest, "duplicate": True},
                    )
                return _outcome(
                    operation="put",
                    context=context,
                    status="conflict",
                    result={"record_id": resolved_id, "existing_digest": existing["digest"], "incoming_digest": digest},
                    reasons=("record id already exists with different content",),
                    conflict_ids=(resolved_id,),
                )
            connection.execute(
                "INSERT INTO records(record_id, record_type, payload, digest, created_at) VALUES (?, ?, ?, ?, ?)",
                (resolved_id, record_type, payload, digest, created_at),
            )
        return _outcome(
            operation="put",
            context=context,
            status="success",
            result={"record_id": resolved_id, "digest": digest, "duplicate": False},
        )

    def get(self, record_id: str) -> Mapping[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM records WHERE record_id = ?",
                (record_id,),
            ).fetchone()
        if row is None:
            return None
        return json.loads(row["payload"])

    def get_row(self, record_id: str) -> Mapping[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT record_id, record_type, payload, digest, created_at FROM records WHERE record_id = ?",
                (record_id,),
            ).fetchone()
        return self._row_to_dict(row) if row is not None else None

    def list_rows(self, record_type: str | None = None) -> list[Mapping[str, Any]]:
        query = "SELECT record_id, record_type, payload, digest, created_at FROM records"
        parameters: tuple[str, ...] = ()
        if record_type:
            query += " WHERE record_type = ?"
            parameters = (record_type,)
        # Preserve insertion order when producers use the same clock value.
        # Snapshot projection treats created_at as the primary observation
        # signal and rowid as the deterministic tie-breaker.
        query += " ORDER BY created_at, rowid"
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def list_records(self, record_type: str | None = None) -> list[Mapping[str, Any]]:
        return [row["record"] for row in self.list_rows(record_type)]

    def append_event(
        self,
        event_type: str,
        aggregate_id: str,
        payload: Mapping[str, Any],
        context: AdapterContext,
        event_id: str | None = None,
    ) -> Mapping[str, Any]:
        if not context.request_id:
            return _outcome(
                operation="append_event",
                context=context,
                status="failure",
                error_code="invalid_context",
                reasons=("request_id is required",),
            )
        if not context.read_only:
            return _outcome(
                operation="append_event",
                context=context,
                status="failure",
                error_code="read_only_context_required",
                reasons=("Control Plane core context must be read_only",),
            )
        local_paths = find_local_paths(payload, "event.payload")
        if local_paths:
            return _outcome(
                operation="append_event",
                context=context,
                status="failure",
                error_code="invalid_event_payload",
                reasons=tuple(f"runtime-local path is not allowed: {path}" for path in local_paths),
            )
        digest = canonical_digest(payload)
        resolved_id = event_id or f"event:{event_type}:{aggregate_id}:{digest[7:19]}"
        event = {
            "schema": "aine.control-plane.audit-event.v1",
            "event_id": resolved_id,
            "event_type": event_type,
            "aggregate_id": aggregate_id,
            "payload": dict(payload),
        }
        event_payload = json.dumps(event, ensure_ascii=False, sort_keys=True)
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT digest FROM events WHERE event_id = ?",
                (resolved_id,),
            ).fetchone()
            if existing is not None:
                status = "success" if existing["digest"] == digest else "conflict"
                return _outcome(
                    operation="append_event",
                    context=context,
                    status=status,
                    result={"event_id": resolved_id, "digest": digest, "duplicate": status == "success"},
                    reasons=() if status == "success" else ("event id already exists with different content",),
                    conflict_ids=() if status == "success" else (resolved_id,),
                )
            connection.execute(
                "INSERT INTO events(event_id, event_type, aggregate_id, payload, digest, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (resolved_id, event_type, aggregate_id, event_payload, digest, self._clock()),
            )
        return _outcome(
            operation="append_event",
            context=context,
            status="success",
            result={"event_id": resolved_id, "digest": digest, "duplicate": False},
        )

    def list_events(self, aggregate_id: str | None = None) -> list[Mapping[str, Any]]:
        query = "SELECT payload FROM events"
        parameters: tuple[str, ...] = ()
        if aggregate_id:
            query += " WHERE aggregate_id = ?"
            parameters = (aggregate_id,)
        query += " ORDER BY created_at, event_id"
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def export(self, destination: str | Path, record_type: str | None = None) -> Mapping[str, Any]:
        records = self.list_rows(record_type)
        events = self.list_events()
        document = {
            "schema": EXPORT_SCHEMA,
            "store_schema": STORE_SCHEMA,
            "records": records,
            "events": events,
        }
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return {"schema": EXPORT_SCHEMA, "destination": str(target), "record_count": len(records), "event_count": len(events)}

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> Mapping[str, Any]:
        return {
            "record_id": row["record_id"],
            "record_type": row["record_type"],
            "record": json.loads(row["payload"]),
            "digest": row["digest"],
            "created_at": row["created_at"],
        }

    def close(self) -> None:
        """Compatibility hook; connections are scoped per operation."""

    def __enter__(self) -> "LocalRecordStore":
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.close()
