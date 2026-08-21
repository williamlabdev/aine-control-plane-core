# AINE Control Plane Core

Provider-neutral, dependency-free primitives for building read-only portfolio
governance around [`aine-registry`](https://github.com/williamlabdev/aine-registry).

This repository is the public core boundary. It defines portable contracts and
reference implementations; it is not a hosted control plane, an agent runner,
or a provider integration product.

## What is included

- read-only adapter contracts and machine-readable outcomes;
- portable adapter configuration and local-path/credential-field validation;
- append-only SQLite evidence and audit storage;
- portable Registry snapshot ingest, project/artifact/dependency views, and impact analysis;
- advisory or opt-in enforced policy evaluation, including unknown and conflict states;
- deterministic RBAC/ABAC authorization evaluation;
- retention evaluation without deletion;
- JSONL, SQLite, and static-fixture reference adapters;
- JSON Schemas, fixtures, and conformance tests for the public boundary.

The stable wire identifiers remain under the `aine.control-plane.*.v1`
namespace. The Python package is intentionally dependency-free and can be
embedded by a service, CLI, CI integration, or another adapter implementation.

## What is intentionally excluded

- hosted SaaS, tenant administration, billing, and commercial operations;
- UI, HTTP authentication, session management, and network exposure;
- provider SDKs, credentials, secret-manager resolution, and external identity integrations;
- source-repository mutation, Git operations, deployment execution, and agent execution;
- customer-specific business logic and private portfolio data.

Those concerns belong in an application or project adapter that consumes these
contracts. The core has no source-repository mutation APIs and does not make
network calls. File-backed adapters write to their configured destination, so
callers must keep that destination outside scanned source repositories.

## Quick start

```python
from aine_control_plane_core.contracts import AdapterContext
from aine_control_plane_core.governance import evaluate_policy

context = AdapterContext("request-1", actor={"id": "developer"})
decision = evaluate_policy(
    {"policy_id": "release", "required_checks": ["tests"]},
    [{"check_id": "tests", "status": "pass"}],
    context,
)
assert decision["status"] == "pass"
```

The reference adapters are intentionally explicit about their runtime
destination:

```python
from pathlib import Path

from aine_control_plane_core.adapters import JsonlEvidenceSinkAdapter

sink = JsonlEvidenceSinkAdapter(Path("evidence.jsonl"))
```

The destination path above is runtime configuration and is never part of a
portable adapter configuration or evidence record.

## Development

The project has no runtime dependencies.

```bash
python -m unittest discover -s tests -p 'test_*.py'
python -m compileall -q aine_control_plane_core tests
PYTHONPATH=. python examples/policy_evaluation.py
```

Read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the public boundary and
[SECURITY.md](SECURITY.md) before embedding the package in a service.

## License

MIT. See [LICENSE](LICENSE).
