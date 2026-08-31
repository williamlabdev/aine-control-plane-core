from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Protocol


CONTRACT_VERSION = "aine.control-plane.contracts.v1"


class AdapterError(Exception):
    """Raised when an adapter cannot satisfy a contract without guessing."""


class CredentialProvider(Protocol):
    """Resolve a runtime credential reference without exposing its value."""

    def resolve(self, reference: str) -> str: ...


@dataclass(frozen=True)
class AdapterMetadata:
    adapter_id: str
    kind: str
    contract_version: str = CONTRACT_VERSION
    capabilities: tuple[str, ...] = ()
    read_only: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "adapter_id": self.adapter_id,
            "kind": self.kind,
            "contract_version": self.contract_version,
            "capabilities": list(self.capabilities),
            "read_only": self.read_only,
        }


@dataclass(frozen=True)
class AdapterContext:
    request_id: str
    actor: Mapping[str, Any] = field(default_factory=dict)
    evidence_ids: tuple[str, ...] = ()
    read_only: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "actor": dict(self.actor),
            "evidence_ids": list(self.evidence_ids),
            "read_only": self.read_only,
        }


class EvidenceSinkAdapter(Protocol):
    """Persist or forward portable records without changing their meaning."""

    @property
    def metadata(self) -> AdapterMetadata: ...

    def put(self, record: Mapping[str, Any], context: AdapterContext) -> Mapping[str, Any]: ...

    def get(self, record_id: str, context: AdapterContext) -> Mapping[str, Any] | None: ...

    def list(self, context: AdapterContext) -> Iterable[Mapping[str, Any]]: ...


class EvidenceSourceAdapter(Protocol):
    """Collect portable evidence from an external read-only source."""

    @property
    def metadata(self) -> AdapterMetadata: ...

    def collect(self, request: Mapping[str, Any], context: AdapterContext) -> Mapping[str, Any]: ...


class IdentityAdapter(Protocol):
    """Resolve an external subject into portable policy attributes."""

    @property
    def metadata(self) -> AdapterMetadata: ...

    def resolve(self, subject_id: str, context: AdapterContext) -> Mapping[str, Any]: ...


class PortfolioViewAdapter(Protocol):
    """Render or publish a portable portfolio snapshot."""

    @property
    def metadata(self) -> AdapterMetadata: ...

    def publish(self, snapshot: Mapping[str, Any], context: AdapterContext) -> Mapping[str, Any]: ...


class RetentionAdapter(Protocol):
    """Evaluate retention without deleting or silently mutating records."""

    @property
    def metadata(self) -> AdapterMetadata: ...

    def evaluate(self, records: Iterable[Mapping[str, Any]], policy: Mapping[str, Any], context: AdapterContext) -> Mapping[str, Any]: ...
