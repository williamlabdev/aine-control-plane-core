# Contributing

Contributions should preserve the public boundary described in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

Before opening a change:

1. keep the implementation dependency-free unless the public boundary is explicitly revised;
2. add or update a JSON Schema and fixture for every new portable field or relationship;
3. add a regression or conformance test for every new behavior;
4. verify that tests, examples, and documentation contain no secrets, customer data, or machine-local paths;
5. run `python -m unittest discover -s tests -p 'test_*.py'` and `python -m compileall -q aine_control_plane_core tests`.

Provider-specific integrations should be implemented in a separate adapter
repository rather than added to this core.
