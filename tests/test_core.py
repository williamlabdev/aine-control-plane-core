from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from aine_control_plane_core.contracts import AdapterContext
from aine_control_plane_core.governance import authorize, evaluate_policy
from aine_control_plane_core.portfolio import PortfolioRegistry
from aine_control_plane_core.retention import evaluate_store_retention
from aine_control_plane_core.store import LocalRecordStore
from aine_control_plane_core.validation import (
    validate_authorization_decision,
    validate_policy_decision,
    validate_record,
)


FIXTURE_DIR = Path(__file__).parents[1] / "aine_control_plane_core" / "fixtures"


class PublicCoreTests(unittest.TestCase):
    def setUp(self):
        self.context = AdapterContext(
            "request-core",
            actor={"id": "developer", "roles": ["approver"], "teams": ["platform"]},
        )

    def test_policy_preserves_enforced_unknown_and_failure(self):
        policy = {"policy_id": "policy.release", "required_checks": ["tests", "security"]}
        checks = [
            {"check_id": "tests", "status": "pass", "evidence_ids": ["evidence.tests"]},
            {"check_id": "security", "status": "fail", "evidence_ids": ["evidence.security"]},
        ]
        advisory = evaluate_policy(policy, checks, self.context)
        self.assertEqual(validate_policy_decision(advisory), [])
        self.assertEqual(advisory["status"], "fail")
        self.assertFalse(advisory["blocked"])

        enforced = evaluate_policy(policy, checks, self.context, mode="enforced")
        self.assertEqual(enforced["status"], "fail")
        self.assertTrue(enforced["blocked"])

        unknown = evaluate_policy(policy, [{"check_id": "tests", "status": "pass"}], self.context, mode="enforced")
        self.assertEqual(unknown["status"], "unknown")
        self.assertTrue(unknown["blocked"])

    def test_rbac_and_abac_authorization(self):
        subject = {
            "subject_id": "developer",
            "roles": ["developer"],
            "teams": ["platform"],
            "attributes": {"environment": "staging"},
        }
        rules = [
            {
                "rule_id": "rule.deploy-staging",
                "effect": "allow",
                "action": "deploy",
                "resource": "service/*",
                "roles": ["developer"],
                "attributes": {"environment": "staging"},
            },
            {"rule_id": "rule.deny-prod", "effect": "deny", "action": "deploy", "resource": "service/production"},
        ]
        allowed = authorize(subject, rules, "deploy", "service/checkout", self.context)
        self.assertEqual(validate_authorization_decision(allowed), [])
        self.assertEqual(allowed["status"], "allow")
        denied = authorize(subject, rules, "deploy", "service/production", self.context)
        self.assertEqual(denied["status"], "deny")
        unknown = authorize({"subject_id": "unknown", "roles": ["developer"], "attributes": {}}, rules, "deploy", "service/checkout", self.context)
        self.assertEqual(unknown["status"], "unknown")

    def test_store_and_portfolio_are_append_only_and_portable(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LocalRecordStore(Path(directory) / "control-plane.sqlite", clock=lambda: "2026-01-10T00:00:00+00:00")
            record = {"schema": "aine.evidence.v1", "evidence_id": "evidence.store", "claims": {"status": "pass"}}
            self.assertEqual(store.put(record, self.context)["status"], "success")
            self.assertTrue(store.put(record, self.context)["result"]["duplicate"])
            self.assertEqual(store.put({**record, "claims": {"status": "fail"}}, self.context)["status"], "conflict")

            snapshot = json.loads((FIXTURE_DIR / "registry_snapshot.json").read_text(encoding="utf-8"))
            registry = PortfolioRegistry(store)
            self.assertEqual(registry.ingest_snapshot(snapshot, self.context)["status"], "success")
            self.assertEqual(registry.get_project("reference.provider")["name"], "provider")
            self.assertEqual(registry.impact("reference.provider")["affected_projects"][0]["project_id"], "reference.consumer")

            leaked = json.loads(json.dumps(snapshot))
            leaked["artifacts"][0]["path"] = "/Users/example/private/api.yaml"
            self.assertTrue(registry.ingest_snapshot(leaked, self.context)["status"] == "failure")

            invalid_schema = json.loads(json.dumps(snapshot))
            invalid_schema["snapshot_id"] = "snapshot.invalid-schema"
            invalid_schema["schema"] = "not-aine-registry"
            self.assertEqual(registry.ingest_snapshot(invalid_schema, self.context)["status"], "failure")

            retention = evaluate_store_retention(
                store,
                {"retain_days": 1},
                now=lambda: datetime(2026, 1, 12, tzinfo=timezone.utc),
            )
            self.assertEqual(retention["decisions"][0]["status"], "review")

    def test_record_validation_rejects_absolute_path(self):
        record = {"schema": "aine.evidence.v1", "evidence_id": "evidence.path", "claims": {"path": "/Users/example/private.txt"}}
        self.assertTrue(validate_record(record))

        unc_record = {"schema": "aine.evidence.v1", "evidence_id": "evidence.unc", "claims": {"path": "\\\\server\\share\\private.txt"}}
        self.assertTrue(validate_record(unc_record))

    def test_store_rejects_nonportable_records_and_event_payloads(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LocalRecordStore(Path(directory) / "control-plane.sqlite")
            record = {"schema": "aine.evidence.v1", "evidence_id": "evidence.path", "claims": {"path": "/Users/example/private.txt"}}
            rejected = store.put(record, self.context)
            self.assertEqual(rejected["status"], "failure")
            self.assertEqual(rejected["error_code"], "invalid_record")

            event = store.append_event("evidence.recorded", "evidence.path", record, self.context)
            self.assertEqual(event["status"], "failure")
            self.assertEqual(event["error_code"], "invalid_event_payload")


if __name__ == "__main__":
    unittest.main()
