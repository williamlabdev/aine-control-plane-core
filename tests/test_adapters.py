from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aine_control_plane.adapters import (
    AIRT_CHAIN_PROJECTION_SCHEMA,
    AirtChainProjectionAdapter,
    JsonlEvidenceSinkAdapter,
    StaticIdentityAdapter,
)
from aine_control_plane.contracts import AdapterContext
from aine_control_plane.validation import (
    validate_adapter_config,
    validate_adapter_metadata,
    validate_outcome,
    validate_record,
)


FIXTURE_DIR = Path(__file__).parents[1] / "aine_control_plane" / "fixtures"


class ReferenceAdapterTests(unittest.TestCase):
    def setUp(self):
        self.context = AdapterContext("request-reference-1", actor={"id": "agent.codex"})

    def test_jsonl_evidence_sink_round_trip_and_invalid_record_outcome(self):
        record = json.loads((FIXTURE_DIR / "reference_record.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            sink = JsonlEvidenceSinkAdapter(Path(directory) / "evidence.jsonl")
            self.assertEqual(validate_adapter_metadata(sink.metadata), [])
            self.assertEqual(validate_adapter_config(sink.config.as_dict()), [])

            stored = sink.put(record, self.context)
            self.assertEqual(validate_outcome(stored), [])
            self.assertEqual(stored["status"], "success")
            self.assertEqual(sink.get("evidence.reference.1", self.context), record)
            self.assertEqual(list(sink.list(self.context)), [record])

            invalid = sink.put({"schema": "aine.evidence.v1"}, self.context)
            self.assertEqual(validate_outcome(invalid), [])
            self.assertEqual(invalid["status"], "failure")
            self.assertEqual(invalid["error_code"], "invalid_input")

    def test_static_identity_reports_success_unknown_and_conflict(self):
        subjects = json.loads((FIXTURE_DIR / "reference_identity.json").read_text(encoding="utf-8"))
        identity = StaticIdentityAdapter(subjects)
        self.assertEqual(validate_adapter_metadata(identity.metadata), [])
        self.assertEqual(validate_adapter_config(identity.config.as_dict()), [])

        resolved = identity.resolve("agent.codex", self.context)
        self.assertEqual(validate_outcome(resolved), [])
        self.assertEqual(resolved["status"], "success")
        self.assertEqual(resolved["result"]["schema"], "aine.control-plane.identity-context.v1")

        unknown = identity.resolve("user.missing", self.context)
        self.assertEqual(validate_outcome(unknown), [])
        self.assertEqual(unknown["status"], "unknown")

        conflict = identity.resolve("user.conflicted", self.context)
        self.assertEqual(validate_outcome(conflict), [])
        self.assertEqual(conflict["status"], "conflict")
        self.assertEqual(conflict["conflict_ids"], ["identity-conflict.1"])


SNAPSHOT_ID = "sha256:" + "1a" * 32


def _airt_run():
    return json.loads((FIXTURE_DIR / "airt_run.json").read_text(encoding="utf-8"))


class AirtChainProjectionTests(unittest.TestCase):
    def setUp(self):
        self.adapter = AirtChainProjectionAdapter()
        self.context = AdapterContext("request-airt-1", actor={"id": "agent.codex"})

    def _collect(self, run, snapshot_id=SNAPSHOT_ID):
        return self.adapter.collect({"run": run, "snapshot_id": snapshot_id}, self.context)

    def test_a_real_denied_run_becomes_a_valid_observation(self):
        self.assertEqual(validate_adapter_metadata(self.adapter.metadata), [])
        self.assertEqual(validate_adapter_config(self.adapter.config.as_dict()), [])

        outcome = self._collect(_airt_run())
        self.assertEqual(validate_outcome(outcome), [])
        # A denied tool call is a run that failed, not a collection that failed.
        self.assertEqual(outcome["status"], "success")

        observation = outcome["result"]
        self.assertEqual(validate_record(observation), [])
        self.assertEqual(observation["producer"], "airt")
        self.assertEqual(observation["project_id"], "aine.airt")
        self.assertEqual(observation["native_schema"], AIRT_CHAIN_PROJECTION_SCHEMA)
        self.assertEqual(observation["status"], "failure")
        self.assertEqual(observation["claims"]["rule"], "no-destructive-shell")
        self.assertEqual(outcome["evidence_ids"], [observation["evidence_id"]])
        self.assertTrue(observation["read_only"])

    def test_the_projection_drops_non_portable_event_fields_and_says_so(self):
        run = _airt_run()
        projection, dropped = self.adapter.project(run)
        self.assertEqual(dropped, ["args", "cwd", "tool_name"])
        blob = json.dumps(projection)
        for leaked in ("cwd", "args\"", "/workspace"):
            self.assertNotIn(leaked, blob)
        for event in projection["events"]:
            self.assertEqual(sorted(event), ["args_hash", "direction", "hash", "method", "seq"])

        outcome = self._collect(run)
        self.assertIn("dropped non-portable event fields: args, cwd, tool_name", outcome["reasons"])
        self.assertNotIn("/workspace", json.dumps(outcome["result"]))

    def test_the_projection_is_stable_regardless_of_event_order(self):
        run = _airt_run()
        shuffled = dict(run, events=list(reversed(run["events"])))
        self.assertEqual(self.adapter.project(run)[0], self.adapter.project(shuffled)[0])
        self.assertEqual(
            self._collect(run)["result"]["native_digest"],
            self._collect(shuffled)["result"]["native_digest"],
        )

    def test_the_adapter_asserts_no_chain_verification_it_did_not_perform(self):
        run = _airt_run()
        run.pop("chain_verified")
        observation = self._collect(run)["result"]
        self.assertNotIn("chain_verified", observation["claims"])

    def test_a_run_without_a_verdict_is_unknown_rather_than_success(self):
        run = _airt_run()
        run.pop("verdict")
        outcome = self._collect(run)
        self.assertEqual(outcome["status"], "success")
        self.assertEqual(outcome["result"]["status"], "unknown")
        self.assertIn("run carries no recorded verdict", outcome["reasons"])
        self.assertNotIn("verdict", outcome["result"]["claims"])

    def test_a_run_sealed_without_a_public_key_is_a_conflict(self):
        run = _airt_run()
        run.pop("public_key")
        outcome = self._collect(run)
        self.assertEqual(validate_outcome(outcome), [])
        self.assertEqual(outcome["status"], "conflict")
        self.assertEqual(outcome["result"]["status"], "conflict")
        self.assertEqual(outcome["conflict_ids"], [run["run_id"]])
        self.assertIn("run is sealed but carries no public key", outcome["reasons"])

    def test_missing_correlation_snapshot_or_chain_is_reported_not_guessed(self):
        run = _airt_run()
        run.pop("correlation_id")
        run.pop("final_hash")
        outcome = self._collect(run, snapshot_id="")
        self.assertEqual(outcome["status"], "failure")
        self.assertEqual(outcome["error_code"], "invalid_input")
        self.assertEqual(
            outcome["reasons"],
            ["correlation_id is required", "final_hash is required", "snapshot_id is required"],
        )
        self.assertNotIn("result", outcome)

    def test_an_empty_run_has_no_chain_to_observe(self):
        outcome = self._collect(dict(_airt_run(), events=[]))
        self.assertEqual(outcome["status"], "failure")
        self.assertIn("a run with no events has no chain to observe", outcome["reasons"])


if __name__ == "__main__":
    unittest.main()
