from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from aine_control_plane.change_requests import CHANGE_REQUEST_SCHEMA, validate_change_request
from aine_control_plane.contracts import AdapterContext
from aine_control_plane.server import ControlPlaneHTTPServer
from aine_control_plane.service import ControlPlaneService
from aine_control_plane.store import LocalRecordStore


class ChangeRequestWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.context = AdapterContext(
            "change-request-test",
            actor={"id": "agent.codex", "roles": ["developer"], "teams": ["platform"]},
        )

    def test_create_is_aine_control_plane_owned_append_only_draft(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LocalRecordStore(Path(directory) / "control-plane.sqlite")
            service = ControlPlaneService(store)
            result = service.create_change_request(
                {
                    "change_id": "change.feature.1",
                    "change_type": "feature",
                    "title": "Add project proposal review",
                    "description": "Capture a feature intent before execution is authorized.",
                    "scope": {"project_ids": ["aine-control-plane"]},
                    "acceptance_criteria": ["The proposal is visible in the private UI."],
                    "source_of_truth": ["docs/BLUEPRINT.md"],
                    "evidence_ids": [],
                    "risk": "medium",
                    "approval_required": True,
                },
                self.context,
            )
            self.assertEqual(result["status"], "success")
            record = result["result"]["change_request"]
            self.assertEqual(record["schema"], CHANGE_REQUEST_SCHEMA)
            self.assertEqual(record["status"], "draft")
            self.assertTrue(record["read_only"])
            self.assertEqual(validate_change_request(record), [])
            self.assertEqual(len(service.list_change_requests()), 1)
            self.assertEqual(len(store.list_records("change_request")), 1)
            self.assertEqual(store.list_events()[0]["event_type"], "change_request.created")

    def test_submit_creates_revision_approval_and_audit_events(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LocalRecordStore(Path(directory) / "control-plane.sqlite")
            service = ControlPlaneService(store)
            created = service.create_change_request(
                {
                    "change_id": "change.requirement.1",
                    "change_type": "requirement",
                    "title": "Require a cross-repository preflight",
                    "description": "Document the validation gate for a portfolio change.",
                    "scope": {"project_ids": ["aine-registry", "aine-control-plane"]},
                    "acceptance_criteria": ["A machine-readable preflight result is linked."],
                    "source_of_truth": [],
                    "evidence_ids": ["evidence.preflight.1"],
                    "risk": "high",
                    "approval_required": True,
                },
                self.context,
            )
            self.assertEqual(created["status"], "success")

            submitted = service.submit_change_request("change.requirement.1", self.context)
            self.assertEqual(submitted["status"], "success")
            current = submitted["result"]["change_request"]
            self.assertEqual(current["revision"], 2)
            self.assertEqual(current["status"], "submitted")
            self.assertEqual(current["previous_revision"], 1)
            self.assertTrue(current["approval_id"].startswith("approval.change-request."))
            self.assertEqual(submitted["result"]["approval"]["status"], "pending")
            self.assertEqual(len(store.list_records("change_request")), 2)
            self.assertEqual(len(service.list_change_requests()), 1)
            self.assertEqual(service.list_change_requests()[0]["revision"], 2)

            event_types = [event["event_type"] for event in store.list_events()]
            self.assertEqual(
                event_types,
                ["change_request.created", "change_request.submitted", "approval.requested"],
            )

            repeated = service.submit_change_request("change.requirement.1", self.context)
            self.assertEqual(repeated["status"], "failure")
            self.assertEqual(repeated["error_code"], "invalid_change_request_transition")
            self.assertEqual(len(store.list_records("change_request")), 2)

    def test_invalid_type_and_project_registration_are_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LocalRecordStore(Path(directory) / "control-plane.sqlite")
            service = ControlPlaneService(store)
            invalid = service.create_change_request(
                {"change_type": "bug", "title": "Not supported", "description": "x"},
                self.context,
            )
            self.assertEqual(invalid["status"], "failure")
            self.assertEqual(invalid["error_code"], "invalid_change_request")

            leaked_path = service.create_change_request(
                {
                    "change_type": "feature",
                    "title": "Reject local path",
                    "description": "A portable proposal cannot contain a machine-local path.",
                    "scope": {"project_ids": ["aine-control-plane"], "path": "/Users/example/private"},
                },
                self.context,
            )
            self.assertEqual(leaked_path["status"], "failure")
            self.assertEqual(leaked_path["error_code"], "invalid_change_request")

            registration = service.create_change_request(
                {
                    "change_type": "project_registration",
                    "title": "Register a second workspace root",
                    "description": "Add an explicit project boundary to the portfolio registry.",
                    "scope": {"root_id": "side-projects"},
                    "acceptance_criteria": ["The root is represented without leaking local paths."],
                    "source_of_truth": ["registry-snapshot"],
                    "risk": "low",
                    "approval_required": False,
                },
                self.context,
            )
            self.assertEqual(registration["status"], "success")
            self.assertEqual(registration["result"]["change_request"]["change_type"], "project_registration")
            submitted = service.submit_change_request(
                registration["result"]["change_request"]["change_id"],
                self.context,
            )
            self.assertEqual(submitted["status"], "success")
            self.assertNotIn("approval", submitted["result"])

    def test_fix_change_type_creates_a_draft_and_routes_like_any_other_type(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LocalRecordStore(Path(directory) / "control-plane.sqlite")
            service = ControlPlaneService(store)
            created = service.create_change_request(
                {
                    "change_id": "change.fix.1",
                    "change_type": "fix",
                    "title": "Stop rejecting root-relative API routes as local paths",
                    "description": "A dogfood snapshot was refused for an /api/v1 route reference.",
                    "scope": {"project_ids": ["aine-control-plane"]},
                    "acceptance_criteria": ["The snapshot ingests without an invalid_snapshot error."],
                    "source_of_truth": [],
                    "evidence_ids": [],
                    "risk": "low",
                    "approval_required": True,
                },
                self.context,
            )
            self.assertEqual(created["status"], "success")
            self.assertEqual(created["result"]["change_request"]["change_type"], "fix")

            submitted = service.submit_change_request("change.fix.1", self.context)
            self.assertEqual(submitted["status"], "success")
            approval = submitted["result"]["approval"]
            self.assertEqual(approval["status"], "pending")
            self.assertEqual(approval["subject"], {"change_id": "change.fix.1", "change_type": "fix"})
            self.assertEqual(approval["required_roles"], ["approver"])

    def test_change_request_schema_declares_read_only_proposal_boundary(self):
        schema_path = Path(__file__).parents[1] / "aine_control_plane" / "schema" / "change-request.v1.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertEqual(schema["properties"]["schema"]["const"], CHANGE_REQUEST_SCHEMA)
        self.assertEqual(schema["properties"]["read_only"]["const"], True)
        self.assertEqual(
            set(schema["properties"]["change_type"]["enum"]),
            {"feature", "fix", "requirement", "project_registration"},
        )

    def test_http_routes_require_actor_and_expose_lifecycle(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LocalRecordStore(Path(directory) / "control-plane.sqlite")
            server = ControlPlaneHTTPServer(("127.0.0.1", 0), ControlPlaneService(store))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_address[1]}"
            payload = {
                "change_id": "change.http.test",
                "change_type": "project_registration",
                "title": "Register a workspace",
                "description": "Make a workspace boundary explicit.",
                "scope": {"root_id": "side-projects"},
                "acceptance_criteria": ["The project is represented by a portable identifier."],
                "source_of_truth": [],
                "risk": "low",
                "approval_required": False,
            }
            try:
                with urlopen(f"{base}/v1/change-requests") as response:
                    self.assertEqual(json.loads(response.read())["change_requests"], [])

                missing_actor = Request(
                    f"{base}/v1/change-requests",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with self.assertRaises(HTTPError) as raised:
                    urlopen(missing_actor)
                self.assertEqual(raised.exception.code, 401)

                create = Request(
                    f"{base}/v1/change-requests",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json", "X-AINE-Actor": "agent.codex"},
                    method="POST",
                )
                with urlopen(create) as response:
                    created = json.loads(response.read())
                self.assertEqual(created["status"], "success")

                with urlopen(f"{base}/v1/change-requests/change.http.test") as response:
                    self.assertEqual(json.loads(response.read())["status"], "draft")

                submit = Request(
                    f"{base}/v1/change-requests/change.http.test/submit",
                    data=b"{}",
                    headers={"Content-Type": "application/json", "X-AINE-Actor": "agent.codex"},
                    method="POST",
                )
                with urlopen(submit) as response:
                    submitted = json.loads(response.read())
                self.assertEqual(submitted["result"]["change_request"]["status"], "submitted")
                self.assertEqual(submitted["result"]["change_request"]["revision"], 2)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
