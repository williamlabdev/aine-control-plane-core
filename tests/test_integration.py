from __future__ import annotations

import json
import unittest
from pathlib import Path

from aine_control_plane_core.integration import (
    INTEGRATION_OBSERVATION_SCHEMA,
    build_integration_observation,
    validate_integration_observation,
)
from aine_control_plane_core.validation import validate_record


FIXTURE = Path(__file__).parents[1] / "aine_control_plane_core" / "fixtures" / "integration_observation.json"


class IntegrationObservationTests(unittest.TestCase):
    def test_fixture_is_a_core_portable_record(self):
        record = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(record["schema"], INTEGRATION_OBSERVATION_SCHEMA)
        self.assertEqual(validate_integration_observation(record), [])
        self.assertEqual(validate_record(record), [])

    def test_build_is_deterministic_and_does_not_embed_native_payload(self):
        native = {"schema": "orvena-evidence-v1", "completed": True, "sandbox": "enforced"}
        record = build_integration_observation(
            producer="orvena",
            correlation_id="corr.e2e.001",
            run_id="native-run-001",
            snapshot_id="sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            native_schema="orvena-evidence-v1",
            status="success",
            claims={"completed": True, "sandbox": "enforced"},
            native=native,
        )
        self.assertEqual(validate_record(record), [])
        self.assertNotIn("native", record)
        self.assertTrue(record["native_digest"].startswith("sha256:"))
        same = build_integration_observation(
            producer="orvena",
            correlation_id="corr.e2e.001",
            run_id="native-run-001",
            snapshot_id="sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            native_schema="orvena-evidence-v1",
            status="success",
            claims={"completed": True, "sandbox": "enforced"},
            native=native,
        )
        self.assertEqual(record, same)

    def test_producer_states_its_own_native_schema(self):
        # The core no longer asserts an identifier on a producer's behalf: a
        # producer that publishes no portable export has none to assert.
        record = build_integration_observation(
            producer="airt",
            correlation_id="corr.e2e.002",
            run_id="native-claude-001",
            snapshot_id="sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            native_schema="airt.native-hook.v1",
            status="failure",
            claims={"verdict": "deny", "rule": "no-destructive-shell"},
            native={"run_id": "native-claude-001", "final_hash": "0" * 64},
        )
        self.assertEqual(validate_record(record), [])
        self.assertEqual(record["native_schema"], "airt.native-hook.v1")
        self.assertEqual(record["project_id"], "aine.airt")

    def test_native_schema_must_be_a_portable_identifier(self):
        record = json.loads(FIXTURE.read_text(encoding="utf-8"))
        record["native_schema"] = "the log format we happen to write"
        self.assertTrue(any("native_schema" in error for error in validate_integration_observation(record)))
        with self.assertRaises(TypeError):
            build_integration_observation(
                producer="orvena",
                correlation_id="corr.e2e.003",
                run_id="native-run-003",
                snapshot_id="sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                status="success",
                claims={},
                native={},
            )

    def test_observations_of_the_same_run_stay_distinct_per_native_format(self):
        common = dict(
            producer="orvena",
            correlation_id="corr.e2e.004",
            run_id="native-run-004",
            snapshot_id="sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            status="success",
            claims={"completed": True},
            native={"completed": True},
        )
        first = build_integration_observation(native_schema="orvena-evidence-v1", **common)
        second = build_integration_observation(native_schema="orvena-evidence-v2", **common)
        self.assertNotEqual(first["evidence_id"], second["evidence_id"])

    def test_rejects_project_mismatch_and_local_paths(self):
        record = json.loads(FIXTURE.read_text(encoding="utf-8"))
        record["project_id"] = "aine.airt"
        record["claims"]["path"] = "/private/producer/evidence.json"
        errors = validate_integration_observation(record)
        self.assertTrue(any("project_id" in error for error in errors))
        self.assertTrue(any("runtime-local" in error for error in errors))

    def test_rejects_mutating_or_unsafe_correlation_records(self):
        record = json.loads(FIXTURE.read_text(encoding="utf-8"))
        record["correlation_id"] = "../unsafe"
        record["read_only"] = False
        errors = validate_integration_observation(record)
        self.assertTrue(any("correlation_id" in error for error in errors))
        self.assertIn("integration observations must remain read_only", errors)


if __name__ == "__main__":
    unittest.main()
