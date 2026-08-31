from __future__ import annotations

import json
from typing import Any, Iterable, Mapping

from .contracts import AdapterContext
from .outcomes import AdapterOutcome
from .store import LocalRecordStore
from .validation import find_local_paths


REGISTRY_SNAPSHOT_SCHEMA = "aine.registry.v1"


def _evidence_strings(value: Any) -> set[str]:
    if isinstance(value, list):
        return {item for item in value if isinstance(item, str)}
    # Structured evidence remains in the raw observation. Only explicit string
    # references are promoted into the portable evidence_refs union.
    return set()


def _source_rule_identity(rule: Mapping[str, Any]) -> str:
    source_rule_id = rule.get("source_rule_id")
    if isinstance(source_rule_id, str) and source_rule_id.strip():
        return f"id:{source_rule_id}"
    authority = rule.get("authority")
    stable_fields = {
        "domain": rule.get("domain"),
        "authority": dict(authority) if isinstance(authority, Mapping) else authority,
    }
    return "legacy:" + json.dumps(stable_fields, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _merge_observation(
    current: Mapping[str, Any] | None,
    incoming: Mapping[str, Any],
    snapshot_id: str,
) -> Mapping[str, Any]:
    merged = dict(incoming)
    merged["observed_snapshot_id"] = snapshot_id
    if current:
        evidence_refs = _evidence_strings(current.get("evidence_refs"))
        evidence_refs.update(_evidence_strings(current.get("evidence")))
        evidence_refs.update(_evidence_strings(incoming.get("evidence_refs")))
        evidence_refs.update(_evidence_strings(incoming.get("evidence")))
        if evidence_refs:
            merged["evidence_refs"] = sorted(evidence_refs)
    return merged


def _outcome(
    *,
    operation: str,
    context: AdapterContext,
    status: str,
    result: Mapping[str, Any] | None = None,
    error_code: str | None = None,
    reasons: Iterable[str] = (),
    conflict_ids: Iterable[str] = (),
) -> Mapping[str, Any]:
    return AdapterOutcome(
        status=status,
        adapter_id="local.portfolio-registry",
        operation=operation,
        request_id=context.request_id,
        read_only=context.read_only,
        result=result,
        error_code=error_code,
        reasons=tuple(reasons),
        conflict_ids=tuple(conflict_ids),
    ).as_dict()


def validate_snapshot(snapshot: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(snapshot, Mapping):
        return ["snapshot must be an object"]
    if snapshot.get("schema") != REGISTRY_SNAPSHOT_SCHEMA:
        errors.append(f"snapshot.schema must be {REGISTRY_SNAPSHOT_SCHEMA}")
    if not isinstance(snapshot.get("snapshot_id"), str) or not snapshot.get("snapshot_id", "").strip():
        errors.append("snapshot.snapshot_id must be a non-empty string")
    for field in ("projects", "artifacts", "dependencies"):
        if not isinstance(snapshot.get(field), list):
            errors.append(f"snapshot.{field} must be an array")
    projects = snapshot.get("projects", [])
    if isinstance(projects, list):
        for index, project in enumerate(projects):
            if not isinstance(project, Mapping):
                errors.append(f"snapshot.projects[{index}] must be an object")
                continue
            if not isinstance(project.get("project_id"), str) or not project.get("project_id", "").strip():
                errors.append(f"snapshot.projects[{index}].project_id must be a non-empty string")
            if not isinstance(project.get("name"), str) or not project.get("name", "").strip():
                errors.append(f"snapshot.projects[{index}].name must be a non-empty string")
    artifacts = snapshot.get("artifacts", [])
    if isinstance(artifacts, list):
        for index, artifact in enumerate(artifacts):
            if not isinstance(artifact, Mapping):
                errors.append(f"snapshot.artifacts[{index}] must be an object")
                continue
            if not isinstance(artifact.get("artifact_id"), str) or not artifact.get("artifact_id", "").strip():
                errors.append(f"snapshot.artifacts[{index}].artifact_id must be a non-empty string")
    if "source_of_truth" in snapshot and not isinstance(snapshot.get("source_of_truth"), list):
        errors.append("snapshot.source_of_truth must be an array")
    def validate_edge(edge: Any, prefix: str) -> None:
        if not isinstance(edge, Mapping):
            errors.append(f"{prefix} must be an object")
            return
        for identity_field in ("dependency_id", "relationship_id"):
            if identity_field in edge and not isinstance(edge[identity_field], str):
                errors.append(f"{prefix}.{identity_field} must be a string")
        edge_id = edge.get("dependency_id") or edge.get("relationship_id")
        if not isinstance(edge_id, str) or not edge_id.strip():
            errors.append(f"{prefix} is missing a string edge identity")
        for field in ("kind", "relationship_type", "relationship_source", "scope", "strength", "status"):
            if field in edge and not isinstance(edge[field], str):
                errors.append(f"{prefix}.{field} must be a string")
        for endpoint_name in ("source", "target"):
            endpoint = edge.get(endpoint_name)
            if not isinstance(endpoint, Mapping):
                errors.append(f"{prefix}.{endpoint_name} must be an object")
                continue
            for field in ("project_id", "root_id"):
                if field in endpoint and not isinstance(endpoint[field], str):
                    errors.append(f"{prefix}.{endpoint_name}.{field} must be a string")
        evidence = edge.get("evidence")
        if evidence is not None and (
            not isinstance(evidence, Mapping)
            and (not isinstance(evidence, list) or any(not isinstance(item, str) for item in evidence))
        ):
            errors.append(f"{prefix}.evidence must be an array of strings or an object")
        evidence_refs = edge.get("evidence_refs")
        if evidence_refs is not None and (
            not isinstance(evidence_refs, list) or any(not isinstance(item, str) for item in evidence_refs)
        ):
            errors.append(f"{prefix}.evidence_refs must be an array of strings")

    for field in ("dependencies", "relationships"):
        records = snapshot.get(field, [])
        if field == "relationships" and not isinstance(records, list):
            errors.append("snapshot.relationships must be an array")
        if not isinstance(records, list):
            continue
        for index, edge in enumerate(records):
            validate_edge(edge, f"snapshot.{field}[{index}]")
    source_records = snapshot.get("source_of_truth", [])
    if isinstance(source_records, list):
        for index, rule in enumerate(source_records):
            prefix = f"snapshot.source_of_truth[{index}]"
            if not isinstance(rule, Mapping):
                errors.append(f"{prefix} must be an object")
                continue
            for field in ("source_rule_id", "domain", "status"):
                if field in rule and not isinstance(rule[field], str):
                    errors.append(f"{prefix}.{field} must be a string")
            authority = rule.get("authority")
            if authority is not None and not isinstance(authority, Mapping):
                errors.append(f"{prefix}.authority must be an object")
            elif isinstance(authority, Mapping):
                for field in ("project_id", "artifact"):
                    if field in authority and not isinstance(authority[field], str):
                        errors.append(f"{prefix}.authority.{field} must be a string")
            evidence = rule.get("evidence")
            if evidence is not None and (
                not isinstance(evidence, Mapping)
                and (not isinstance(evidence, list) or any(not isinstance(item, str) for item in evidence))
            ):
                errors.append(f"{prefix}.evidence must be an array of strings or an object")
            evidence_refs = rule.get("evidence_refs")
            if evidence_refs is not None and (
                not isinstance(evidence_refs, list) or any(not isinstance(item, str) for item in evidence_refs)
            ):
                errors.append(f"{prefix}.evidence_refs must be an array of strings")
    for path in find_local_paths(snapshot, "snapshot"):
        errors.append(f"runtime-local path is not allowed: {path}")
    return errors


class PortfolioRegistry:
    """Ingest and query portable Registry snapshots without rescanning roots."""

    def __init__(self, store: LocalRecordStore) -> None:
        self.store = store

    def ingest_snapshot(self, snapshot: Mapping[str, Any], context: AdapterContext) -> Mapping[str, Any]:
        errors = validate_snapshot(snapshot)
        if errors:
            return _outcome(
                operation="ingest_snapshot",
                context=context,
                status="failure",
                error_code="invalid_snapshot",
                reasons=errors,
            )
        snapshot_id = str(snapshot["snapshot_id"])
        result = self.store.put(snapshot, context, record_type="snapshot", record_id=snapshot_id)
        if result.get("status") == "success" and not result.get("result", {}).get("duplicate"):
            self.store.append_event("portfolio.snapshot_ingested", snapshot_id, snapshot, context)
        if result.get("status") == "success":
            enriched = dict(result)
            enriched_result = dict(result.get("result", {}))
            enriched_result["summary"] = self._summary(snapshot)
            enriched["result"] = enriched_result
            return enriched
        return result

    def snapshots(self) -> list[Mapping[str, Any]]:
        return self.store.list_records("snapshot")

    def snapshot_ids(self) -> list[str]:
        return [str(snapshot["snapshot_id"]) for snapshot in self.snapshots() if snapshot.get("snapshot_id")]

    def projects(self) -> list[Mapping[str, Any]]:
        projects: dict[str, Mapping[str, Any]] = {}
        for snapshot in self.snapshots():
            for project in snapshot.get("projects", []):
                if isinstance(project, Mapping) and project.get("project_id"):
                    projects[str(project["project_id"])] = dict(project)
        return [projects[key] for key in sorted(projects)]

    def artifacts(self) -> list[Mapping[str, Any]]:
        artifacts: dict[str, Mapping[str, Any]] = {}
        for snapshot in self.snapshots():
            for artifact in snapshot.get("artifacts", []):
                if isinstance(artifact, Mapping) and artifact.get("artifact_id"):
                    artifacts[str(artifact["artifact_id"])] = dict(artifact)
        return [artifacts[key] for key in sorted(artifacts)]

    def dependencies(self) -> list[Mapping[str, Any]]:
        dependencies: dict[str, Mapping[str, Any]] = {}
        for snapshot in self.snapshots():
            snapshot_id = str(snapshot.get("snapshot_id", "UNKNOWN"))
            edges = list(snapshot.get("dependencies", [])) + list(snapshot.get("relationships", []))
            for edge in edges:
                if not isinstance(edge, Mapping):
                    continue
                edge_id = edge.get("dependency_id") or edge.get("relationship_id")
                if edge_id:
                    identity = str(edge_id)
                    dependencies[identity] = dict(_merge_observation(dependencies.get(identity), edge, snapshot_id))
        return [dependencies[key] for key in sorted(dependencies)]

    def relationships(
        self,
        project_id: str | None = None,
        relationship_type: str | None = None,
        status: str | None = None,
    ) -> list[Mapping[str, Any]]:
        """Return declared relationship/dependency edges without rescanning repositories."""
        relationships: dict[str, Mapping[str, Any]] = {}
        for snapshot in self.snapshots():
            snapshot_id = str(snapshot.get("snapshot_id", "UNKNOWN"))
            relationship_records = snapshot.get("relationships", [])
            dependency_records = snapshot.get("dependencies", [])
            edges = list(relationship_records) if isinstance(relationship_records, list) else []
            if isinstance(dependency_records, list):
                # A declared dependency is already an evidence-backed edge. Keep
                # it in the relationship projection so cross-root dependencies
                # remain visible even when no richer relationship_type exists.
                edges.extend(edge for edge in dependency_records if isinstance(edge, Mapping))
            for edge in edges:
                if not isinstance(edge, Mapping):
                    continue
                source = edge.get("source", {})
                target = edge.get("target", {})
                source_id = source.get("project_id") if isinstance(source, Mapping) else None
                target_id = target.get("project_id") if isinstance(target, Mapping) else None
                semantic_identity = json.dumps(
                    {
                        "source": source_id,
                        "target": target_id,
                        "relationship_type": edge.get("relationship_type", edge.get("kind")),
                        "status": edge.get("status"),
                        "strength": edge.get("strength"),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                edge_id = edge.get("dependency_id") or edge.get("relationship_id")
                identity = f"id:{edge_id}" if edge_id else f"legacy:{semantic_identity}"
                current = relationships.get(identity)
                if current is None:
                    relationships[identity] = dict(_merge_observation(None, edge, snapshot_id))
                    continue
                # A later snapshot is the current observation for a stable edge.
                # Preserve earlier evidence while allowing status, endpoints, and
                # other declared fields to move forward with the observation.
                relationships[identity] = dict(_merge_observation(current, edge, snapshot_id))
        filtered: list[Mapping[str, Any]] = []
        for edge in relationships.values():
            source = edge.get("source", {})
            target = edge.get("target", {})
            source_id = source.get("project_id") if isinstance(source, Mapping) else None
            target_id = target.get("project_id") if isinstance(target, Mapping) else None
            if project_id is not None and project_id not in {source_id, target_id}:
                continue
            if relationship_type is not None and (edge.get("relationship_type") or edge.get("kind")) != relationship_type:
                continue
            if status is not None and edge.get("status") != status:
                continue
            filtered.append(edge)
        return sorted(filtered, key=lambda edge: str(edge.get("dependency_id") or edge.get("relationship_id") or ""))

    def source_of_truth(
        self,
        domain: str | None = None,
        project_id: str | None = None,
    ) -> list[Mapping[str, Any]]:
        """Return the latest observed declaration for each source rule."""
        rules: dict[str, Mapping[str, Any]] = {}
        for snapshot in self.snapshots():
            snapshot_id = str(snapshot.get("snapshot_id", "UNKNOWN"))
            source_records = snapshot.get("source_of_truth", [])
            if not isinstance(source_records, list):
                continue
            for rule in source_records:
                if not isinstance(rule, Mapping):
                    continue
                identity = _source_rule_identity(rule)
                rules[identity] = dict(_merge_observation(rules.get(identity), rule, snapshot_id))
        filtered: list[Mapping[str, Any]] = []
        for rule in rules.values():
            authority = rule.get("authority", {})
            authority_project_id = authority.get("project_id") if isinstance(authority, Mapping) else None
            if domain is not None and rule.get("domain") != domain:
                continue
            if project_id is not None and authority_project_id != project_id:
                continue
            filtered.append(rule)
        return sorted(filtered, key=lambda rule: str(rule.get("source_rule_id") or rule.get("domain") or ""))

    def get_project(self, project_id: str) -> Mapping[str, Any] | None:
        for project in self.projects():
            if project.get("project_id") == project_id:
                return project
        return None

    def impact(self, project_id: str) -> Mapping[str, Any]:
        affected: dict[str, Mapping[str, Any]] = {}
        matching_edges: list[Mapping[str, Any]] = []
        for edge in self.dependencies():
            source = edge.get("source", {})
            target = edge.get("target", {})
            source_id = source.get("project_id") if isinstance(source, Mapping) else None
            target_id = target.get("project_id") if isinstance(target, Mapping) else None
            if edge.get("kind") in {"portfolio", "governance", "integration"} and edge.get("impact") is not True:
                continue
            if source_id == project_id or target_id == project_id:
                matching_edges.append(edge)
                other_id = target_id if source_id == project_id else source_id
                if other_id and not str(other_id).startswith("external:"):
                    project = self.get_project(str(other_id))
                    affected[str(other_id)] = project or {"project_id": str(other_id)}
        return {
            "schema": "aine.control-plane.impact-report.v1",
            "project_id": project_id,
            "affected_projects": [affected[key] for key in sorted(affected)],
            "relationships": matching_edges,
            "source_of_truth": self.source_of_truth(project_id=project_id),
            "read_only": True,
        }

    @staticmethod
    def _summary(snapshot: Mapping[str, Any]) -> Mapping[str, int]:
        return {
            "projects": len(snapshot.get("projects", [])),
            "artifacts": len(snapshot.get("artifacts", [])),
            "dependencies": len(snapshot.get("dependencies", [])),
            "source_of_truth": len(snapshot.get("source_of_truth", [])),
        }
