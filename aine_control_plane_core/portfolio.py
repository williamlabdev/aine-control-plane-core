from __future__ import annotations

import json
from typing import Any, Iterable, Mapping

from .contracts import AdapterContext
from .outcomes import AdapterOutcome
from .store import LocalRecordStore
from .validation import find_local_paths


REGISTRY_SNAPSHOT_SCHEMA = "aine.registry.v1"


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
        errors.append(f"unsupported snapshot schema: {snapshot.get('schema')}")
    if not snapshot.get("snapshot_id"):
        errors.append("snapshot.snapshot_id is required")
    for field in ("projects", "artifacts", "dependencies"):
        if not isinstance(snapshot.get(field), list):
            errors.append(f"snapshot.{field} must be an array")
    if "source_of_truth" in snapshot and not isinstance(snapshot.get("source_of_truth"), list):
        errors.append("snapshot.source_of_truth must be an array")
    if "relationships" in snapshot and not isinstance(snapshot.get("relationships"), list):
        errors.append("snapshot.relationships must be an array")
    relationship_records = snapshot.get("relationships", [])
    if not isinstance(relationship_records, list):
        relationship_records = []
    for index, edge in enumerate(relationship_records):
        if not isinstance(edge, Mapping):
            errors.append(f"snapshot.relationships[{index}] must be an object")
            continue
        if not (edge.get("dependency_id") or edge.get("relationship_id")):
            errors.append(f"snapshot.relationships[{index}] is missing edge identity")
        if not isinstance(edge.get("source"), Mapping) or not isinstance(edge.get("target"), Mapping):
            errors.append(f"snapshot.relationships[{index}] is missing edge endpoints")
        evidence = edge.get("evidence", [])
        if not isinstance(evidence, list) or any(not isinstance(item, str) for item in evidence):
            errors.append(f"snapshot.relationships[{index}].evidence must be an array of strings")
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
            edges = list(snapshot.get("dependencies", [])) + list(snapshot.get("relationships", []))
            for edge in edges:
                if not isinstance(edge, Mapping):
                    continue
                edge_id = edge.get("dependency_id") or edge.get("relationship_id")
                if edge_id:
                    dependencies[str(edge_id)] = dict(edge)
        return [dependencies[key] for key in sorted(dependencies)]

    def relationships(
        self,
        project_id: str | None = None,
        relationship_type: str | None = None,
        status: str | None = None,
    ) -> list[Mapping[str, Any]]:
        """Return explicit relationship edges without rescanning repositories."""
        relationships: dict[str, Mapping[str, Any]] = {}
        for snapshot in self.snapshots():
            edges = list(snapshot.get("relationships", []))
            edges.extend(
                edge
                for edge in snapshot.get("dependencies", [])
                if isinstance(edge, Mapping)
                and (edge.get("relationship_type") or edge.get("relationship_source") == "manifest")
            )
            for edge in edges:
                if not isinstance(edge, Mapping):
                    continue
                source = edge.get("source", {})
                target = edge.get("target", {})
                source_id = source.get("project_id") if isinstance(source, Mapping) else None
                target_id = target.get("project_id") if isinstance(target, Mapping) else None
                if project_id is not None and project_id not in {source_id, target_id}:
                    continue
                if relationship_type is not None and edge.get("relationship_type") != relationship_type:
                    continue
                if status is not None and edge.get("status") != status:
                    continue
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
                    relationships[identity] = dict(edge)
                else:
                    merged = dict(current)
                    current_evidence = {item for item in current.get("evidence", []) if isinstance(item, str)}
                    incoming_evidence = {item for item in edge.get("evidence", []) if isinstance(item, str)}
                    evidence = current_evidence | incoming_evidence
                    if evidence:
                        merged["evidence"] = sorted(evidence)
                    relationships[identity] = merged
        return [relationships[key] for key in sorted(relationships)]

    def source_of_truth(
        self,
        domain: str | None = None,
        project_id: str | None = None,
    ) -> list[Mapping[str, Any]]:
        """Return declared source-of-truth rules with optional portable filters."""
        rules: dict[str, Mapping[str, Any]] = {}
        for snapshot in self.snapshots():
            for rule in snapshot.get("source_of_truth", []):
                if not isinstance(rule, Mapping):
                    continue
                if domain is not None and rule.get("domain") != domain:
                    continue
                authority = rule.get("authority", {})
                authority_project = authority.get("project_id") if isinstance(authority, Mapping) else None
                if project_id is not None and authority_project != project_id:
                    continue
                payload = json.dumps(dict(rule), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                identity = str(rule.get("source_rule_id") or f"content:{payload}")
                rules[identity] = dict(rule)
        return [rules[identity] for identity in sorted(rules)]

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
