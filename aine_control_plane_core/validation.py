from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any, Mapping
from urllib.parse import urlsplit

from .config import ADAPTER_CONFIG_SCHEMA
from .contracts import AdapterContext, AdapterMetadata, CONTRACT_VERSION
from .outcomes import OUTCOME_SCHEMA, OUTCOME_STATUSES


ADAPTER_KINDS = ("evidence_source", "evidence_sink", "identity", "portfolio_view", "retention")
_FORBIDDEN_CONFIG_KEY_PATTERN = re.compile(
    r"(?:^|[-_])(?:[Aa][Cc][Cc][Ee][Ss][Ss][-_]?[Kk][Ee][Yy]|[Aa][Pp][Ii][-_]?[Kk][Ee][Yy]|[Pp][Rr][Ii][Vv][Aa][Tt][Ee][-_]?[Kk][Ee][Yy]|[Tt][Oo][Kk][Ee][Nn]|[Ss][Ee][Cc][Rr][Ee][Tt]|[Pp][Aa][Ss][Ss][Ww][Oo][Rr][Dd]|[Cc][Rr][Ee][Dd][Ee][Nn][Tt][Ii][Aa][Ll][Ss]?|[Pp][Aa][Tt][Hh]|[Ff][Ii][Ll][Ee]|[Dd][Ii][Rr]|[Dd][Ii][Rr][Ee][Cc][Tt][Oo][Rr][Yy]|[Rr][Oo][Oo][Tt]|[Ww][Oo][Rr][Kk][Ss][Pp][Aa][Cc][Ee]|[Ll][Oo][Cc][Aa][Ll][-_]?[Pp][Aa][Tt][Hh]|[Ff][Ii][Ll][Ee][-_]?[Pp][Aa][Tt][Hh]|[Ww][Oo][Rr][Kk][Ss][Pp][Aa][Cc][Ee][-_]?[Rr][Oo][Oo][Tt])([-_]|$)"
    r"|(?:^|[-_])(?:[Aa][Cc][Cc][Ee][Ss][Ss][-_]?[Kk][Ee][Yy]|[Aa][Pp][Ii][-_]?[Kk][Ee][Yy]|[Pp][Rr][Ii][Vv][Aa][Tt][Ee][-_]?[Kk][Ee][Yy]|[Tt][Oo][Kk][Ee][Nn]|[Ss][Ee][Cc][Rr][Ee][Tt]|[Pp][Aa][Ss][Ss][Ww][Oo][Rr][Dd]|[Cc][Rr][Ee][Dd][Ee][Nn][Tt][Ii][Aa][Ll][Ss]?|[Pp][Aa][Tt][Hh]|[Ff][Ii][Ll][Ee]|[Dd][Ii][Rr]|[Dd][Ii][Rr][Ee][Cc][Tt][Oo][Rr][Yy]|[Rr][Oo][Oo][Tt]|[Ww][Oo][Rr][Kk][Ss][Pp][Aa][Cc][Ee]|[Ll][Oo][Cc][Aa][Ll][-_]?[Pp][Aa][Tt][Hh]|[Ff][Ii][Ll][Ee][-_]?[Pp][Aa][Tt][Hh]|[Ww][Oo][Rr][Kk][Ss][Pp][Aa][Cc][Ee][-_]?[Rr][Oo][Oo][Tt])([A-Z]|[-_]|$)"
    r"|(?:^|[A-Za-z0-9])(?:[A][Cc][Cc][Ee][Ss][Ss][-_]?[Kk][Ee][Yy]|[A][Pp][Ii][-_]?[Kk][Ee][Yy]|[P][Rr][Ii][Vv][Aa][Tt][Ee][-_]?[Kk][Ee][Yy])([A-Z]|[-_]|$)"
    r"|[A-Za-z](?:[T][Oo][Kk][Ee][Nn]|[S][Ee][Cc][Rr][Ee][Tt]|[P][Aa][Ss][Ss][Ww][Oo][Rr][Dd]|[C][Rr][Ee][Dd][Ee][Nn][Tt][Ii][Aa][Ll][Ss]?|[P][Aa][Tt][Hh]|[F][Ii][Ll][Ee]|[D][Ii][Rr]|[R][Oo][Oo][Tt]|[W][Oo][Rr][Kk][Ss][Pp][Aa][Cc][Ee])([A-Z]|[-_]|$)"
    r"|[Aa][Pp][Ii][_-]{2,}[Kk][Ee][Yy]|[Aa][Cc][Cc][Ee][Ss][Ss][_-]{2,}[Kk][Ee][Yy]|[Pp][Rr][Ii][Vv][Aa][Tt][Ee][_-]{2,}[Kk][Ee][Yy]"
)
_LOCAL_PATH_KEYS = {
    "dir",
    "directory",
    "file",
    "file_path",
    "local_path",
    "path",
    "root",
    "workspace",
    "workspace_root",
}
_CREDENTIAL_REFERENCE_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://[^\s/?#\[\]]+(?:/[^\s?#]*)?$")
_ENV_REFERENCE_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ADAPTER_CONFIG_KEYS = {
    "schema",
    "adapter_id",
    "kind",
    "contract_version",
    "options",
    "credential_refs",
    "read_only",
}


def canonical_digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def validate_adapter_metadata(metadata: AdapterMetadata) -> list[str]:
    errors: list[str] = []
    if not metadata.adapter_id:
        errors.append("adapter_id is required")
    if not metadata.kind:
        errors.append("kind is required")
    if metadata.contract_version != CONTRACT_VERSION:
        errors.append(f"unsupported contract_version: {metadata.contract_version}")
    if not metadata.read_only:
        errors.append("core adapters must declare read_only=true")
    return errors


def validate_context(context: AdapterContext) -> list[str]:
    errors: list[str] = []
    if not context.request_id:
        errors.append("request_id is required")
    if not context.read_only:
        errors.append("adapter context must be read_only")
    return errors


def validate_record(record: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(record, Mapping):
        return ["record must be an object"]
    if not record.get("schema"):
        errors.append("record.schema is required")
    if not record.get("evidence_id") and not record.get("approval_id") and not record.get("handoff_id") and not record.get("snapshot_id"):
        errors.append("record must contain a portable identity")
    for path in find_local_paths(record):
        errors.append(f"runtime-local path is not allowed: {path}")
    if record.get("schema") == "aine.control-plane.integration-observation.v1":
        from .integration import validate_integration_observation

        errors.extend(validate_integration_observation(record))
    return errors


def find_local_paths(value: Any, path: str = "record") -> list[str]:
    """Find machine-local filesystem paths in portable data.

    Portable Registry records may legitimately contain root-relative references
    such as ``./service/openapi.yaml`` or ``../aine-registry/README.md``.
    Absolute paths and file URIs remain forbidden because they identify the
    producing machine or require a local filesystem interpretation.
    """

    if isinstance(value, Mapping):
        found: list[str] = []
        for key, nested in value.items():
            found.extend(find_local_paths(nested, f"{path}.{key}"))
        return found
    if isinstance(value, (list, tuple)):
        found = []
        for index, nested in enumerate(value):
            found.extend(find_local_paths(nested, f"{path}[{index}]"))
        return found
    if isinstance(value, str) and (
        value.lower().startswith(("/", "~/", "file://"))
        or value.startswith(("\\\\", "//"))
        or bool(re.match(r"^[A-Za-z]:[\\/]", value))
    ):
        return [path]
    return []


def validate_outcome(outcome: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(outcome, Mapping):
        return ["outcome must be an object"]
    if outcome.get("schema") != OUTCOME_SCHEMA:
        errors.append("unsupported outcome schema")
    if outcome.get("status") not in OUTCOME_STATUSES:
        errors.append("outcome.status must be success, failure, unknown, or conflict")
    for field in ("adapter_id", "operation", "request_id"):
        if not outcome.get(field):
            errors.append(f"outcome.{field} is required")
    if outcome.get("read_only") is not True:
        errors.append("outcome.read_only must be true")
    if outcome.get("status") == "failure" and not outcome.get("error_code"):
        errors.append("failure outcomes require error_code")
    if outcome.get("status") == "unknown" and not outcome.get("reasons"):
        errors.append("unknown outcomes require reasons")
    if outcome.get("status") == "conflict" and not outcome.get("conflict_ids"):
        errors.append("conflict outcomes require conflict_ids")
    return errors


def validate_policy_decision(decision: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(decision, Mapping):
        return ["policy decision must be an object"]
    if decision.get("schema") != "aine.control-plane.policy-decision.v1":
        errors.append("unsupported policy decision schema")
    if decision.get("mode") not in ("advisory", "enforced"):
        errors.append("policy decision mode is unsupported")
    if decision.get("status") not in ("pass", "fail", "unknown", "conflict"):
        errors.append("policy decision status is unsupported")
    if not decision.get("policy_id") or not decision.get("request_id"):
        errors.append("policy_id and request_id are required")
    if decision.get("read_only") is not True:
        errors.append("policy decision must be read_only")
    if decision.get("mode") == "enforced" and decision.get("status") != "pass" and decision.get("blocked") is not True:
        errors.append("enforced non-pass decision must be blocked")
    return errors


def validate_authorization_decision(decision: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(decision, Mapping):
        return ["authorization decision must be an object"]
    if decision.get("schema") != "aine.control-plane.authorization-decision.v1":
        errors.append("unsupported authorization decision schema")
    if decision.get("status") not in ("allow", "deny", "unknown"):
        errors.append("authorization decision status is unsupported")
    for field in ("subject_id", "action", "resource", "request_id"):
        if not decision.get(field):
            errors.append(f"authorization decision {field} is required")
    if decision.get("read_only") is not True:
        errors.append("authorization decision must be read_only")
    return errors


def _secret_keys(value: Any, path: str = "config") -> list[str]:
    if isinstance(value, Mapping):
        found: list[str] = []
        for key, nested in value.items():
            if _contains_forbidden_marker(str(key)):
                found.append(f"{path}.{key}")
            found.extend(_secret_keys(nested, f"{path}.{key}"))
        return found
    if isinstance(value, (list, tuple)):
        found = []
        for index, nested in enumerate(value):
            found.extend(_secret_keys(nested, f"{path}[{index}]"))
        return found
    return []


def _local_path_fields(value: Any, path: str = "config") -> list[str]:
    if isinstance(value, Mapping):
        found: list[str] = []
        for key, nested in value.items():
            key_text = _normalize_config_key(key)
            if key_text in _LOCAL_PATH_KEYS:
                found.append(f"{path}.{key}")
            found.extend(_local_path_fields(nested, f"{path}.{key}"))
        return found
    if isinstance(value, (list, tuple)):
        found = []
        for index, nested in enumerate(value):
            found.extend(_local_path_fields(nested, f"{path}[{index}]"))
        return found
    if isinstance(value, str) and value.lower().startswith(("/", "~/", "./", "../", "file://")):
        return [path]
    return []


def _normalize_config_key(key: Any) -> str:
    text = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", str(key))
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", text)
    return re.sub(r"_+", "_", text.lower().replace("-", "_"))


def _contains_forbidden_marker(raw_key: str) -> bool:
    return bool(_FORBIDDEN_CONFIG_KEY_PATTERN.search(raw_key))


def _json_value_errors(value: Any, path: str) -> list[str]:
    if value is None or isinstance(value, (str, bool, int)):
        return []
    if isinstance(value, float):
        return [] if math.isfinite(value) else [f"{path} must contain finite JSON numbers"]
    if isinstance(value, Mapping):
        errors: list[str] = []
        for key, nested in value.items():
            if not isinstance(key, str):
                errors.append(f"{path} object keys must be strings")
                continue
            errors.extend(_json_value_errors(nested, f"{path}.{key}"))
        return errors
    if isinstance(value, list):
        errors = []
        for index, nested in enumerate(value):
            errors.extend(_json_value_errors(nested, f"{path}[{index}]"))
        return errors
    return [f"{path} must contain only JSON-compatible values"]


def _credential_reference_errors(reference: str, path: str) -> list[str]:
    if not _CREDENTIAL_REFERENCE_PATTERN.fullmatch(reference):
        return [f"{path} must be a URI reference"]
    try:
        parsed = urlsplit(reference)
    except ValueError:
        return [f"{path} must be a valid URI reference"]

    errors: list[str] = []
    if not parsed.netloc:
        errors.append(f"{path} must include a URI authority")
    if parsed.username is not None or parsed.password is not None:
        errors.append(f"{path} must not contain URI userinfo")
    if parsed.scheme == "file":
        errors.append(f"{path} must not use the file:// scheme")
    if "?" in reference or "#" in reference:
        errors.append(f"{path} must not contain a query or fragment")
    if parsed.scheme == "env":
        if parsed.path or not _ENV_REFERENCE_NAME_PATTERN.fullmatch(parsed.netloc):
            errors.append(f"{path} env:// reference must contain one valid environment variable name")
    return errors


def validate_credential_reference(reference: Any) -> list[str]:
    """Validate one non-secret credential reference outside an adapter config."""

    if not isinstance(reference, str):
        return ["credential_ref must be a string"]
    return _credential_reference_errors(reference, "credential_ref")


def validate_adapter_config(config: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(config, Mapping):
        return ["config must be an object"]
    for key in config:
        if key not in _ADAPTER_CONFIG_KEYS:
            errors.append(f"unsupported config field: config.{key}")
    if config.get("schema") != ADAPTER_CONFIG_SCHEMA:
        errors.append("unsupported adapter config schema")
    if not isinstance(config.get("adapter_id"), str) or not config.get("adapter_id"):
        errors.append("config.adapter_id is required")
    if not isinstance(config.get("kind"), str) or config.get("kind") not in ADAPTER_KINDS:
        errors.append("config.kind is unsupported")
    if config.get("contract_version") != CONTRACT_VERSION:
        errors.append(f"unsupported contract_version: {config.get('contract_version')}")
    if config.get("read_only") is not True:
        errors.append("config.read_only must be true")
    if "options" not in config:
        errors.append("config.options is required")
    elif not isinstance(config["options"], Mapping):
        errors.append("config.options must be an object")
    else:
        errors.extend(_json_value_errors(config["options"], "config.options"))
    if "credential_refs" not in config:
        errors.append("config.credential_refs is required")
    credential_refs = config.get("credential_refs", [])
    if not isinstance(credential_refs, list) or not all(isinstance(value, str) for value in credential_refs):
        errors.append("config.credential_refs must be an array of strings")
    else:
        for index, reference in enumerate(credential_refs):
            errors.extend(_credential_reference_errors(reference, f"config.credential_refs[{index}]"))
    for path in _secret_keys(config):
        if path == "config.credential_refs":
            continue
        errors.append(f"raw credential field is not allowed: {path}")
    for path in _local_path_fields(config):
        errors.append(f"runtime-local path is not allowed: {path}")
    return list(dict.fromkeys(errors))
