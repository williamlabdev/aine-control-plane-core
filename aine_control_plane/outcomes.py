from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


OUTCOME_SCHEMA = "aine.control-plane.adapter-outcome.v1"
OUTCOME_STATUSES = ("success", "failure", "unknown", "conflict")


@dataclass(frozen=True)
class AdapterOutcome:
    """Portable, machine-readable result for an adapter operation."""

    status: str
    adapter_id: str
    operation: str
    request_id: str
    read_only: bool = True
    result: Mapping[str, Any] | None = None
    error_code: str | None = None
    reasons: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    conflict_ids: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        outcome: dict[str, Any] = {
            "schema": OUTCOME_SCHEMA,
            "status": self.status,
            "adapter_id": self.adapter_id,
            "operation": self.operation,
            "request_id": self.request_id,
            "read_only": self.read_only,
        }
        if self.result is not None:
            outcome["result"] = dict(self.result)
        if self.error_code:
            outcome["error_code"] = self.error_code
        if self.reasons:
            outcome["reasons"] = list(self.reasons)
        if self.evidence_ids:
            outcome["evidence_ids"] = list(self.evidence_ids)
        if self.conflict_ids:
            outcome["conflict_ids"] = list(self.conflict_ids)
        return outcome
