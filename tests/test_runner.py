from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from aine_control_plane_core.contracts import AdapterContext
from aine_control_plane_core.validation import validate_outcome
from aine_control_plane_core.runner import (
    PATCH_ARTIFACT_SCHEMA,
    RUNNER_SESSION_SCHEMA,
    VALIDATION_REPORT_SCHEMA,
    validate_patch_artifact,
    validate_runner_session,
    validate_validation_report,
)
from aine_control_plane_core.service import ControlPlaneService
from aine_control_plane_core.server import ControlPlaneHTTPServer
from aine_control_plane_core.store import LocalRecordStore


FIXTURE_DIR = Path(__file__).parents[1] / "aine_control_plane_core" / "fixtures"


class RunnerWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.developer = AdapterContext(
            "runner-test",
            actor={"id": "runner.external", "roles": ["developer"], "teams": ["platform"]},
        )

    def _prepare_execution(self, service: ControlPlaneService, suffix: str = "runner-test") -> str:
        plan = service.create_remediation_plan(
            {
                "plan_id": f"remediation.plan.{suffix}",
                "title": "Prepare a runner patch",
                "rationale": "Collect isolated validation evidence.",
                "finding": {"summary": "Evidence needs review."},
                "scope": {"project_ids": ["reference.consumer"]},
                "strategy": {"description": "Prepare a portable patch artifact."},
                "validation": {"required_checks": ["registry.validate", "preflight"]},
                "acceptance_criteria": ["Evidence is reported."],
                "risk": "low",
                "approval_required": False,
            },
            self.developer,
        )
        self.assertEqual(plan["status"], "success")
        plan_id = f"remediation.plan.{suffix}"
        self.assertEqual(service.submit_remediation_plan(plan_id, self.developer)["status"], "success")
        execution = service.request_remediation_dry_run(plan_id, self.developer)
        self.assertEqual(execution["status"], "success")
        return execution["result"]["execution"]["execution_id"]

    def test_fixtures_validate_and_preserve_unknowns(self):
        validators = (
            ("runner_session.json", validate_runner_session, RUNNER_SESSION_SCHEMA),
            ("patch_artifact.json", validate_patch_artifact, PATCH_ARTIFACT_SCHEMA),
            ("validation_report.json", validate_validation_report, VALIDATION_REPORT_SCHEMA),
        )
        for filename, validator, schema in validators:
            with self.subTest(filename=filename):
                record = json.loads((FIXTURE_DIR / filename).read_text(encoding="utf-8"))
                self.assertEqual(record["schema"], schema)
                self.assertEqual(validator(record), [])

    def test_external_runner_session_patch_and_validation_are_append_only(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LocalRecordStore(Path(directory) / "control-plane.sqlite")
            service = ControlPlaneService(store)
            execution_id = self._prepare_execution(service)

            session_result = service.create_runner_session(
                execution_id,
                {"correlation_id": "corr.runner.test"},
                self.developer,
            )
            self.assertEqual(session_result["status"], "success")
            session = session_result["result"]["session"]
            duplicate_session = service.create_runner_session(execution_id, {}, self.developer)
            self.assertTrue(duplicate_session["result"]["duplicate"])
            self.assertEqual(session["schema"], RUNNER_SESSION_SCHEMA)
            self.assertEqual(session["correlation_id"], "corr.runner.test")
            self.assertTrue(session["read_only"])
            self.assertFalse(session["mutation_scope"]["source_repositories"])

            mismatched_patch = service.create_patch_artifact(
                session["session_id"],
                {"correlation_id": "corr.other", "status": "proposed"},
                self.developer,
            )
            self.assertEqual(mismatched_patch["status"], "conflict")
            self.assertEqual(mismatched_patch["error_code"], "runner_correlation_mismatch")

            patch_result = service.create_patch_artifact(
                session["session_id"],
                {
                    "patch_id": "patch.runner-test",
                    "format": "file_manifest",
                    "content_digest": "sha256:" + "b" * 64,
                    "artifact_ref": "urn:aine:patch:runner-test",
                    "files": [{"path": "service/api.yaml", "change": "modified"}],
                    "change_summary": "Prepare relationship evidence.",
                    "evidence_ids": ["evidence.patch"],
                },
                self.developer,
            )
            self.assertEqual(patch_result["status"], "success")
            patch = patch_result["result"]["patch_artifact"]
            self.assertEqual(patch["correlation_id"], session["correlation_id"])

            mismatched_report = service.create_validation_report(
                session["session_id"],
                {"correlation_id": "corr.other", "summary": "mismatch", "checks": []},
                self.developer,
            )
            self.assertEqual(mismatched_report["status"], "conflict")
            self.assertEqual(mismatched_report["error_code"], "runner_correlation_mismatch")

            report_result = service.create_validation_report(
                session["session_id"],
                {
                    "report_id": "validation.runner-test",
                    "status": "unknown",
                    "summary": "The preflight result was not observable.",
                    "checks": [{"check_id": "registry.validate", "status": "pass", "summary": "Snapshot is valid."}],
                    "missing_check_ids": ["preflight"],
                    "evidence_ids": ["evidence.validation"],
                },
                self.developer,
            )
            self.assertEqual(report_result["status"], "success")
            report = report_result["result"]["validation_report"]
            self.assertEqual(report["status"], "unknown")
            self.assertEqual(report["missing_check_ids"], ["preflight"])
            self.assertEqual(report["correlation_id"], session["correlation_id"])

            current = service.get_runner_session(session["session_id"])
            self.assertIn(patch["patch_id"], current["patch_artifact_ids"])
            self.assertIn(report["report_id"], current["validation_report_ids"])

            append_only = service.report_runner_session(
                session["session_id"],
                {"status": "running", "patch_artifact_ids": [], "validation_report_ids": []},
                self.developer,
            )
            self.assertEqual(append_only["status"], "success")
            current = service.get_runner_session(session["session_id"])
            self.assertIn(patch["patch_id"], current["patch_artifact_ids"])
            self.assertIn(report["report_id"], current["validation_report_ids"])

            completed = service.report_runner_session(
                session["session_id"],
                {"status": "completed", "evidence_ids": ["evidence.patch", "evidence.validation"]},
                self.developer,
            )
            self.assertEqual(completed["status"], "success")
            self.assertEqual(service.get_runner_session(session["session_id"])["status"], "completed")
            self.assertGreaterEqual(service.get_runner_session(session["session_id"])["revision"], 4)
            self.assertIn("runner.patch.created", [event["event_type"] for event in store.list_events()])
            self.assertIn("runner.validation.reported", [event["event_type"] for event in store.list_events()])

            closed_patch = service.create_patch_artifact(
                session["session_id"],
                {
                    "format": "file_manifest",
                    "content_digest": "sha256:" + "e" * 64,
                    "files": [{"path": "service.py", "change": "modified"}],
                    "change_summary": "Must not be accepted after completion.",
                },
                self.developer,
            )
            self.assertEqual(closed_patch["error_code"], "runner_session_closed")
            closed_report = service.create_validation_report(
                session["session_id"],
                {"summary": "Must not be accepted after completion.", "checks": []},
                self.developer,
            )
            self.assertEqual(closed_report["error_code"], "runner_session_closed")

    def test_runner_rejects_invalid_relationships_and_conflict_outcomes(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LocalRecordStore(Path(directory) / "control-plane.sqlite")
            service = ControlPlaneService(store)
            execution_id = self._prepare_execution(service)
            session = service.create_runner_session(execution_id, {}, self.developer)["result"]["session"]
            phantom = service.report_runner_session(
                session["session_id"],
                {"status": "running", "patch_artifact_ids": ["patch.missing"]},
                self.developer,
            )
            self.assertEqual(phantom["error_code"], "invalid_runner_relationships")
            self.assertEqual(service.get_runner_session(session["session_id"])["revision"], 1)

            second_execution = self._prepare_execution(service, "runner-test-second")
            conflict = service.create_runner_session(
                second_execution,
                {"session_id": session["session_id"]},
                self.developer,
            )
            self.assertEqual(conflict["status"], "conflict")
            self.assertEqual(validate_outcome(conflict), [])

            patch = service.create_patch_artifact(
                session["session_id"],
                {
                    "patch_id": "patch.runner-owned",
                    "format": "file_manifest",
                    "content_digest": "sha256:" + "f" * 64,
                    "files": [{"path": "service.py", "change": "modified"}],
                    "change_summary": "Owned by the first session.",
                },
                self.developer,
            )
            self.assertEqual(patch["status"], "success")
            second_session = service.create_runner_session(second_execution, {}, self.developer)["result"]["session"]
            wrong_owner = service.report_runner_session(
                second_session["session_id"],
                {"status": "running", "patch_artifact_ids": ["patch.runner-owned"]},
                self.developer,
            )
            self.assertEqual(wrong_owner["error_code"], "invalid_runner_relationships")

    def test_runner_rejects_paths_raw_patch_and_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LocalRecordStore(Path(directory) / "control-plane.sqlite")
            service = ControlPlaneService(store)
            execution_id = self._prepare_execution(service)
            session = service.create_runner_session(execution_id, {}, self.developer)["result"]["session"]

            leaked = dict(session)
            leaked["workspace_ref"] = "file:///Users/example/worktree"
            self.assertTrue(validate_runner_session(leaked))
            unsafe_correlation = dict(session)
            unsafe_correlation["correlation_id"] = "../local-run"
            self.assertTrue(validate_runner_session(unsafe_correlation))

            absolute_patch = {
                "format": "file_manifest",
                "content_digest": "sha256:" + "c" * 64,
                "files": [{"path": "/Users/example/service.py", "change": "modified"}],
                "change_summary": "should be rejected",
            }
            result = service.create_patch_artifact(session["session_id"], absolute_patch, self.developer)
            self.assertEqual(result["status"], "failure")
            self.assertEqual(result["error_code"], "invalid_patch_artifact")

            applied = dict(absolute_patch)
            applied["files"] = [{"path": "service.py", "change": "modified"}]
            applied["status"] = "applied"
            applied_result = service.create_patch_artifact(session["session_id"], applied, self.developer)
            self.assertEqual(applied_result["status"], "failure")
            self.assertEqual(applied_result["error_code"], "patch_application_not_allowed")

            raw = dict(absolute_patch)
            raw["files"] = [{"path": "service.py", "change": "modified"}]
            raw["diff"] = "@@ source content must stay outside the Control Plane @@"
            raw_result = service.create_patch_artifact(session["session_id"], raw, self.developer)
            self.assertEqual(raw_result["status"], "failure")
            self.assertEqual(raw_result["error_code"], "raw_patch_payload_not_accepted")

            for path in (
                "../outside.py",
                "src/../../outside.py",
                "https://example.invalid/source.py",
            ):
                invalid = dict(absolute_patch)
                invalid["files"] = [{"path": path, "change": "modified"}]
                invalid_result = service.create_patch_artifact(session["session_id"], invalid, self.developer)
                self.assertEqual(invalid_result["error_code"], "invalid_patch_artifact")

            direct = json.loads((FIXTURE_DIR / "patch_artifact.json").read_text(encoding="utf-8"))
            direct["diff"] = "raw content"
            self.assertTrue(validate_patch_artifact(direct))
            direct.pop("diff")
            direct["files"] = [{"path": "../outside.py", "change": "modified"}]
            self.assertTrue(validate_patch_artifact(direct))

            report = json.loads((FIXTURE_DIR / "validation_report.json").read_text(encoding="utf-8"))
            report.pop("evidence_ids")
            self.assertTrue(validate_validation_report(report))

            empty_scope = json.loads((FIXTURE_DIR / "runner_session.json").read_text(encoding="utf-8"))
            empty_scope["project_ids"] = []
            self.assertTrue(validate_runner_session(empty_scope))

            malformed_report = service.create_validation_report(
                session["session_id"],
                {
                    "summary": "Malformed checks must remain visible to the validator.",
                    "checks": ["not-an-object"],
                },
                self.developer,
            )
            self.assertEqual(malformed_report["error_code"], "invalid_validation_report")
            self.assertEqual(service.list_validation_reports(), [])

    def test_runner_http_routes_expose_portable_records(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LocalRecordStore(Path(directory) / "control-plane.sqlite")
            service = ControlPlaneService(store)
            execution_id = self._prepare_execution(service)
            server = ControlPlaneHTTPServer(("127.0.0.1", 0), service)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                create = Request(
                    f"{base}/v1/execution-requests/{execution_id}/runner-session",
                    data=b"{}",
                    headers={"Content-Type": "application/json", "X-AINE-Actor": "runner.external"},
                    method="POST",
                )
                with urlopen(create) as response:
                    self.assertEqual(response.status, 201)
                    session = json.loads(response.read())["result"]["session"]

                with urlopen(f"{base}/v1/runner-sessions") as response:
                    sessions = json.loads(response.read())
                self.assertEqual(sessions["sessions"][0]["session_id"], session["session_id"])

                patch = Request(
                    f"{base}/v1/runner-sessions/{session['session_id']}/patch-artifacts",
                    data=json.dumps({
                        "format": "file_manifest",
                        "content_digest": "sha256:" + "d" * 64,
                        "files": [{"path": "service.py", "change": "modified"}],
                        "change_summary": "Portable patch metadata",
                    }).encode("utf-8"),
                    headers={"Content-Type": "application/json", "X-AINE-Actor": "runner.external"},
                    method="POST",
                )
                with urlopen(patch) as response:
                    self.assertEqual(response.status, 201)

                report = Request(
                    f"{base}/v1/runner-sessions/{session['session_id']}/validation-reports",
                    data=json.dumps({
                        "status": "conflict",
                        "summary": "Two validation sources disagree.",
                        "checks": [{"check_id": "preflight", "status": "conflict", "summary": "Conflicting evidence."}],
                    }).encode("utf-8"),
                    headers={"Content-Type": "application/json", "X-AINE-Actor": "runner.external"},
                    method="POST",
                )
                with urlopen(report) as response:
                    self.assertEqual(response.status, 201)
                    validation = json.loads(response.read())["result"]["validation_report"]
                self.assertEqual(validation["status"], "conflict")

                session_report = Request(
                    f"{base}/v1/runner-sessions/{session['session_id']}/report",
                    data=json.dumps({"status": "completed"}).encode("utf-8"),
                    headers={"Content-Type": "application/json", "X-AINE-Actor": "runner.external"},
                    method="POST",
                )
                with urlopen(session_report) as response:
                    self.assertEqual(response.status, 200)
                    completed = json.loads(response.read())["result"]["session"]
                self.assertEqual(completed["status"], "completed")

                closed_patch = Request(
                    f"{base}/v1/runner-sessions/{session['session_id']}/patch-artifacts",
                    data=json.dumps({
                        "format": "file_manifest",
                        "content_digest": "sha256:" + "e" * 64,
                        "files": [{"path": "service.py", "change": "modified"}],
                        "change_summary": "Closed sessions reject new artifacts.",
                    }).encode("utf-8"),
                    headers={"Content-Type": "application/json", "X-AINE-Actor": "runner.external"},
                    method="POST",
                )
                with self.assertRaises(HTTPError) as error:
                    urlopen(closed_patch)
                self.assertEqual(error.exception.code, 409)

                closed_report = Request(
                    f"{base}/v1/runner-sessions/{session['session_id']}/validation-reports",
                    data=json.dumps({"summary": "Closed sessions reject new reports.", "checks": []}).encode("utf-8"),
                    headers={"Content-Type": "application/json", "X-AINE-Actor": "runner.external"},
                    method="POST",
                )
                with self.assertRaises(HTTPError) as error:
                    urlopen(closed_report)
                self.assertEqual(error.exception.code, 409)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
