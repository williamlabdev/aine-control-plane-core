from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .contracts import CONTRACT_VERSION


ADAPTER_CONFIG_SCHEMA = "aine.control-plane.adapter-config.v1"


@dataclass(frozen=True)
class AdapterConfig:
    """Portable adapter configuration with guarded credential references.

    Validation rejects known secret-bearing fields and runtime-local paths;
    arbitrary opaque option values still require adapter-level discipline.
    """

    adapter_id: str
    kind: str
    options: Mapping[str, Any] = field(default_factory=dict)
    credential_refs: tuple[str, ...] = ()
    contract_version: str = CONTRACT_VERSION
    read_only: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": ADAPTER_CONFIG_SCHEMA,
            "adapter_id": self.adapter_id,
            "kind": self.kind,
            "contract_version": self.contract_version,
            "options": dict(self.options),
            "credential_refs": list(self.credential_refs),
            "read_only": self.read_only,
        }
