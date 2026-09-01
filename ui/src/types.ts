export type Project = {
  project_id: string;
  name: string;
  kind?: string;
  path?: string;
  root_id?: string;
  owner?: string;
  ownership?: {
    team?: string;
    owners?: string[];
    delegates?: string[];
  };
  git?: {
    branch?: string;
    commit?: string;
    dirty?: boolean;
  };
  runtime?: {
    languages?: string[];
    frameworks?: string[];
  };
  risk?: {
    default?: string;
  };
  policy?: {
    mode?: string;
  };
}

export type Artifact = {
  artifact_id: string;
  project_id?: string;
  artifact_type?: string;
  kind?: string;
  role?: string;
  status?: string;
  workspace_path?: string;
}

export type Dependency = {
  dependency_id?: string;
  relationship_id?: string;
  kind?: string;
  relationship_type?: string;
  relationship_source?: string;
  scope?: string;
  strength?: string;
  status?: string;
  observed_snapshot_id?: string;
  evidence_refs?: string[];
  evidence?: string[] | Record<string, unknown>;
  source?: { project_id?: string; root_id?: string };
  target?: { project_id?: string; root_id?: string };
  [key: string]: unknown;
}

export type SourceOfTruth = {
  source_rule_id?: string;
  domain?: string;
  authority?: {
    project_id?: string;
    artifact?: string;
    [key: string]: unknown;
  };
  status?: string;
  observed_snapshot_id?: string;
  evidence_refs?: string[];
  evidence?: string[] | Record<string, unknown>;
  [key: string]: unknown;
}

export type PortfolioProvenance = {
  snapshot_ids?: string[];
  snapshot_count?: number;
}

export type EvidenceRecord = {
  record_id?: string;
  evidence_id?: string;
  schema?: string;
  kind?: string;
  observed_at?: string;
  created_at?: string;
  [key: string]: unknown;
}

export type AuditEvent = {
  event_id?: string;
  event_type?: string;
  aggregate_id?: string;
  created_at?: string;
  payload?: Record<string, unknown>;
}

export type Adapter = {
  metadata?: {
    adapter_id?: string;
    kind?: string;
    capabilities?: string[];
    read_only?: boolean;
  };
  config?: Record<string, unknown>;
}

export type ImpactReport = {
  project_id: string;
  affected_projects?: Project[];
  relationships?: Dependency[];
  source_of_truth?: SourceOfTruth[];
}

export type Health = {
  status?: string;
  service?: string;
  contract_version?: string;
}

export type Contract = {
  capabilities?: string[];
  contract_version?: string;
  read_only?: boolean;
}

export type ChangeRequest = {
  change_id: string;
  revision: number;
  status: string;
  change_type: "feature" | "fix" | "requirement" | "project_registration" | string;
  title: string;
  description: string;
  scope?: {
    project_ids?: string[];
    [key: string]: unknown;
  };
  requested_by?: string;
  owner?: string;
  acceptance_criteria?: string[];
  source_of_truth?: string[];
  evidence_ids?: string[];
  risk?: string;
  approval_required?: boolean;
  approval_id?: string;
  created_at?: string;
  submitted_at?: string;
  [key: string]: unknown;
}

export type RemediationPlan = {
  plan_id: string;
  revision: number;
  status: string;
  title: string;
  rationale: string;
  finding?: {
    finding_id?: string;
    severity?: string;
    summary?: string;
  };
  scope?: {
    project_ids?: string[];
    artifact_ids?: string[];
    [key: string]: unknown;
  };
  strategy?: {
    kind?: string;
    description?: string;
  };
  validation?: {
    required_checks?: string[];
    [key: string]: unknown;
  };
  acceptance_criteria?: string[];
  evidence_ids?: string[];
  requested_by?: string;
  owner?: string;
  risk?: string;
  approval_required?: boolean;
  approval_id?: string;
  created_at?: string;
  submitted_at?: string;
  [key: string]: unknown;
}

export type ExecutionRequest = {
  execution_id: string;
  plan_id: string;
  revision: number;
  status: string;
  mode: string;
  runner_kind?: string;
  mutation_scope?: {
    source_repositories?: boolean;
    git?: boolean;
    deployment?: boolean;
  };
  validation?: {
    required_checks?: string[];
    [key: string]: unknown;
  };
  evidence_ids?: string[];
  requested_by?: string;
  created_at?: string;
  reported_at?: string;
  result?: {
    summary?: string;
    [key: string]: unknown;
  };
  [key: string]: unknown;
}

export type RunnerSession = {
  session_id: string;
  revision: number;
  status: string;
  execution_id: string;
  plan_id: string;
  runner_kind?: string;
  operation_profile?: string;
  project_ids?: string[];
  patch_artifact_ids?: string[];
  validation_report_ids?: string[];
  evidence_ids?: string[];
  mutation_scope?: {
    source_repositories?: boolean;
    git?: boolean;
    deployment?: boolean;
  };
  requested_by?: string;
  created_at?: string;
  reported_at?: string;
  result?: {
    summary?: string;
    [key: string]: unknown;
  };
  [key: string]: unknown;
}

export type PatchArtifact = {
  patch_id: string;
  revision: number;
  status: string;
  session_id: string;
  execution_id: string;
  plan_id: string;
  format?: string;
  content_digest?: string;
  artifact_ref?: string;
  files?: Array<{
    path?: string;
    old_path?: string;
    change?: string;
  }>;
  file_count?: number;
  change_summary?: string;
  evidence_ids?: string[];
  created_at?: string;
  [key: string]: unknown;
}

export type ValidationReport = {
  report_id: string;
  revision: number;
  status: string;
  session_id: string;
  execution_id: string;
  plan_id: string;
  summary?: string;
  checks?: Array<{
    check_id?: string;
    status?: string;
    summary?: string;
    evidence_ids?: string[];
  }>;
  missing_check_ids?: string[];
  evidence_ids?: string[];
  created_at?: string;
  [key: string]: unknown;
}
