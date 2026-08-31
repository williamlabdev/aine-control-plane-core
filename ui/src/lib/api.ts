import type {
  Adapter,
  AuditEvent,
  Contract,
  EvidenceRecord,
  Health,
  ImpactReport,
  PortfolioProvenance,
  Project,
  SourceOfTruth,
  Dependency,
  ChangeRequest,
  ExecutionRequest,
  RemediationPlan,
  RunnerSession,
  PatchArtifact,
  ValidationReport,
} from "../types";

const baseUrl = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");
const actor = import.meta.env.VITE_AINE_ACTOR || "";

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...(actor ? { "X-AINE-Actor": actor } : {}),
      ...init.headers,
    },
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return (await response.json()) as T;
}

export const api = {
  health: () => request<Health>("/healthz"),
  contract: () => request<Contract>("/v1/contract"),
  adapters: async () => {
    const response = await request<{ adapters?: Adapter[] }>("/v1/adapters");
    return response.adapters || [];
  },
  projects: async () => {
    const response = await request<{ projects?: Project[] }>("/v1/projects");
    return response.projects || [];
  },
  impact: (projectId: string) =>
    request<ImpactReport>(`/v1/projects/${encodeURIComponent(projectId)}/impact`),
  relationships: async (params: { project_id?: string; relationship_type?: string; status?: string } = {}) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value) query.set(key, value);
    });
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return request<{ relationships?: Dependency[]; provenance?: PortfolioProvenance }>(`/v1/relationships${suffix}`);
  },
  sourceOfTruth: async (params: { domain?: string; project_id?: string } = {}) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value) query.set(key, value);
    });
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return request<{ source_of_truth?: SourceOfTruth[]; provenance?: PortfolioProvenance }>(`/v1/source-of-truth${suffix}`);
  },
  evidence: async () => {
    const response = await request<{ records?: EvidenceRecord[] }>("/v1/evidence");
    return response.records || [];
  },
  audit: async () => {
    const response = await request<{ events?: AuditEvent[] }>("/v1/audit/events");
    return response.events || [];
  },
  changeRequests: async () => {
    const response = await request<{ change_requests?: ChangeRequest[] }>("/v1/change-requests");
    return response.change_requests || [];
  },
  createChangeRequest: (payload: Record<string, unknown>) =>
    request<{ result?: { change_request?: ChangeRequest } }>("/v1/change-requests", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  submitChangeRequest: (changeId: string) =>
    request<{ result?: { change_request?: ChangeRequest; approval?: Record<string, unknown> } }>(
      `/v1/change-requests/${encodeURIComponent(changeId)}/submit`,
      { method: "POST", body: "{}" },
    ),
  remediationPlans: async () => {
    const response = await request<{ plans?: RemediationPlan[] }>("/v1/remediation-plans");
    return response.plans || [];
  },
  createRemediationPlan: (payload: Record<string, unknown>) =>
    request<{ result?: { plan?: RemediationPlan } }>("/v1/remediation-plans", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  submitRemediationPlan: (planId: string) =>
    request<{ result?: { plan?: RemediationPlan; approval?: Record<string, unknown> } }>(
      `/v1/remediation-plans/${encodeURIComponent(planId)}/submit`,
      { method: "POST", body: "{}" },
    ),
  requestRemediationDryRun: (planId: string) =>
    request<{ result?: { execution?: ExecutionRequest } }>(
      `/v1/remediation-plans/${encodeURIComponent(planId)}/execution`,
      { method: "POST", body: "{}" },
    ),
  executionRequests: async () => {
    const response = await request<{ executions?: ExecutionRequest[] }>("/v1/execution-requests");
    return response.executions || [];
  },
  runnerSessions: async () => {
    const response = await request<{ sessions?: RunnerSession[] }>("/v1/runner-sessions");
    return response.sessions || [];
  },
  createRunnerSession: (executionId: string, payload: Record<string, unknown> = {}) =>
    request<{ result?: { session?: RunnerSession } }>(
      `/v1/execution-requests/${encodeURIComponent(executionId)}/runner-session`,
      { method: "POST", body: JSON.stringify(payload) },
    ),
  patchArtifacts: async () => {
    const response = await request<{ patch_artifacts?: PatchArtifact[] }>("/v1/patch-artifacts");
    return response.patch_artifacts || [];
  },
  validationReports: async () => {
    const response = await request<{ validation_reports?: ValidationReport[] }>("/v1/validation-reports");
    return response.validation_reports || [];
  },
};
