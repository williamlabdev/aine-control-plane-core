from __future__ import annotations

from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from typing import Any, Iterable, Mapping

from .contracts import AdapterContext


POLICY_DECISION_SCHEMA = "aine.control-plane.policy-decision.v1"
AUTHORIZATION_DECISION_SCHEMA = "aine.control-plane.authorization-decision.v1"
POLICY_MODES = ("advisory", "enforced")
POLICY_STATUSES = ("pass", "fail", "unknown", "conflict")


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if value))


@dataclass(frozen=True)
class PolicyDecision:
    policy_id: str
    mode: str
    status: str
    blocked: bool
    request_id: str
    required_checks: tuple[str, ...] = ()
    missing_checks: tuple[str, ...] = ()
    failures: tuple[str, ...] = ()
    unknowns: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    approval_required: bool = False
    reasons: tuple[str, ...] = ()
    read_only: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": POLICY_DECISION_SCHEMA,
            "policy_id": self.policy_id,
            "mode": self.mode,
            "status": self.status,
            "blocked": self.blocked,
            "request_id": self.request_id,
            "required_checks": list(self.required_checks),
            "missing_checks": list(self.missing_checks),
            "failures": list(self.failures),
            "unknowns": list(self.unknowns),
            "conflicts": list(self.conflicts),
            "evidence_ids": list(self.evidence_ids),
            "approval_required": self.approval_required,
            "reasons": list(self.reasons),
            "read_only": self.read_only,
        }


def evaluate_policy(
    policy: Mapping[str, Any],
    checks: Iterable[Mapping[str, Any]] | Mapping[str, Mapping[str, Any]],
    context: AdapterContext,
    mode: str | None = None,
) -> Mapping[str, Any]:
    policy_id = str(policy.get("policy_id", "policy.unknown"))
    selected_mode = str(mode or policy.get("mode", "advisory"))
    required_checks = tuple(str(value) for value in policy.get("required_checks", []))
    failures: list[str] = []
    unknowns: list[str] = []
    conflicts: list[str] = []
    missing: list[str] = []
    evidence_ids: list[str] = []
    reasons: list[str] = []

    if selected_mode not in POLICY_MODES:
        reasons.append(f"unsupported policy mode: {selected_mode}")
        selected_mode = "advisory"
        unknowns.append("policy.mode")

    if isinstance(checks, Mapping):
        check_map = {str(key): value for key, value in checks.items()}
    else:
        check_map = {str(item.get("check_id")): item for item in checks if item.get("check_id")}

    for check_id in required_checks:
        check = check_map.get(check_id)
        if check is None:
            missing.append(check_id)
            continue
        status = str(check.get("status", "unknown"))
        evidence_ids.extend(str(value) for value in check.get("evidence_ids", []))
        if status == "fail":
            failures.append(check_id)
        elif status == "unknown":
            unknowns.append(check_id)
        elif status == "conflict":
            conflicts.append(check_id)
        elif status != "pass":
            unknowns.append(check_id)
            reasons.append(f"unsupported check status for {check_id}: {status}")

    if conflicts:
        status = "conflict"
    elif missing or unknowns:
        status = "unknown"
    elif failures:
        status = "fail"
    else:
        status = "pass"
    blocked = selected_mode == "enforced" and status != "pass"
    if blocked:
        reasons.append("enforced policy blocks the operation")
    if selected_mode == "advisory" and status != "pass":
        reasons.append("advisory policy reports the finding without blocking")

    return PolicyDecision(
        policy_id=policy_id,
        mode=selected_mode,
        status=status,
        blocked=blocked,
        request_id=context.request_id,
        required_checks=required_checks,
        missing_checks=tuple(missing),
        failures=tuple(failures),
        unknowns=tuple(unknowns),
        conflicts=tuple(conflicts),
        evidence_ids=tuple(_unique(evidence_ids)),
        approval_required=bool(policy.get("approval_required", False)),
        reasons=tuple(reasons),
        read_only=context.read_only,
    ).as_dict()


@dataclass(frozen=True)
class AuthorizationDecision:
    subject_id: str
    action: str
    resource: str
    status: str
    request_id: str
    matched_rule_ids: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    read_only: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": AUTHORIZATION_DECISION_SCHEMA,
            "subject_id": self.subject_id,
            "action": self.action,
            "resource": self.resource,
            "status": self.status,
            "request_id": self.request_id,
            "matched_rule_ids": list(self.matched_rule_ids),
            "reasons": list(self.reasons),
            "read_only": self.read_only,
        }


def authorize(
    subject: Mapping[str, Any],
    rules: Iterable[Mapping[str, Any]],
    action: str,
    resource: str,
    context: AdapterContext,
) -> Mapping[str, Any]:
    subject_id = str(subject.get("subject_id", "unknown"))
    subject_roles = {str(value) for value in subject.get("roles", [])}
    subject_teams = {str(value) for value in subject.get("teams", [])}
    subject_attributes = subject.get("attributes", {})
    if not isinstance(subject_attributes, Mapping):
        subject_attributes = {}

    allows: list[str] = []
    denies: list[str] = []
    unknowns: list[str] = []
    for index, rule in enumerate(rules):
        rule_id = str(rule.get("rule_id", f"rule.{index}"))
        if not fnmatchcase(action, str(rule.get("action", "*"))):
            continue
        if not fnmatchcase(resource, str(rule.get("resource", "*"))):
            continue

        required_roles = {str(value) for value in rule.get("roles", [])}
        required_teams = {str(value) for value in rule.get("teams", [])}
        required_attributes = rule.get("attributes", {})
        if not isinstance(required_attributes, Mapping):
            required_attributes = {}
        if required_roles and not (required_roles & subject_roles):
            continue
        if required_teams and not (required_teams & subject_teams):
            continue
        missing_attributes = [key for key in required_attributes if key not in subject_attributes]
        if missing_attributes:
            unknowns.extend(f"missing subject attribute: {key}" for key in missing_attributes)
            continue
        if any(subject_attributes.get(key) != value for key, value in required_attributes.items()):
            continue

        effect = str(rule.get("effect", "deny"))
        if effect == "allow":
            allows.append(rule_id)
        elif effect == "deny":
            denies.append(rule_id)

    if denies:
        status = "deny"
        reasons = ("explicit deny rule matched",)
        matched = denies + allows
    elif allows:
        status = "allow"
        reasons = ("allow rule matched",)
        matched = allows
    elif unknowns:
        status = "unknown"
        reasons = tuple(unknowns)
        matched = []
    else:
        status = "deny"
        reasons = ("no matching allow rule",)
        matched = []

    return AuthorizationDecision(
        subject_id=subject_id,
        action=action,
        resource=resource,
        status=status,
        request_id=context.request_id,
        matched_rule_ids=tuple(matched),
        reasons=reasons,
        read_only=context.read_only,
    ).as_dict()
