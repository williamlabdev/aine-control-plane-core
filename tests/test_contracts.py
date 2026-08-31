from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from aine_control_plane.config import AdapterConfig
from aine_control_plane.contracts import AdapterContext, AdapterMetadata, CONTRACT_VERSION
from aine_control_plane.outcomes import AdapterOutcome
from aine_control_plane.validation import (
    canonical_digest,
    validate_adapter_config,
    validate_adapter_metadata,
    validate_context,
    validate_outcome,
    validate_record,
)


class ControlPlaneContractTests(unittest.TestCase):
    def test_metadata_and_context_are_read_only(self):
        metadata = AdapterMetadata("local-evidence", "evidence_sink", capabilities=("put", "get", "list"))
        context = AdapterContext("request-1", actor={"id": "agent.codex"})
        self.assertEqual(validate_adapter_metadata(metadata), [])
        self.assertEqual(validate_context(context), [])
        self.assertTrue(metadata.as_dict()["read_only"])
        self.assertTrue(context.as_dict()["read_only"])

    def test_rejects_mutating_adapter_declarations(self):
        metadata = AdapterMetadata("unsafe", "evidence_sink", read_only=False)
        context = AdapterContext("request-1", read_only=False)
        self.assertIn("core adapters must declare read_only=true", validate_adapter_metadata(metadata))
        self.assertIn("adapter context must be read_only", validate_context(context))

    def test_record_validation_and_stable_digest(self):
        record = {"schema": "aine.evidence.v1", "evidence_id": "evidence.1", "claims": {"status": "pass"}}
        self.assertEqual(validate_record(record), [])
        self.assertEqual(canonical_digest(record), canonical_digest({"claims": record["claims"], "evidence_id": "evidence.1", "schema": "aine.evidence.v1"}))
        self.assertEqual(CONTRACT_VERSION, "aine.control-plane.contracts.v1")

    def test_outcome_and_portable_config_are_machine_readable(self):
        outcome = AdapterOutcome(
            status="success",
            adapter_id="reference.adapter",
            operation="resolve",
            request_id="request-1",
            result={"value": "ok"},
        ).as_dict()
        self.assertEqual(validate_outcome(outcome), [])

        config = AdapterConfig(
            adapter_id="reference.adapter",
            kind="identity",
            options={"source": "fixture"},
            credential_refs=("vault://identity/reference",),
        ).as_dict()
        self.assertEqual(validate_adapter_config(config), [])

        unsafe = dict(config)
        unsafe["options"] = {"api_key": "must-not-be-embedded"}
        self.assertTrue(validate_adapter_config(unsafe))

        local_path = dict(config)
        local_path["options"] = {"path": "/Users/example/evidence.jsonl"}
        self.assertTrue(validate_adapter_config(local_path))

        raw_reference = dict(config)
        raw_reference["credential_refs"] = ["token-value-without-a-scheme"]
        self.assertIn("must be a URI reference", " ".join(validate_adapter_config(raw_reference)))

        secret_bearing_reference = dict(config)
        secret_bearing_reference["credential_refs"] = ["vault://host/path?token=raw-secret-marker"]
        self.assertTrue(validate_adapter_config(secret_bearing_reference))

        for reference in ("vault://host/path?", "vault://host/path#", "vault:///tmp/token"):
            with self.subTest(reference=reference):
                malformed_reference = dict(config)
                malformed_reference["credential_refs"] = [reference]
                self.assertTrue(validate_adapter_config(malformed_reference))

        userinfo_reference = dict(config)
        userinfo_reference["credential_refs"] = ["https://user:raw-secret-marker@example.invalid/ref"]
        self.assertTrue(validate_adapter_config(userinfo_reference))

        malformed_env_reference = dict(config)
        malformed_env_reference["credential_refs"] = ["env://AINE/GITHUB_TOKEN"]
        self.assertTrue(validate_adapter_config(malformed_env_reference))

        missing_credentials = dict(config)
        del missing_credentials["credential_refs"]
        self.assertIn("credential_refs is required", " ".join(validate_adapter_config(missing_credentials)))

        missing_options = dict(config)
        del missing_options["options"]
        self.assertIn("options is required", " ".join(validate_adapter_config(missing_options)))

        file_reference = dict(config)
        file_reference["credential_refs"] = ["file:///tmp/github-token"]
        self.assertTrue(validate_adapter_config(file_reference))

        uppercase_file_reference = dict(config)
        uppercase_file_reference["credential_refs"] = ["FILE://host/tmp/github-token"]
        self.assertTrue(validate_adapter_config(uppercase_file_reference))

        raw_option = dict(config)
        raw_option["options"] = {"github_token": "raw-secret-marker"}
        self.assertTrue(validate_adapter_config(raw_option))

        for key in (
            "GITHUB_TOKEN",
            "foo_token_value",
            "fooTokenValue",
            "API_KEY",
            "api__key",
            "apiKeyValue",
            "fooAccessKeyValue",
            "fooPrivateKey",
            "fooCredentialsValue",
            "fooApi_Key",
            "fooToken_Value",
            "fooTOKENValue",
            "TOKENX",
            "fooAPIApiKey",
            "tokenValue",
            "fileName",
            "credentialValue",
            "pathValue",
            "foo_tokenValue",
        ):
            with self.subTest(key=key):
                keyed_option = dict(config)
                keyed_option["options"] = {key: "raw-secret-marker"}
                self.assertTrue(validate_adapter_config(keyed_option))

        for key in ("profile", "tokenizer", "secretary", "api_endpoint"):
            with self.subTest(key=key):
                opaque_option = dict(config)
                opaque_option["options"] = {key: "opaque-value"}
                self.assertEqual(validate_adapter_config(opaque_option), [])

        nested_reference = dict(config)
        nested_reference["options"] = {"credential_refs": "raw-secret-marker"}
        self.assertTrue(validate_adapter_config(nested_reference))

        unknown_field = dict(config)
        unknown_field["metadata"] = {"token": "raw-secret-marker"}
        self.assertIn("unsupported config field", " ".join(validate_adapter_config(unknown_field)))

        non_json_value = dict(config)
        non_json_value["options"] = {"safe": {1, 2}}
        self.assertTrue(validate_adapter_config(non_json_value))

        numeric_adapter_id = dict(config)
        numeric_adapter_id["adapter_id"] = 7
        self.assertTrue(validate_adapter_config(numeric_adapter_id))

        record_with_path = {"schema": "aine.evidence.v1", "evidence_id": "evidence.path", "claims": {"path": "/Users/example/private.txt"}}
        self.assertTrue(validate_record(record_with_path))

    def test_schema_key_guard_matches_runtime_key_examples(self):
        schema_path = Path(__file__).parents[1] / "aine_control_plane" / "schema" / "adapter-config.v1.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        patterns = tuple(
            item["not"]["pattern"]
            for item in schema["$defs"]["portable_object"]["propertyNames"]["allOf"]
        )
        forbidden = (
            "GITHUB_TOKEN",
            "fooTokenValue",
            "API_KEY",
            "api__key",
            "apiKeyValue",
            "fooAccessKeyValue",
            "fooPrivateKey",
            "fooCredentialsValue",
            "fooApi_Key",
            "fooToken_Value",
            "fooTOKENValue",
            "TOKENX",
            "fooAPIApiKey",
            "workspaceRoot",
        )
        allowed = (
            "profile",
            "tokenizer",
            "secretary",
            "api_endpoint",
            "filename",
            "apiaccesskey",
            "APIaccesskey",
            "fooAPIaccesskeyValue",
        )
        for key in forbidden:
            with self.subTest(key=key):
                self.assertTrue(any(re.search(pattern, key) for pattern in patterns))
                guarded_config = AdapterConfig(
                    adapter_id="reference.adapter",
                    kind="identity",
                    options={key: "raw-secret-marker"},
                    credential_refs=("vault://identity/reference",),
                ).as_dict()
                self.assertTrue(validate_adapter_config(guarded_config))
        for key in allowed:
            with self.subTest(key=key):
                self.assertFalse(any(re.search(pattern, key) for pattern in patterns))
                opaque_config = AdapterConfig(
                    adapter_id="reference.adapter",
                    kind="identity",
                    options={key: "opaque-value"},
                    credential_refs=("vault://identity/reference",),
                ).as_dict()
                self.assertEqual(validate_adapter_config(opaque_config), [])


if __name__ == "__main__":
    unittest.main()
