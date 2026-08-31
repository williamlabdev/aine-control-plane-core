"""End-to-end exercise of the correlated portfolio chain.

A real producer run becomes an observation, the observation joins a stored
portfolio snapshot, and the correlation identifier answers as a query. Every
other test in this suite checks one link; this one checks that the links hold
when a separate process, a real store, and real producer output are involved.

Two neighbours are needed and neither is a dependency of this package, so the
whole class skips unless both are present:

    AINE_REGISTRY_PATH    an AINE Registry checkout, driven through its CLI
                          (defaults to a sibling `aine-registry` directory)
    AINE_AIRT_LIVE_PATH   a directory of airt run directories, each holding an
                          `events.db` and the `airt.pub` beside it

The airt databases are live local output, never fixtures, so there is no
default for the second path.
"""

from __future__ import annotations

import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from urllib.request import urlopen

from aine_control_plane.adapters import AirtChainProjectionAdapter
from aine_control_plane.contracts import AdapterContext

# One portfolio review is one correlation. airt records its own session
# identifier per run; that is airt's identity, not the portfolio's, so the
# caller supplies the correlation the way a real integration would.
CORRELATION = "chain.e2e.portfolio"


def _registry_path() -> Path:
    return Path(os.environ.get("AINE_REGISTRY_PATH")
                or Path(__file__).parents[2] / "aine-registry")


def _airt_runs_path() -> Path | None:
    value = os.environ.get("AINE_AIRT_LIVE_PATH")
    return Path(value) if value else None


def _chain_available() -> bool:
    registry = _registry_path()
    if not (registry / "registry" / "aine_registry.py").is_file():
        return False
    airt = _airt_runs_path()
    return bool(airt and any(airt.glob("*/events.db")))


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _read_airt_run(db_path: Path) -> list[dict]:
    """Read whole runs out of a live airt event database, read-only.

    airt keeps the signing anchor's public half in `airt.pub` beside the
    database rather than in a column. A caller that reads only the events has
    a sealed run it cannot show a key for, which this core reports as a
    conflict; reading the key is the integration's job.
    """

    public_key_path = db_path.parent / "airt.pub"
    public_key = public_key_path.read_text(encoding="utf-8").strip() if public_key_path.is_file() else ""
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    runs: dict[str, dict] = {}
    order: list[str] = []
    try:
        for row in connection.execute("select * from events order by seq"):
            event = dict(row)
            run_id = event["run_id"]
            if run_id not in runs:
                runs[run_id] = {
                    "run_id": run_id,
                    "correlation_id": CORRELATION,
                    "verdict": "",
                    "rule": "",
                    "tool": "",
                    "events": [],
                    "final_hash": "",
                    "public_key": public_key,
                    "sealed": False,
                }
                order.append(run_id)
            run = runs[run_id]
            run["events"].append({
                "seq": event["seq"],
                "direction": event["direction"],
                "method": event["method"],
                "args_hash": event["args_hash"],
                "hash": event["hash"],
                # Carried deliberately: the projection must drop these and say so.
                "tool_name": event["tool_name"],
                "payload": event["payload"],
            })
            for source, target in (("verdict", "verdict"), ("matched_policy", "rule"), ("tool_name", "tool")):
                if event[source]:
                    run[target] = event[source]
            if event["hash"]:
                run["final_hash"] = event["hash"]
            if event["sig"]:
                run["sealed"] = True
    finally:
        connection.close()
    return [runs[run_id] for run_id in order]


@unittest.skipUnless(
    _chain_available(),
    "set AINE_AIRT_LIVE_PATH (and AINE_REGISTRY_PATH if the checkout is not a sibling)",
)
class PortfolioChainE2ETests(unittest.TestCase):
    """One correlated review, walked from producer output to scoped query."""

    @classmethod
    def setUpClass(cls):
        cls.registry = _registry_path()
        cls._workspace = tempfile.TemporaryDirectory(prefix="aine-chain-e2e-")
        work = Path(cls._workspace.name)
        cls.store = work / "store"
        cls.snapshot_path = work / "snapshot.json"

        cls._registry_cli(
            "scan",
            "--root", str(cls.registry),
            "--root", str(Path(__file__).parents[1]),
            "--output", str(cls.snapshot_path),
        )
        cls.snapshot = json.loads(cls.snapshot_path.read_text(encoding="utf-8"))
        cls.snapshot_record_id = json.loads(
            cls._registry_cli("evidence", "store", "--input", str(cls.snapshot_path),
                              "--store", str(cls.store)).stdout
        )["record_id"]

        cls.runs = []
        for database in sorted(_airt_runs_path().glob("*/events.db")):
            cls.runs.extend(_read_airt_run(database))
        cls.assertRunsExist = bool(cls.runs)

        adapter = AirtChainProjectionAdapter()
        cls.outcomes = []
        for index, run in enumerate(cls.runs):
            context = AdapterContext(f"chain.e2e.{index:02d}", actor={"id": "agent.e2e"})
            cls.outcomes.append(
                adapter.collect({"run": run, "snapshot_id": cls.snapshot_record_id}, context)
            )

        cls.observation_ids = []
        cls.observation_paths = []
        for index, outcome in enumerate(cls.outcomes):
            path = work / f"observation-{index:02d}.json"
            path.write_text(json.dumps(outcome["result"], indent=2), encoding="utf-8")
            cls.observation_paths.append(path)
            cls.observation_ids.append(json.loads(
                cls._registry_cli("evidence", "store", "--input", str(path),
                                  "--store", str(cls.store)).stdout
            )["record_id"])

    @classmethod
    def tearDownClass(cls):
        cls._workspace.cleanup()

    @classmethod
    def _registry_cli(cls, *arguments, expect_success: bool = True):
        process = subprocess.run(
            [sys.executable, "-m", "registry.aine_registry", *arguments],
            cwd=cls.registry, capture_output=True, text=True,
        )
        if expect_success and process.returncode != 0:
            raise AssertionError(f"registry CLI failed: {arguments}\n{process.stdout}\n{process.stderr}")
        return process

    def _list(self, *arguments):
        return json.loads(self._registry_cli("evidence", "list", "--store", str(self.store),
                                             *arguments).stdout)

    def _export(self, *arguments):
        return json.loads(self._registry_cli("evidence", "export", "--store", str(self.store),
                                             *arguments).stdout)

    def test_every_live_run_produced_a_valid_observation(self):
        self.assertTrue(self.runs, "no live airt runs were readable")
        for run, outcome in zip(self.runs, self.outcomes):
            with self.subTest(run_id=run["run_id"]):
                self.assertIn(outcome["status"], ("success", "conflict"), outcome.get("reasons"))
                self.assertEqual(outcome["result"]["correlation_id"], CORRELATION)
                self.assertEqual(outcome["result"]["snapshot_id"], self.snapshot_record_id)

    def test_a_denied_run_is_a_failed_run_not_a_failed_collection(self):
        denied = [outcome for run, outcome in zip(self.runs, self.outcomes) if run["verdict"] == "deny"]
        self.assertTrue(denied, "no denied run was available to observe")
        for outcome in denied:
            self.assertEqual(outcome["status"], "success")
            self.assertEqual(outcome["result"]["status"], "failure")

    def test_the_projection_drops_non_portable_fields_and_says_so(self):
        for outcome in self.outcomes:
            self.assertTrue(
                any("dropped non-portable event fields" in reason for reason in outcome["reasons"]),
                outcome["reasons"],
            )
        stored = "".join(path.read_text(encoding="utf-8") for path in self.observation_paths)
        self.assertNotIn("payload", stored)
        self.assertNotIn("tool_name", stored)

    def test_neither_half_of_the_signing_key_reaches_the_store(self):
        stored = "".join(path.read_text(encoding="utf-8") for path in self.observation_paths)
        secrets = []
        for directory in sorted(_airt_runs_path().glob("*/events.db")):
            for name in ("airt.pub", "airt.key"):
                candidate = directory.parent / name
                if candidate.is_file():
                    secrets.append(candidate.read_bytes().hex())
                    secrets.append(candidate.read_bytes().decode("utf-8", "ignore").strip())
        self.assertTrue(secrets, "no signing material was present to check against")
        for secret in secrets:
            if secret:
                self.assertNotIn(secret, stored)

    def test_the_snapshot_keeps_its_content_digest_apart_from_its_store_identity(self):
        self.assertTrue(self.snapshot_record_id.startswith("sha256:"))
        self.assertNotEqual(self.snapshot_record_id, self.snapshot["snapshot_id"])

    def test_a_scoped_listing_returns_the_correlated_records_and_no_others(self):
        scoped = self._list("--correlation", CORRELATION)
        self.assertEqual(len(scoped), len(self.observation_ids))
        self.assertEqual(len(self._list()), len(self.observation_ids) + 1)

    def test_a_scoped_bundle_declares_its_scope_and_names_what_it_left_out(self):
        bundle = self._export("--correlation", CORRELATION)
        self.assertEqual(bundle["correlation_id"], CORRELATION)
        self.assertEqual(len(bundle["record_ids"]), len(self.observation_ids))
        reference = next(entry for entry in bundle["unresolved_refs"]
                         if entry["record_id"] == self.snapshot_record_id)
        self.assertEqual(reference["status"], "out_of_scope")
        self.assertEqual(sorted(reference["referenced_by"]), sorted(self.observation_ids))

    def test_an_unscoped_bundle_claims_no_scope_and_resolves_every_reference(self):
        bundle = self._export()
        self.assertNotIn("correlation_id", bundle)
        self.assertEqual(bundle["unresolved_refs"], [])
        self.assertEqual(len(bundle["record_ids"]), len(self.observation_ids) + 1)

    def test_the_read_only_api_answers_the_same_correlation_question(self):
        port = _free_port()
        server = subprocess.Popen(
            [sys.executable, "-u", "-m", "registry.aine_registry", "serve",
             "--snapshot", str(self.snapshot_path), "--store", str(self.store),
             "--host", "127.0.0.1", "--port", str(port)],
            cwd=self.registry, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        try:
            base = f"http://127.0.0.1:{port}"
            served = None
            for _ in range(200):
                if server.poll() is not None:
                    break
                try:
                    with urlopen(f"{base}/api/evidence?correlation={CORRELATION}") as response:
                        served = json.load(response)
                    break
                except OSError:
                    time.sleep(0.05)
            self.assertIsNotNone(served, "the served API never became reachable")
            self.assertEqual(len(served), len(self.observation_ids))
            with urlopen(f"{base}/api/evidence") as response:
                self.assertEqual(len(json.load(response)), len(self.observation_ids) + 1)
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()

    def test_a_tampered_record_is_refused_on_read_but_stays_visible_in_a_listing(self):
        target = self.store / (self.observation_ids[0].split(":", 1)[1] + ".json")
        original = target.read_text(encoding="utf-8")
        document = json.loads(original)
        document["record"]["claims"]["verdict"] = "tampered-not-a-real-verdict"
        target.write_text(json.dumps(document), encoding="utf-8")
        try:
            read = self._registry_cli("evidence", "get", "--id", self.observation_ids[0],
                                      "--store", str(self.store), expect_success=False)
            self.assertNotEqual(read.returncode, 0)
            # A record whose correlation cannot be read cannot honestly be
            # filtered out of a scoped listing, and a broken store is relevant
            # to every review that might otherwise miss it.
            scoped = self._list("--correlation", CORRELATION)
            self.assertTrue(any(entry.get("status") == "invalid" for entry in scoped))
        finally:
            target.write_text(original, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
