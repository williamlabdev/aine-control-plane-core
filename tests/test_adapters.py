from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aine_control_plane_core.adapters import JsonlEvidenceSinkAdapter, StaticIdentityAdapter
from aine_control_plane_core.contracts import AdapterContext
from aine_control_plane_core.validation import validate_adapter_config, validate_adapter_metadata, validate_outcome


FIXTURE_DIR = Path(__file__).parents[1] / "aine_control_plane_core" / "fixtures"


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


if __name__ == "__main__":
    unittest.main()
