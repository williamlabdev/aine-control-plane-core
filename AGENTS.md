# AINE Control Plane Core project instructions

- Keep this repository provider-neutral, dependency-free, and read-only by default.
- Do not add credentials, customer data, private paths, provider SDKs, or hosted-service code.
- Portable records may contain root-relative references, but must not contain absolute paths or `file://` references.
- Keep `success`, `failure`, `unknown`, and `conflict` outcomes machine-readable; never collapse uncertainty into a boolean.
- Every contract or schema change needs a fixture and a regression/conformance test.
- The core has no source-repository mutation API; file-backed adapters may write only to their explicitly configured evidence destination, which callers must keep outside scanned repositories, Git state, and deployment state.
- Keep network, identity, secret-manager, UI, HTTP authentication, remediation, and agent execution concerns outside this core.
- Preserve the `aine.control-plane.*.v1` wire identifiers unless a deliberate compatibility change is documented.
- Run the full unittest discovery and `compileall` before proposing a release.
