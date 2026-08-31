import type { Adapter, AuditEvent, Contract, EvidenceRecord } from "../types";

export type InsightStatus =
  | "pass"
  | "fail"
  | "unknown"
  | "conflict"
  | "pending"
  | "allow"
  | "deny"
  | "declared"
  | "not_configured";

export type InsightSignal = {
  label: string;
  status: InsightStatus;
  detail: string;
  evidenceIds?: string[];
};

export type PolicyEvaluation = {
  id: string;
  policyId: string;
  mode: string;
  status: InsightStatus;
  blocked: boolean;
  requiredChecks: string[];
  missingChecks: string[];
  failures: string[];
  unknowns: string[];
  conflicts: string[];
  evidenceIds: string[];
  createdAt?: string;
};

export type AuthorizationEvaluation = {
  id: string;
  subjectId: string;
  action: string;
  resource: string;
  status: InsightStatus;
  reasons: string[];
  createdAt?: string;
};

export type ApprovalSummary = {
  id: string;
  status: InsightStatus;
  requestedBy: string;
  requiredRoles: string[];
  decisions: string[];
  evidenceIds: string[];
  createdAt?: string;
};

export type EvaluationCheck = {
  id: string;
  checkId: string;
  policyId: string;
  status: InsightStatus;
  evidenceIds: string[];
};

export type EvaluationRecord = {
  id: string;
  label: string;
  status: InsightStatus;
  source: string;
  evidenceIds: string[];
  detail: string;
  createdAt?: string;
};

export type PortfolioInsights = {
  policyEvaluations: PolicyEvaluation[];
  authorizationEvaluations: AuthorizationEvaluation[];
  approvals: ApprovalSummary[];
  checks: EvaluationCheck[];
  evaluationRecords: EvaluationRecord[];
  securityEvidence: EvidenceRecord[];
  governanceSignals: InsightSignal[];
  securitySignals: InsightSignal[];
};

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function text(value: unknown, fallback = "UNKNOWN") {
  return typeof value === "string" && value.trim() ? value : fallback;
}

function stringList(value: unknown) {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string" && item.trim().length > 0) : [];
}

function status(value: unknown): InsightStatus {
  const normalized = text(value, "unknown").toLowerCase();
  if (["pass", "fail", "unknown", "conflict", "pending", "allow", "deny", "declared", "not_configured"].includes(normalized)) {
    return normalized as InsightStatus;
  }
  return "unknown";
}

function payload(event: AuditEvent) {
  return record(event.payload);
}

function policyEvents(audit: AuditEvent[]) {
  return audit.filter((event) => event.event_type === "policy.evaluated");
}

function policyEvaluations(audit: AuditEvent[]): PolicyEvaluation[] {
  return policyEvents(audit).map((event, index) => {
    const data = payload(event);
    return {
      id: text(event.event_id, `policy-event-${index}`),
      policyId: text(data.policy_id, text(event.aggregate_id, "UNKNOWN")),
      mode: text(data.mode, "UNKNOWN"),
      status: status(data.status),
      blocked: data.blocked === true,
      requiredChecks: stringList(data.required_checks),
      missingChecks: stringList(data.missing_checks),
      failures: stringList(data.failures),
      unknowns: stringList(data.unknowns),
      conflicts: stringList(data.conflicts),
      evidenceIds: stringList(data.evidence_ids),
      createdAt: event.created_at,
    };
  });
}

function authorizationEvaluations(audit: AuditEvent[]): AuthorizationEvaluation[] {
  return audit.filter((event) => event.event_type === "authorization.evaluated").map((event, index) => {
    const data = payload(event);
    return {
      id: text(event.event_id, `authorization-event-${index}`),
      subjectId: text(data.subject_id),
      action: text(data.action),
      resource: text(data.resource, text(event.aggregate_id, "UNKNOWN")),
      status: status(data.status),
      reasons: stringList(data.reasons),
      createdAt: event.created_at,
    };
  });
}

function approvalSummaries(audit: AuditEvent[]): ApprovalSummary[] {
  const summaries = new Map<string, ApprovalSummary>();
  for (const event of audit) {
    if (event.event_type !== "approval.requested" && event.event_type !== "approval.decided") continue;
    const data = payload(event);
    const id = text(data.approval_id, text(event.aggregate_id, "UNKNOWN"));
    const current = summaries.get(id) || {
      id,
      status: "pending" as InsightStatus,
      requestedBy: "UNKNOWN",
      requiredRoles: [],
      decisions: [],
      evidenceIds: [],
      createdAt: event.created_at,
    };
    if (event.event_type === "approval.requested") {
      current.requestedBy = text(data.requested_by);
      current.requiredRoles = stringList(data.required_roles);
      current.evidenceIds = stringList(data.evidence_ids);
    }
    if (event.event_type === "approval.decided") {
      const decision = text(data.decision, "unknown").toLowerCase();
      current.decisions = [...current.decisions, decision];
      current.status = decision === "reject" ? "deny" : decision === "approve" ? "allow" : "unknown";
      current.evidenceIds = [...new Set([...current.evidenceIds, ...stringList(data.evidence_ids)])];
    }
    summaries.set(id, current);
  }
  return [...summaries.values()].sort((left, right) => String(right.createdAt || "").localeCompare(String(left.createdAt || "")));
}

export function evidenceInsightStatus(evidence: EvidenceRecord): InsightStatus {
  const claims = record(evidence.claims);
  return status(evidence.status || claims.status || claims.policy_status || claims.security_status);
}

function explicitlySecurityTagged(evidence: EvidenceRecord) {
  const kind = text(evidence.kind, "").toLowerCase();
  const schema = text(evidence.schema, "").toLowerCase();
  const claims = record(evidence.claims);
  const category = text(claims.category, "").toLowerCase();
  const domain = text(claims.domain, "").toLowerCase();
  const securityKinds = new Set(["security", "security_scan", "vulnerability_scan", "sast", "dast", "dependency_scan", "secret_scan", "sbom"]);
  return securityKinds.has(kind) || kind.includes("security") || schema.includes("security") || category === "security" || domain === "security";
}

function explicitlyEvaluationTagged(evidence: EvidenceRecord) {
  const kind = text(evidence.kind, "").toLowerCase();
  const schema = text(evidence.schema, "").toLowerCase();
  const claims = record(evidence.claims);
  return ["eval", "evaluation", "test", "validation", "preflight", "ci_check", "check"].includes(kind)
    || /eval|validation|preflight/.test(schema)
    || ["check_id", "checks", "policy_status", "finding_ids"].some((key) => key in claims);
}

function evaluationRecords(evidence: EvidenceRecord[], policies: PolicyEvaluation[]): EvaluationRecord[] {
  const policyRecords = policies.map((policy) => ({
    id: policy.id,
    label: policy.policyId,
    status: policy.status,
    source: `policy · ${policy.mode}`,
    evidenceIds: policy.evidenceIds,
    detail: policy.blocked ? "Enforced policy blocked the operation." : `${policy.requiredChecks.length} required checks reported.`,
    createdAt: policy.createdAt,
  }));
  const evidenceRecords = evidence.filter(explicitlyEvaluationTagged).map((item, index) => ({
    id: text(item.record_id || item.evidence_id, `evaluation-evidence-${index}`),
    label: text(item.kind, "evaluation evidence"),
    status: evidenceInsightStatus(item),
    source: text(item.schema, "portable evidence"),
    evidenceIds: stringList(item.evidence_ids || item.evidenceId),
    detail: text(record(item.claims).message, "Evidence-backed evaluation record."),
    createdAt: text(item.observed_at || item.created_at, ""),
  }));
  return [...policyRecords, ...evidenceRecords].sort((left, right) => String(right.createdAt || "").localeCompare(String(left.createdAt || "")));
}

function evaluationChecks(policies: PolicyEvaluation[]): EvaluationCheck[] {
  return policies.flatMap((policy) => policy.requiredChecks.map((checkId) => ({
    id: `${policy.id}:${checkId}`,
    checkId,
    policyId: policy.policyId,
    status: policy.conflicts.includes(checkId)
      ? "conflict"
      : policy.failures.includes(checkId)
        ? "fail"
        : policy.unknowns.includes(checkId) || policy.missingChecks.includes(checkId)
          ? "unknown"
          : "pass",
    evidenceIds: policy.evidenceIds,
  })));
}

function latest<T>(items: T[]) {
  return items.length ? items[items.length - 1] : undefined;
}

export function deriveInsights(
  evidence: EvidenceRecord[],
  audit: AuditEvent[],
  contract: Contract | null,
  adapters: Adapter[],
): PortfolioInsights {
  const policies = policyEvaluations(audit);
  const authorizations = authorizationEvaluations(audit);
  const approvals = approvalSummaries(audit);
  const capabilities = new Set(contract?.capabilities || []);
  const securityEvidence = evidence.filter(explicitlySecurityTagged);
  const securityStatuses = securityEvidence.map(evidenceInsightStatus);
  const securityStatus = securityStatuses.includes("fail")
    ? "fail"
    : securityStatuses.includes("conflict")
      ? "conflict"
      : securityStatuses.includes("unknown")
        ? "unknown"
        : securityStatuses.every((item) => item === "pass")
          ? "pass"
          : "unknown";
  const latestPolicy = latest(policies);
  const latestAuthorization = latest(authorizations);
  const pendingApprovals = approvals.filter((item) => item.status === "pending").length;
  const identityConfigured = adapters.some((adapter) => adapter.metadata?.kind === "identity");

  const governanceSignals: InsightSignal[] = [
    {
      label: "Policy decisions",
      status: latestPolicy?.status || "unknown",
      detail: latestPolicy ? `${latestPolicy.policyId} · ${latestPolicy.mode}` : "No policy.evaluated event observed",
      evidenceIds: latestPolicy?.evidenceIds,
    },
    {
      label: "Authorization",
      status: latestAuthorization?.status || (capabilities.has("authorization_rbac_abac") ? "not_configured" : "unknown"),
      detail: latestAuthorization ? `${latestAuthorization.action} on ${latestAuthorization.resource}` : "No RBAC/ABAC decision observed",
    },
    {
      label: "Approvals",
      status: pendingApprovals ? "pending" : approvals.length ? "pass" : capabilities.has("approval_workflow") ? "not_configured" : "unknown",
      detail: approvals.length ? `${pendingApprovals} pending of ${approvals.length} observed` : "No approval workflow event observed",
    },
    {
      label: "Audit stream",
      status: audit.length ? "pass" : "unknown",
      detail: audit.length ? `${audit.length} append-only events observed` : "No audit events observed",
    },
  ];

  const securitySignals: InsightSignal[] = [
    {
      label: "Read-only contract",
      status: contract?.read_only === true ? "declared" : "unknown",
      detail: contract?.read_only === true ? "Service contract declares read_only=true" : "Contract read-only state is unavailable",
    },
    {
      label: "Credential boundary",
      status: capabilities.has("credential_provider_boundary") ? "declared" : "unknown",
      detail: capabilities.has("credential_provider_boundary") ? "Credential references stay behind an adapter boundary" : "Credential boundary capability not observed",
    },
    {
      label: "Identity adapter",
      status: identityConfigured ? "pass" : "not_configured",
      detail: identityConfigured ? "An identity adapter is configured" : "No identity adapter is configured in this service",
    },
    {
      label: "Security evidence",
      status: securityEvidence.length ? securityStatus : "unknown",
      detail: securityEvidence.length ? `${securityEvidence.length} explicitly security-tagged records observed` : "No explicitly security-tagged evidence observed",
      evidenceIds: securityEvidence.map((item) => text(item.record_id || item.evidence_id, "UNKNOWN")),
    },
  ];

  return {
    policyEvaluations: policies,
    authorizationEvaluations: authorizations,
    approvals,
    checks: evaluationChecks(policies),
    evaluationRecords: evaluationRecords(evidence, policies),
    securityEvidence,
    governanceSignals,
    securitySignals,
  };
}
