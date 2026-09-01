from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from aine_control_plane.contracts import AdapterContext
from aine_control_plane.governance import authorize, evaluate_policy
from aine_control_plane.portfolio import PortfolioRegistry
from aine_control_plane.retention import evaluate_store_retention
from aine_control_plane.store import LocalRecordStore
from aine_control_plane.validation import (
    _MACHINE_LOCAL_PREFIXES,
    find_local_paths,
    validate_authorization_decision,
    validate_policy_decision,
    validate_record,
)


FIXTURE_DIR = Path(__file__).parents[1] / "aine_control_plane" / "fixtures"


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
            impact = registry.impact("reference.provider")
            self.assertEqual(impact["affected_projects"][0]["project_id"], "reference.consumer")
            self.assertTrue(all(not item["project_id"].startswith("external:") for item in impact["affected_projects"]))

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

    def test_portfolio_queries_relationships_source_of_truth_and_impact(self):
        with tempfile.TemporaryDirectory() as directory:
            snapshot = json.loads((FIXTURE_DIR / "registry_semantics_snapshot.json").read_text(encoding="utf-8"))
            clock_values = iter(
                (
                    "2026-08-22T00:00:01+00:00",
                    "2026-08-22T00:00:02+00:00",
                    "2026-08-22T00:00:03+00:00",
                    "2026-08-22T00:00:04+00:00",
                    "2026-08-22T00:00:05+00:00",
                    "2026-08-22T00:00:06+00:00",
                    "2026-08-22T00:00:07+00:00",
                )
            )
            store = LocalRecordStore(Path(directory) / "portfolio.sqlite", clock=lambda: next(clock_values))
            registry = PortfolioRegistry(store)

            self.assertEqual(registry.ingest_snapshot(snapshot, self.context)["status"], "success")
            relationships = registry.relationships(
                project_id="core.web-app",
                relationship_type="service_client",
                status="active",
            )
            self.assertEqual([item["dependency_id"] for item in relationships], ["rel.polyrepo.service-client"])
            self.assertEqual(registry.relationships(relationship_type="unknown"), [])

            source_rules = registry.source_of_truth(domain="checkout.api")
            self.assertEqual(len(source_rules), 1)
            self.assertEqual(source_rules[0]["authority"]["artifact"], "checkout-openapi")
            self.assertEqual(registry.source_of_truth(project_id="core.web-app"), [])

            newer = {
                **snapshot,
                "snapshot_id": "snapshot.polyrepo.semantic.2",
                "source_of_truth": [{**source_rules[0], "evidence": ["checkout-service/.aine/registry.v2.json"]}],
            }
            self.assertEqual(registry.ingest_snapshot(newer, self.context)["status"], "success")
            self.assertEqual(registry.source_of_truth(domain="checkout.api")[0]["evidence"], ["checkout-service/.aine/registry.v2.json"])

            impact = registry.impact("core.checkout-service")
            self.assertTrue(any(edge["scope"] == "cross_root" for edge in impact["relationships"]))
            self.assertEqual(impact["source_of_truth"], registry.source_of_truth(project_id="core.checkout-service"))

            topology_snapshot = {
                **snapshot,
                "snapshot_id": "snapshot.polyrepo.topology-only",
                "relationships": [{
                    "dependency_id": "rel.topology-only",
                    "source": {"project_id": "core.web-app"},
                    "target": {"project_id": "core.checkout-service"},
                    "kind": "governance",
                    "relationship_type": "portfolio_snapshot_consumer",
                    "status": "planned",
                    "evidence": ["core/web-app/.aine/registry.json"],
                }],
            }
            self.assertEqual(registry.ingest_snapshot(topology_snapshot, self.context)["status"], "success")
            self.assertFalse(any(edge.get("dependency_id") == "rel.topology-only" for edge in registry.impact("core.checkout-service")["relationships"]))

            invalid = {**snapshot, "snapshot_id": "snapshot.polyrepo.invalid", "relationships": [{"source": {}, "target": {}}]}
            self.assertEqual(registry.ingest_snapshot(invalid, self.context)["status"], "failure")
            invalid_type = {**snapshot, "snapshot_id": "snapshot.polyrepo.invalid-type", "relationships": None}
            self.assertEqual(registry.ingest_snapshot(invalid_type, self.context)["status"], "failure")
            invalid_evidence = {
                **snapshot,
                "snapshot_id": "snapshot.polyrepo.invalid-evidence",
                "relationships": [{**snapshot["relationships"][0], "evidence": [{}]}],
            }
            self.assertEqual(registry.ingest_snapshot(invalid_evidence, self.context)["status"], "failure")

    def test_portfolio_merges_observations_across_snapshots(self):
        with tempfile.TemporaryDirectory() as directory:
            timestamps = iter(
                (
                    "2026-01-01T00:00:00+00:00",
                    "2026-01-01T00:00:01+00:00",
                    "2026-01-02T00:00:00+00:00",
                    "2026-01-02T00:00:01+00:00",
                )
            )
            store = LocalRecordStore(
                Path(directory) / "portfolio.sqlite",
                clock=lambda: next(timestamps, "2026-01-03T00:00:00+00:00"),
            )
            registry = PortfolioRegistry(store)
            snapshot = json.loads((FIXTURE_DIR / "registry_semantics_snapshot.json").read_text(encoding="utf-8"))
            self.assertEqual(registry.ingest_snapshot(snapshot, self.context)["status"], "success")
            self.assertEqual(registry.snapshot_ids(), ["snapshot.polyrepo.semantic.1"])
            self.assertTrue(
                all(edge["observed_snapshot_id"] == "snapshot.polyrepo.semantic.1" for edge in registry.relationships())
            )

            updated = json.loads(json.dumps(snapshot))
            updated["snapshot_id"] = "snapshot.polyrepo.semantic.2"
            updated["dependencies"][0]["status"] = "active"
            updated["dependencies"][0]["evidence"].append("content-tool/.aine/registry.v2.json")
            updated["source_of_truth"][0]["authority"]["project_id"] = "core.web-app"
            updated["source_of_truth"][0]["evidence"].append("web-app/.aine/registry.v2.json")
            self.assertEqual(registry.ingest_snapshot(updated, self.context)["status"], "success")

            merged = [edge for edge in registry.relationships() if edge.get("dependency_id") == "dep.polyrepo.cross-root"]
            self.assertEqual(len(merged), 1)
            self.assertEqual(merged[0]["observed_snapshot_id"], "snapshot.polyrepo.semantic.2")
            self.assertEqual(merged[0]["status"], "active")
            self.assertEqual(
                merged[0]["evidence_refs"],
                ["content-tool/.aine/registry.json", "content-tool/.aine/registry.v2.json"],
            )

            rules = registry.source_of_truth(domain="checkout.api")
            self.assertEqual(len(rules), 1)
            self.assertEqual(rules[0]["authority"]["project_id"], "core.web-app")
            self.assertEqual(rules[0]["observed_snapshot_id"], "snapshot.polyrepo.semantic.2")
            self.assertEqual(
                rules[0]["evidence_refs"],
                ["checkout-service/.aine/registry.json", "web-app/.aine/registry.v2.json"],
            )
            self.assertEqual(
                registry.snapshot_ids(),
                ["snapshot.polyrepo.semantic.1", "snapshot.polyrepo.semantic.2"],
            )

    def test_record_validation_rejects_absolute_path(self):
        record = {"schema": "aine.evidence.v1", "evidence_id": "evidence.path", "claims": {"path": "/Users/example/private.txt"}}
        self.assertTrue(validate_record(record))

        unc_record = {"schema": "aine.evidence.v1", "evidence_id": "evidence.unc", "claims": {"path": "\\\\server\\share\\private.txt"}}
        self.assertTrue(validate_record(unc_record))

    def test_find_local_paths_allows_api_route_references(self):
        record = {
            "route": "/api/v1/changes/{change_id}",
            "view": "/v1/relationships",
            "contract": "./service/openapi.yaml",
            "sibling": "../aine-registry/README.md",
            "nested": {"paths": ["/healthz", "/v1/projects?include_retired=true"]},
        }
        self.assertEqual(find_local_paths(record), [])

    def test_find_local_paths_rejects_every_machine_identifying_prefix(self):
        # Iterate the constant itself so the deny list can never grow without coverage.
        for prefix in _MACHINE_LOCAL_PREFIXES:
            for variant in (prefix, prefix + "/x.yaml", prefix.upper() + "/x.yaml", prefix.title() + "\\x.yaml", "  " + prefix + "/x"):
                with self.subTest(prefix=prefix, variant=variant):
                    self.assertEqual(find_local_paths({"path": variant}), ["record.path"])
        for non_prefix in ("~/x", "~other/x", "file:///tmp/x", "FILE:x", "\\\\server\\share", "C:x", "d:/x"):
            with self.subTest(variant=non_prefix):
                self.assertEqual(find_local_paths({"path": non_prefix}), ["record.path"])
        # Prefix matching is on path segments: '/usr' is local, '/users-api' is a route.
        for route in ("/usr-api/x", "/tmpfiles", "/homework/2026"):
            with self.subTest(variant=route):
                self.assertEqual(find_local_paths({"path": route}), [])

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
