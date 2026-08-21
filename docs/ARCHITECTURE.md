# Public architecture boundary

## Position

`aine-control-plane-core` sits between portable artifacts produced by
`aine-registry` and an application-specific control plane. It defines data and
decision contracts, but it does not own a hosted application or a repository.

```mermaid
flowchart LR
    R[aine-registry snapshot] --> P[PortfolioRegistry]
    P --> S[LocalRecordStore]
    S --> E[Portable evidence and audit records]
    E --> G[Policy / RBAC / ABAC evaluation]
    G --> O[Machine-readable decision]
    A[Project or provider adapter] --> C[Core contracts]
    C --> O
```

## Public modules

| Module | Responsibility | Boundary |
| --- | --- | --- |
| `contracts.py` | adapter protocols, context, metadata | no provider SDK or transport |
| `outcomes.py` | portable success/failure/unknown/conflict envelope | preserves uncertainty |
| `config.py` | serializable adapter configuration | credential references plus structural secret/path guards; opaque values remain adapter-specific |
| `validation.py` | contract, record, config, path, and digest validation | evidence-backed structural checks |
| `store.py` | append-only SQLite records/events and export | writes only its configured store |
| `portfolio.py` | Registry snapshot ingest, views, and impact | does not rescan repositories |
| `governance.py` | policy plus deterministic RBAC/ABAC decisions | evaluates; does not enforce external systems |
| `retention.py` | retention recommendations | never deletes |
| `adapters/` | local and deterministic reference adapters | no network/provider dependency |

## Deliberate non-goals

The public core does not include UI, HTTP serving, authentication, GitHub
integration, secret resolution, deployment, source editing, agent execution,
approval workflow orchestration, or hosted multi-tenant state. Those are
application and adapter concerns and must establish their own trust boundary.
File-backed reference adapters have no source-repository handle, but callers
must configure their destinations outside scanned repositories.

## Compatibility

The package release version starts at `0.1.0` because this is a new repository.
Portable contract identifiers remain `aine.control-plane.*.v1`; consumers should
pin and test the wire schemas independently from the Python package version.
