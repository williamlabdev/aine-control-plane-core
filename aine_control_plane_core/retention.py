from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from .store import LocalRecordStore


RETENTION_SCHEMA = "aine.control-plane.retention-decision.v1"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def evaluate_record_retention(
    row: Mapping[str, Any],
    policy: Mapping[str, Any],
    now: Callable[[], datetime] = _now,
) -> Mapping[str, Any]:
    record_id = str(row.get("record_id", "unknown"))
    retain_days = policy.get("retain_days")
    if not isinstance(retain_days, (int, float)) or retain_days < 0:
        return {
            "schema": RETENTION_SCHEMA,
            "record_id": record_id,
            "status": "unknown",
            "reason": "policy.retain_days must be a non-negative number",
            "read_only": True,
        }
    created_at = row.get("created_at")
    if not created_at:
        return {
            "schema": RETENTION_SCHEMA,
            "record_id": record_id,
            "status": "unknown",
            "reason": "record created_at is missing",
            "read_only": True,
        }
    try:
        age_days = (now() - _parse(str(created_at))).total_seconds() / 86400
    except (TypeError, ValueError):
        return {
            "schema": RETENTION_SCHEMA,
            "record_id": record_id,
            "status": "unknown",
            "reason": "record created_at is invalid",
            "read_only": True,
        }
    status = "review" if age_days > float(retain_days) else "keep"
    return {
        "schema": RETENTION_SCHEMA,
        "record_id": record_id,
        "status": status,
        "reason": f"record age is {age_days:.3f} days; retention threshold is {retain_days} days",
        "age_days": round(age_days, 3),
        "read_only": True,
    }


def evaluate_store_retention(
    store: LocalRecordStore,
    policy: Mapping[str, Any],
    now: Callable[[], datetime] = _now,
) -> Mapping[str, Any]:
    decisions = [evaluate_record_retention(row, policy, now) for row in store.list_rows()]
    return {
        "schema": "aine.control-plane.retention-manifest.v1",
        "policy": dict(policy),
        "decisions": decisions,
        "read_only": True,
    }
