import { useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "./lib/api";
import { deriveInsights, evidenceInsightStatus, type InsightStatus, type PortfolioInsights } from "./lib/insights";
import type {
  Adapter,
  AuditEvent,
  ChangeRequest,
  Contract,
  Dependency,
  EvidenceRecord,
  Health,
  ImpactReport,
  PortfolioProvenance,
  Project,
  SourceOfTruth,
  ExecutionRequest,
  RemediationPlan,
  RunnerSession,
  PatchArtifact,
  ValidationReport,
} from "./types";

type View = "overview" | "projects" | "proposals" | "remediation" | "runner" | "governance" | "security" | "evals" | "evidence" | "audit";
type Tone = "neutral" | "blue" | "green" | "amber" | "violet" | "red";
type IconName = "grid" | "layers" | "file" | "activity" | "search" | "refresh" | "arrow" | "shield" | "external" | "gavel" | "lock" | "check";

const navigation: { id: View; label: string; icon: IconName }[] = [
  { id: "overview", label: "Overview", icon: "grid" },
  { id: "projects", label: "Projects", icon: "layers" },
  { id: "proposals", label: "Proposals", icon: "gavel" },
  { id: "remediation", label: "Remediation", icon: "activity" },
  { id: "runner", label: "Runner evidence", icon: "external" },
  { id: "governance", label: "Governance", icon: "gavel" },
  { id: "security", label: "Security", icon: "lock" },
  { id: "evals", label: "Evals", icon: "check" },
  { id: "evidence", label: "Evidence", icon: "file" },
  { id: "audit", label: "Audit trail", icon: "activity" },
];

function Icon({ name, size = 18, className = "" }: { name: IconName; size?: number; className?: string }) {
  const paths: Record<IconName, ReactNode> = {
    grid: <><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /></>,
    layers: <><path d="m12 3 8.5 4.5L12 12 3.5 7.5 12 3Z" /><path d="m3.5 12 8.5 4.5 8.5-4.5" /><path d="m3.5 16.5 8.5 4.5 8.5-4.5" /></>,
    file: <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" /><path d="M14 2v6h6M8 13h8M8 17h5" /></>,
    activity: <><path d="M3 12h4l2-7 4 14 2-7h6" /></>,
    search: <><circle cx="11" cy="11" r="7" /><path d="m20 20-4-4" /></>,
    refresh: <><path d="M20 11a8.1 8.1 0 0 0-14.8-4L3 10" /><path d="M3 4v6h6M4 13a8.1 8.1 0 0 0 14.8 4L21 14" /><path d="M21 20v-6h-6" /></>,
    arrow: <><path d="M5 12h14M13 6l6 6-6 6" /></>,
    shield: <><path d="M12 22s8-3.8 8-10V5l-8-3-8 3v7c0 6.2 8 10 8 10Z" /><path d="m9 12 2 2 4-4" /></>,
    external: <><path d="M14 3h7v7M10 14 21 3" /><path d="M21 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5" /></>,
    gavel: <><path d="m14.5 4.5 5 5" /><path d="m12 7 5 5" /><path d="m3 21 8.5-8.5" /><path d="m7 4 13 13" /><path d="m3 7 4-4 4 4-4 4-4-4Z" /><path d="m13 17 4-4 4 4-4 4-4-4Z" /></>,
    lock: <><rect x="5" y="10" width="14" height="11" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3M12 14v3" /></>,
    check: <><path d="M20 6 9 17l-5-5" /></>,
  };

  return (
    <svg aria-hidden="true" className={className} fill="none" height={size} stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" viewBox="0 0 24 24" width={size}>
      {paths[name]}
    </svg>
  );
}

function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: Tone }) {
  const tones: Record<Tone, string> = {
    neutral: "bg-slate-100 text-slate-600 ring-slate-200",
    blue: "bg-blue-50 text-blue-700 ring-blue-100",
    green: "bg-emerald-50 text-emerald-700 ring-emerald-100",
    amber: "bg-amber-50 text-amber-700 ring-amber-100",
    violet: "bg-violet-50 text-violet-700 ring-violet-100",
    red: "bg-rose-50 text-rose-700 ring-rose-100",
  };
  return <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-[11px] font-semibold tracking-wide ring-1 ring-inset ${tones[tone]}`}>{children}</span>;
}

function MetricCard({ label, value, detail, icon, tone, stale = false }: { label: string; value: string | number; detail: string; icon: IconName; tone: Tone; stale?: boolean }) {
  const accent: Record<Tone, string> = { neutral: "text-slate-500", blue: "text-blue-600", green: "text-emerald-600", amber: "text-amber-600", violet: "text-violet-600", red: "text-rose-600" };
  return (
    <div className="panel-shadow rounded-2xl border border-slate-200/80 bg-white p-5">
      <div className="flex items-start justify-between">
        <span className={`flex h-10 w-10 items-center justify-center rounded-xl bg-slate-50 ${accent[tone]}`}><Icon name={icon} /></span>
        <span className={`text-[10px] font-bold uppercase tracking-[0.18em] ${stale ? "text-amber-600" : "text-slate-400"}`}>{stale ? "Stale" : "Observed"}</span>
      </div>
      <p className="mt-5 text-3xl font-semibold tracking-tight text-slate-900">{value}</p>
      <p className="mt-1 text-sm font-medium text-slate-600">{label}</p>
      <p className="mt-2 text-xs text-slate-400">{detail}</p>
    </div>
  );
}

function SectionTitle({ eyebrow, title, description, action }: { eyebrow: string; title: string; description: string; action?: ReactNode }) {
  return (
    <div className="mb-7 flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
      <div>
        <p className="text-[11px] font-bold uppercase tracking-[0.22em] text-indigo-600">{eyebrow}</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-[-0.04em] text-slate-950 sm:text-4xl">{title}</h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">{description}</p>
      </div>
      {action}
    </div>
  );
}

function EmptyState({ title, detail }: { title: string; detail: string }) {
  return <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50/60 px-6 py-12 text-center"><p className="font-semibold text-slate-700">{title}</p><p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-500">{detail}</p></div>;
}

function formatDate(value?: string) {
  if (!value) return "No timestamp";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(date);
}

function shortId(value?: string) {
  if (!value) return "UNKNOWN";
  const clean = value.replace(/^sha256:/, "");
  return clean.length > 18 ? `${clean.slice(0, 10)}…${clean.slice(-6)}` : clean;
}

function projectKind(project: Project) {
  return (project.kind || "unknown").replaceAll("_", " ");
}

function projectTone(project: Project): Tone {
  if (typeof project.git?.dirty !== "boolean") return "amber";
  if (project.git?.dirty === true) return "amber";
  if (project.policy?.mode === "enforced") return "violet";
  if (project.git?.dirty === false) return "green";
  return "amber";
}

function projectStatus(project: Project) {
  if (typeof project.git?.dirty !== "boolean") return "Git state unknown";
  if (project.git?.dirty === true) return "Changes detected";
  if (project.policy?.mode === "enforced") return "Policy enforced";
  if (project.git?.dirty === false) return "Observed clean state";
  return "Git state unknown";
}

function insightTone(status: InsightStatus): Tone {
  if (status === "pass" || status === "allow" || status === "declared") return "green";
  if (status === "fail" || status === "deny") return "red";
  if (status === "conflict") return "red";
  if (status === "pending") return "amber";
  if (status === "not_configured") return "violet";
  return "amber";
}

function insightLabel(status: InsightStatus) {
  if (status === "not_configured") return "NOT CONFIGURED";
  if (status === "declared") return "DECLARED";
  return status.toUpperCase();
}

function StatusBadge({ status }: { status: InsightStatus }) {
  return <Badge tone={insightTone(status)}>{insightLabel(status)}</Badge>;
}

function SignalCard({ signal }: { signal: { label: string; status: InsightStatus; detail: string } }) {
  return <div className="rounded-xl border border-slate-100 bg-slate-50/70 p-4"><div className="flex items-center justify-between gap-3"><p className="text-sm font-semibold text-slate-700">{signal.label}</p><StatusBadge status={signal.status} /></div><p className="mt-3 text-xs leading-5 text-slate-500">{signal.detail}</p></div>;
}

function SignalList({ signals }: { signals: { label: string; status: InsightStatus; detail: string }[] }) {
  return <div className="space-y-3">{signals.map((signal) => <SignalCard key={signal.label} signal={signal} />)}</div>;
}

function projectPath(project: Project) {
  return project.path && project.path !== "." ? project.path : "workspace root";
}

const proposalActor = import.meta.env.VITE_AINE_ACTOR || "";

function App() {
  const [view, setView] = useState<View>("overview");
  const [projects, setProjects] = useState<Project[]>([]);
  const [evidence, setEvidence] = useState<EvidenceRecord[]>([]);
  const [audit, setAudit] = useState<AuditEvent[]>([]);
  const [contract, setContract] = useState<Contract | null>(null);
  const [adapters, setAdapters] = useState<Adapter[]>([]);
  const [changeRequests, setChangeRequests] = useState<ChangeRequest[]>([]);
  const [remediationPlans, setRemediationPlans] = useState<RemediationPlan[]>([]);
  const [executionRequests, setExecutionRequests] = useState<ExecutionRequest[]>([]);
  const [runnerSessions, setRunnerSessions] = useState<RunnerSession[]>([]);
  const [patchArtifacts, setPatchArtifacts] = useState<PatchArtifact[]>([]);
  const [validationReports, setValidationReports] = useState<ValidationReport[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [selectedProjectId, setSelectedProjectId] = useState<string>();
  const [impact, setImpact] = useState<ImpactReport | null>(null);
  const [impactError, setImpactError] = useState(false);
  const [relationships, setRelationships] = useState<Dependency[]>([]);
  const [sourceOfTruth, setSourceOfTruth] = useState<SourceOfTruth[]>([]);
  const [portfolioProvenance, setPortfolioProvenance] = useState<PortfolioProvenance | null>(null);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();
  const [dataStale, setDataStale] = useState(false);
  const [refreshToken, setRefreshToken] = useState(0);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(undefined);
    if (refreshToken > 0) setDataStale(true);
    Promise.all([api.health(), api.contract(), api.adapters(), api.projects(), api.relationships(), api.sourceOfTruth(), api.evidence(), api.audit(), api.changeRequests(), api.remediationPlans(), api.executionRequests(), api.runnerSessions(), api.patchArtifacts(), api.validationReports()])
      .then(([nextHealth, nextContract, nextAdapters, nextProjects, nextRelationships, nextSourceOfTruth, nextEvidence, nextAudit, nextChangeRequests, nextRemediationPlans, nextExecutionRequests, nextRunnerSessions, nextPatchArtifacts, nextValidationReports]) => {
        if (!active) return;
        setHealth(nextHealth);
        setContract(nextContract);
        setAdapters(nextAdapters);
        setProjects(nextProjects);
        setRelationships(nextRelationships.relationships || []);
        setSourceOfTruth(nextSourceOfTruth.source_of_truth || []);
        setPortfolioProvenance(nextRelationships.provenance || nextSourceOfTruth.provenance || null);
        setEvidence(nextEvidence);
        setAudit(nextAudit);
        setChangeRequests(nextChangeRequests);
        setRemediationPlans(nextRemediationPlans);
        setExecutionRequests(nextExecutionRequests);
        setRunnerSessions(nextRunnerSessions);
        setPatchArtifacts(nextPatchArtifacts);
        setValidationReports(nextValidationReports);
        setSelectedProjectId((current) => current || nextProjects[0]?.project_id);
        setDataStale(false);
      })
      .catch((reason: unknown) => {
        if (active) {
          setError(reason instanceof Error ? reason.message : "Control Plane is unavailable");
          setDataStale(refreshToken > 0);
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [refreshToken]);

  useEffect(() => {
    setImpact(null);
    setImpactError(false);
    if (!selectedProjectId) {
      return;
    }
    let active = true;
    api.impact(selectedProjectId).then((nextImpact) => {
      if (active) {
        setImpact(nextImpact);
        setImpactError(false);
      }
    }).catch(() => {
      if (active) {
        setImpact(null);
        setImpactError(true);
      }
    });
    return () => { active = false; };
  }, [selectedProjectId, refreshToken]);

  const selectedProject = projects.find((project) => project.project_id === selectedProjectId);
  const filteredProjects = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return projects;
    return projects.filter((project) => [project.name, project.project_id, project.path, project.owner, project.ownership?.team].some((value) => value?.toLowerCase().includes(query)));
  }, [projects, search]);
  const dirtyCount = projects.filter((project) => project.git?.dirty).length;
  const unknownGitCount = projects.filter((project) => typeof project.git?.dirty !== "boolean").length;
  const enforcedCount = projects.filter((project) => project.policy?.mode === "enforced").length;
  const latestAudit = [...audit].sort((left, right) => String(right.created_at || "").localeCompare(String(left.created_at || ""))).slice(0, 5);
  const insights = useMemo(() => deriveInsights(evidence, audit, contract, adapters), [audit, adapters, contract, evidence]);

  const openProject = (projectId: string) => {
    setSelectedProjectId(projectId);
    setView("projects");
  };

  return (
    <div className="min-h-screen bg-[#f4f6fa] text-slate-900">
      <aside className="fixed inset-y-0 left-0 z-20 hidden w-[250px] flex-col bg-[#111a2c] text-slate-300 lg:flex">
        <div className="flex h-24 items-center gap-3 border-b border-white/10 px-7">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-500 text-lg font-bold text-white shadow-lg shadow-indigo-900/30">A</div>
          <div><p className="text-[15px] font-bold tracking-tight text-white">AINE</p><p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">Control Plane</p></div>
        </div>
        <div className="px-4 py-7">
          <p className="px-3 text-[10px] font-bold uppercase tracking-[0.2em] text-slate-600">Portfolio</p>
          <nav className="mt-3 space-y-1">
            {navigation.map((item) => <button className={`flex w-full items-center gap-3 rounded-xl px-3 py-3 text-left text-sm font-medium transition ${view === item.id ? "bg-white/10 text-white shadow-inner" : "text-slate-400 hover:bg-white/5 hover:text-slate-200"}`} key={item.id} onClick={() => setView(item.id)}><Icon name={item.icon} size={17} /><span>{item.label}</span>{item.id === "projects" && <span className="ml-auto rounded-full bg-white/10 px-2 py-0.5 text-[10px] text-slate-400">{projects.length}</span>}</button>)}
          </nav>
        </div>
        <div className="mt-auto p-4">
          <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-4">
            <div className="flex items-center gap-2"><span className={`h-2 w-2 rounded-full ${health?.status === "ok" ? "bg-emerald-400" : "bg-amber-400"}`} /><span className="text-xs font-semibold text-slate-300">{health?.status === "ok" ? "Control Plane online" : "Awaiting service"}</span></div>
            <p className="mt-3 text-[11px] leading-5 text-slate-500">Source repositories remain read-only. Proposal records stay inside the private Control Plane; no deployment execution.</p>
          </div>
          <p className="px-1 pt-4 text-[10px] font-medium text-slate-600">Private workspace · v1.6.0</p>
        </div>
      </aside>

      <main className="lg:pl-[250px]">
        <header className="sticky top-0 z-10 flex h-20 items-center justify-between border-b border-slate-200/80 bg-[#f4f6fa]/90 px-5 backdrop-blur-xl sm:px-8 lg:px-12">
          <div className="flex items-center gap-3 lg:hidden"><div className="flex h-9 w-9 items-center justify-center rounded-xl bg-[#111a2c] font-bold text-white">A</div><span className="font-bold text-slate-900">AINE</span></div>
          <div className="relative hidden w-full max-w-md sm:block"><Icon className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" name="search" size={16} /><input className="h-10 w-full rounded-xl border border-slate-200 bg-white/70 pl-10 pr-4 text-sm text-slate-700 outline-none transition placeholder:text-slate-400 focus:border-indigo-300 focus:ring-4 focus:ring-indigo-100" onChange={(event) => setSearch(event.target.value)} placeholder="Search projects, evidence, boundaries…" value={search} /></div>
          <div className="flex items-center gap-3 sm:ml-auto"><Badge tone="violet">PRIVATE PORTFOLIO</Badge><Badge tone={proposalActor ? "blue" : "amber"}>{proposalActor ? "PROPOSAL MODE" : "ACTOR REQUIRED"}</Badge><button aria-label="Refresh portfolio" className="flex h-10 w-10 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-500 transition hover:border-indigo-200 hover:text-indigo-600" onClick={() => setRefreshToken((value) => value + 1)}><Icon name="refresh" size={16} /></button><div className="hidden h-10 w-10 items-center justify-center rounded-full bg-indigo-100 text-sm font-bold text-indigo-700 sm:flex">W</div></div>
        </header>

        <nav aria-label="Mobile portfolio navigation" className="thin-scrollbar flex gap-2 overflow-x-auto border-b border-slate-200/80 bg-white px-5 py-3 lg:hidden">
          {navigation.map((item) => <button className={`flex shrink-0 items-center gap-2 rounded-lg px-3 py-2 text-xs font-semibold transition ${view === item.id ? "bg-indigo-50 text-indigo-700" : "text-slate-500 hover:bg-slate-50"}`} key={item.id} onClick={() => setView(item.id)}><Icon name={item.icon} size={14} />{item.label}{item.id === "projects" && <span className="rounded-full bg-slate-100 px-1.5 py-0.5 text-[10px]">{projects.length}</span>}</button>)}
        </nav>

        <div className="px-5 py-8 sm:px-8 lg:px-12 lg:py-11">
          {error && <div className="mb-6 flex items-start gap-3 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800"><Icon name="activity" size={17} /><div><p className="font-semibold">Control Plane unavailable</p><p className="mt-1 text-amber-700">{error}. Start the loopback service, then refresh this view.</p></div></div>}
          {view === "overview" && <OverviewView audit={latestAudit} dirtyCount={dirtyCount} enforcedCount={enforcedCount} evidence={evidence} insights={insights} loading={loading} onOpenProject={openProject} projects={projects} stale={dataStale} unknownGitCount={unknownGitCount} />}
          {view === "projects" && <ProjectsView impact={impact} impactError={impactError} onSelectProject={setSelectedProjectId} portfolioProvenance={portfolioProvenance} projects={filteredProjects} relationships={relationships} search={search} selectedProject={selectedProject} setSearch={setSearch} sourceOfTruth={sourceOfTruth} />}
          {view === "proposals" && <ProposalsView actor={proposalActor} changeRequests={changeRequests} loading={loading} onRefresh={() => setRefreshToken((value) => value + 1)} projects={projects} />}
          {view === "remediation" && <RemediationView actor={proposalActor} executionRequests={executionRequests} loading={loading} onRefresh={() => setRefreshToken((value) => value + 1)} plans={remediationPlans} projects={projects} />}
          {view === "runner" && <RunnerView actor={proposalActor} executionRequests={executionRequests} loading={loading} onRefresh={() => setRefreshToken((value) => value + 1)} patchArtifacts={patchArtifacts} reports={validationReports} sessions={runnerSessions} />}
          {view === "governance" && <GovernanceView insights={insights} loading={loading} />}
          {view === "security" && <SecurityView adapters={adapters} contract={contract} insights={insights} loading={loading} />}
          {view === "evals" && <EvalsView insights={insights} loading={loading} stale={dataStale} />}
          {view === "evidence" && <EvidenceView evidence={evidence} loading={loading} search={search} setSearch={setSearch} />}
          {view === "audit" && <AuditView audit={audit} loading={loading} />}
        </div>
      </main>
    </div>
  );
}

function OverviewView({ projects, evidence, audit, dirtyCount, enforcedCount, insights, loading, onOpenProject, stale, unknownGitCount }: { projects: Project[]; evidence: EvidenceRecord[]; audit: AuditEvent[]; dirtyCount: number; enforcedCount: number; insights: PortfolioInsights; loading: boolean; onOpenProject: (projectId: string) => void; stale: boolean; unknownGitCount: number }) {
  const languages = [...new Set(projects.flatMap((project) => project.runtime?.languages || []))];
  return <>
    <SectionTitle action={<Badge tone="green"><span className="mr-1.5 h-1.5 w-1.5 rounded-full bg-emerald-500" /> READ-ONLY MODE</Badge>} description="An evidence-backed view of the systems, artifacts, and governance boundaries observed by the Control Plane." eyebrow="Portfolio intelligence" title="Good morning, William" />
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"><MetricCard detail={dirtyCount ? `${dirtyCount} with uncommitted changes` : unknownGitCount ? `${unknownGitCount} without observed Git state` : projects.length ? "No dirty state observed" : "UNKNOWN"} icon="layers" label="Registered projects" tone="blue" stale={stale} value={loading ? "—" : projects.length} /><MetricCard detail={`${languages.length || 0} language/runtime families observed`} icon="arrow" label="Runtime ecosystems" tone="violet" stale={stale} value={loading ? "—" : languages.length} /><MetricCard detail="Portable records in local store" icon="file" label="Evidence records" tone="green" stale={stale} value={loading ? "—" : evidence.length} /><MetricCard detail={enforcedCount ? `${enforcedCount} policy boundaries enforced` : "Advisory policy by default"} icon="activity" label="Audit events" tone="amber" stale={stale} value={loading ? "—" : audit.length} /></div>
    <div className="mt-6 grid gap-4 md:grid-cols-3"><SignalCard signal={insights.governanceSignals[0]} /><SignalCard signal={insights.securitySignals[3]} /><SignalCard signal={{ label: "Evaluation coverage", status: insights.evaluationRecords.length ? "pass" : "unknown", detail: insights.evaluationRecords.length ? `${insights.evaluationRecords.length} evaluation records observed` : "No policy or evaluation evidence observed" }} /></div>
    <div className="mt-6 grid gap-6 xl:grid-cols-[1.45fr_1fr]">
      <section className="panel-shadow rounded-2xl border border-slate-200/80 bg-white p-6"><div className="flex items-start justify-between"><div><p className="text-[11px] font-bold uppercase tracking-[0.18em] text-slate-400">Boundary map</p><h2 className="mt-2 text-lg font-semibold tracking-tight text-slate-900">Portfolio health</h2></div><Badge tone="blue">{projects.length} boundaries</Badge></div><div className="mt-6 space-y-3">{projects.length === 0 ? <EmptyState detail="Start the Control Plane service and ingest a portable Registry snapshot to populate this view." title="No projects observed yet" /> : projects.slice(0, 5).map((project) => <button className="group flex w-full items-center gap-4 rounded-xl border border-slate-100 p-3 text-left transition hover:border-indigo-200 hover:bg-indigo-50/40" key={project.project_id} onClick={() => onOpenProject(project.project_id)}><div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-slate-100 text-sm font-bold text-slate-600">{project.name.slice(0, 1).toUpperCase()}</div><div className="min-w-0 flex-1"><div className="flex items-center gap-2"><p className="truncate text-sm font-semibold text-slate-800">{project.name}</p><Badge tone={projectTone(project)}>{projectStatus(project)}</Badge></div><p className="mt-1 truncate text-xs text-slate-400">{projectPath(project)}</p></div><Icon className="text-slate-300 transition group-hover:translate-x-1 group-hover:text-indigo-500" name="arrow" size={17} /></button>)}</div></section>
      <section className="soft-grid overflow-hidden rounded-2xl border border-slate-200/80 bg-[#111a2c] p-6 text-white"><div className="flex items-start justify-between"><div><p className="text-[11px] font-bold uppercase tracking-[0.18em] text-indigo-300">System signal</p><h2 className="mt-2 text-lg font-semibold tracking-tight">Governance posture</h2></div><Icon className="text-indigo-300" name="shield" size={22} /></div><div className="mt-10"><div className="flex items-end justify-between"><span className="text-sm text-slate-400">Observed boundaries</span><span className="text-2xl font-semibold">{projects.length}</span></div><div className="mt-3 h-2 overflow-hidden rounded-full bg-white/10"><div className="h-full rounded-full bg-indigo-400" style={{ width: `${Math.min(100, projects.length ? 100 : 4)}%` }} /></div></div><div className="mt-7 grid grid-cols-2 gap-3"><div className="rounded-xl border border-white/10 bg-white/[0.05] p-4"><p className="text-2xl font-semibold">{unknownGitCount ? "UNKNOWN" : dirtyCount}</p><p className="mt-1 text-xs text-slate-400">{unknownGitCount ? "Git state" : "Dirty checkouts"}</p>{unknownGitCount > 0 && <p className="mt-1 text-[11px] text-amber-300">{unknownGitCount} boundary{unknownGitCount === 1 ? "" : "ies"} not observed</p>}</div><div className="rounded-xl border border-white/10 bg-white/[0.05] p-4"><p className="text-2xl font-semibold">{enforcedCount}</p><p className="mt-1 text-xs text-slate-400">Enforced policies</p></div></div><p className="mt-8 text-xs leading-5 text-slate-400">Uncertainty stays visible. AINE reports evidence and relationships; it does not infer authority or execute changes.</p></section>
    </div>
    <section className="panel-shadow mt-6 rounded-2xl border border-slate-200/80 bg-white p-6"><div className="flex items-center justify-between"><div><p className="text-[11px] font-bold uppercase tracking-[0.18em] text-slate-400">Recent activity</p><h2 className="mt-2 text-lg font-semibold tracking-tight text-slate-900">Audit trail</h2></div><button className="text-xs font-semibold text-indigo-600 hover:text-indigo-800" onClick={() => onOpenProject(projects[0]?.project_id || "")}>Explore portfolio <Icon className="ml-1 inline" name="arrow" size={13} /></button></div><div className="mt-5 grid gap-3 md:grid-cols-3">{audit.length === 0 ? <EmptyState detail="Ingested snapshots and policy decisions will appear here." title="No events yet" /> : audit.slice(-3).reverse().map((event) => <div className="rounded-xl bg-slate-50 p-4" key={event.event_id || `${event.event_type}-${event.created_at}`}><div className="flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-indigo-400" /><p className="truncate text-sm font-semibold text-slate-700">{event.event_type || "event"}</p></div><p className="mt-3 text-xs text-slate-400">{formatDate(event.created_at)}</p><p className="mt-1 truncate text-xs text-slate-500">{event.aggregate_id || "portfolio"}</p></div>)}</div></section>
  </>;
}

function ProjectsView({ projects, selectedProject, impact, impactError, relationships, sourceOfTruth, portfolioProvenance, search, setSearch, onSelectProject }: { projects: Project[]; selectedProject?: Project; impact: ImpactReport | null; impactError: boolean; relationships: Dependency[]; sourceOfTruth: SourceOfTruth[]; portfolioProvenance: PortfolioProvenance | null; search: string; setSearch: (value: string) => void; onSelectProject: (projectId: string) => void }) {
  const [rootFilter, setRootFilter] = useState("all");
  const roots = [...new Set(projects.map((project) => project.root_id).filter((root): root is string => Boolean(root)))].sort();
  const visibleProjects = rootFilter === "all" ? projects : projects.filter((project) => project.root_id === rootFilter);
  const scopedRelationships = selectedProject
    ? relationships.filter((edge) => edge.source?.project_id === selectedProject.project_id || edge.target?.project_id === selectedProject.project_id)
    : relationships;
  const scopedSourceOfTruth = selectedProject
    ? sourceOfTruth.filter((rule) => rule.authority?.project_id === selectedProject.project_id)
    : sourceOfTruth;

  useEffect(() => {
    if (visibleProjects.length > 0 && !visibleProjects.some((project) => project.project_id === selectedProject?.project_id)) {
      onSelectProject(visibleProjects[0].project_id);
    }
  }, [onSelectProject, rootFilter, selectedProject?.project_id, visibleProjects]);

  return <>
    <SectionTitle action={<div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row"><div className="relative w-full sm:w-72"><Icon className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" name="search" size={16} /><input className="h-10 w-full rounded-xl border border-slate-200 bg-white pl-10 pr-3 text-sm outline-none focus:border-indigo-300 focus:ring-4 focus:ring-indigo-100" onChange={(event) => setSearch(event.target.value)} placeholder="Filter projects" value={search} /></div><select aria-label="Filter by workspace root" className="h-10 rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-700 outline-none focus:border-indigo-300 focus:ring-4 focus:ring-indigo-100" onChange={(event) => setRootFilter(event.target.value)} value={rootFilter}><option value="all">All workspace roots</option>{roots.map((root) => <option key={root} value={root}>{root}</option>)}</select></div>} description="Inspect project ownership, runtime boundaries, local state, and the evidence-backed relationships that shape impact." eyebrow="Portfolio map" title="Projects" />
    <div className="grid gap-6 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.35fr)]">
      <section className="panel-shadow rounded-2xl border border-slate-200/80 bg-white p-3"><div className="flex items-center justify-between px-3 py-3"><div><p className="text-xs font-bold uppercase tracking-[0.16em] text-slate-400">Registered boundaries</p><p className="mt-1 text-xs text-slate-400">{rootFilter === "all" ? "All roots" : `Root: ${rootFilter}`}</p></div><Badge tone="blue">{visibleProjects.length}</Badge></div><div className="thin-scrollbar max-h-[620px] space-y-1 overflow-auto">{visibleProjects.length === 0 ? <div className="p-3"><EmptyState detail="No project matches the current filter." title="No projects found" /></div> : visibleProjects.map((project) => <button className={`w-full rounded-xl p-4 text-left transition ${selectedProject?.project_id === project.project_id ? "bg-indigo-50 ring-1 ring-indigo-200" : "hover:bg-slate-50"}`} key={project.project_id} onClick={() => onSelectProject(project.project_id)}><div className="flex items-center gap-3"><div className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-100 text-xs font-bold text-slate-600">{project.name.slice(0, 1).toUpperCase()}</div><div className="min-w-0 flex-1"><p className="truncate text-sm font-semibold text-slate-800">{project.name}</p><p className="mt-1 truncate text-xs text-slate-400">{projectLocation(project)}</p></div><span className={`h-2 w-2 rounded-full ${project.git?.dirty === true ? "bg-amber-400" : project.git?.dirty === false ? "bg-emerald-400" : "bg-slate-300"}`} /></div></button>)}</div></section>
      <section className="panel-shadow rounded-2xl border border-slate-200/80 bg-white p-6">{selectedProject ? <><div className="flex flex-col justify-between gap-4 border-b border-slate-100 pb-6 sm:flex-row sm:items-start"><div className="flex items-start gap-4"><div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-indigo-100 text-xl font-bold text-indigo-700">{selectedProject.name.slice(0, 1).toUpperCase()}</div><div><div className="flex flex-wrap items-center gap-2"><h2 className="text-xl font-semibold tracking-tight text-slate-900">{selectedProject.name}</h2><Badge tone={projectTone(selectedProject)}>{projectStatus(selectedProject)}</Badge></div><p className="mt-2 text-sm text-slate-500">{selectedProject.project_id}</p><p className="mt-1 text-xs text-slate-400">{projectLocation(selectedProject)}</p></div></div><Badge tone="neutral">{projectKind(selectedProject)}</Badge></div><div className="grid gap-4 border-b border-slate-100 py-6 sm:grid-cols-3"><Info label="Owner" value={selectedProject.owner || "UNKNOWN"} /><Info label="Team" value={selectedProject.ownership?.team || "UNKNOWN"} /><Info label="Branch" value={selectedProject.git?.branch || "UNKNOWN"} /></div><div className="py-6"><p className="text-[11px] font-bold uppercase tracking-[0.18em] text-slate-400">Runtime profile</p><div className="mt-3 flex flex-wrap gap-2">{[...(selectedProject.runtime?.languages || []), ...(selectedProject.runtime?.frameworks || [])].length ? [...(selectedProject.runtime?.languages || []), ...(selectedProject.runtime?.frameworks || [])].map((item) => <Badge key={item} tone="blue">{item}</Badge>) : <span className="text-sm text-slate-400">No runtime metadata observed</span>}</div></div><div className="border-t border-slate-100 pt-6"><div className="flex items-center justify-between"><div><p className="text-[11px] font-bold uppercase tracking-[0.18em] text-slate-400">Impact surface</p><p className="mt-1 text-sm text-slate-500">Incoming and outgoing registered relationships.</p></div><Badge tone="violet">{impact?.project_id === selectedProject.project_id ? impact.relationships?.length || 0 : 0} edges</Badge></div><div className="mt-4 space-y-2">{impactError ? <p className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-5 text-sm text-amber-800">Impact is unavailable for this boundary. The registry relationship view below remains the authoritative stored projection.</p> : impact?.project_id === selectedProject.project_id && impact.relationships?.length ? impact.relationships.slice(0, 6).map((edge, index) => <RelationshipRow edge={edge} key={edge.dependency_id || edge.relationship_id || index} projectId={selectedProject.project_id} />) : <p className="rounded-xl bg-slate-50 px-4 py-5 text-sm text-slate-500">No related edges are currently stored for this boundary.</p>}</div></div></> : <EmptyState detail="Ingest a Registry snapshot to inspect project boundaries and impact." title="Select a project" />}</section>
    </div>
    <div className="mt-6 grid gap-6 xl:grid-cols-2">
      <RelationshipRegistry relationships={scopedRelationships} selectedProject={selectedProject} />
      <SourceOfTruthRegistry rules={scopedSourceOfTruth} selectedProject={selectedProject} />
    </div>
    <PortfolioProvenance provenance={portfolioProvenance} />
  </>;
}

function projectLocation(project: Project) {
  return `${project.root_id || "UNKNOWN root"} · ${projectPath(project)}`;
}

function registryTone(status?: string): Tone {
  if (["active", "declared", "pass"].includes(status || "")) return "green";
  if (["conflict", "failed", "fail"].includes(status || "")) return "red";
  if (["planned", "pending", "unknown"].includes(status || "")) return "amber";
  return "neutral";
}

function isCrossRoot(edge: Dependency) {
  return edge.scope === "cross_root" || (Boolean(edge.source?.root_id) && Boolean(edge.target?.root_id) && edge.source?.root_id !== edge.target?.root_id);
}

function evidenceLabels(refs?: string[] | Record<string, unknown>) {
  if (Array.isArray(refs)) return refs.filter((item): item is string => typeof item === "string" && item.trim().length > 0);
  if (refs && typeof refs === "object") return Object.keys(refs).map((key) => `${key}: observed`);
  return [];
}

function evidenceWithFallback(primary?: string[] | Record<string, unknown>, fallback?: string[] | Record<string, unknown>) {
  const primaryLabels = evidenceLabels(primary);
  return primaryLabels.length > 0 ? primaryLabels : evidenceLabels(fallback);
}

function EvidenceRefs({ refs, fallback }: { refs?: string[] | Record<string, unknown>; fallback?: string[] | Record<string, unknown> }) {
  const evidence = evidenceWithFallback(refs, fallback);
  return evidence.length > 0
    ? <div className="mt-3 flex flex-wrap gap-2">{evidence.map((item) => <span className="rounded-md bg-slate-50 px-2 py-1 font-mono text-[11px] text-slate-500" key={item}>{item}</span>)}</div>
    : <p className="mt-3 text-xs text-amber-700">No evidence reference observed.</p>;
}

function RelationshipRegistry({ relationships, selectedProject }: { relationships: Dependency[]; selectedProject?: Project }) {
  const crossRootCount = relationships.filter(isCrossRoot).length;
  return <section className="panel-shadow rounded-2xl border border-slate-200/80 bg-white p-6"><div className="flex items-start justify-between gap-4"><div><p className="text-[11px] font-bold uppercase tracking-[0.18em] text-slate-400">Relationship registry</p><h2 className="mt-2 text-lg font-semibold tracking-tight text-slate-900">{selectedProject ? `${selectedProject.name} boundary` : "Portfolio relationships"}</h2><p className="mt-1 text-sm text-slate-500">Declared edges observed in portable Registry snapshots.</p></div><div className="flex flex-wrap justify-end gap-2"><Badge tone="violet">{relationships.length} edges</Badge>{crossRootCount > 0 && <Badge tone="amber">{crossRootCount} cross-root</Badge>}</div></div><div className="mt-5 space-y-3">{relationships.length === 0 ? <EmptyState detail={selectedProject ? "No relationship record currently targets or originates from this project." : "Ingest a Registry snapshot with explicit relationships to populate this view."} title="No relationships observed" /> : relationships.map((edge, index) => <div className="rounded-xl border border-slate-100 p-4" key={edge.dependency_id || edge.relationship_id || `${edge.source?.project_id}-${edge.target?.project_id}-${index}`}><div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start"><div className="min-w-0"><p className="truncate text-sm font-semibold text-slate-800">{edge.source?.project_id || "UNKNOWN"} <span className="px-1 text-indigo-500">→</span> {edge.target?.project_id || "UNKNOWN"}</p><p className="mt-1 text-xs text-slate-500">{edge.relationship_type || edge.kind || "UNKNOWN relationship"} · {edge.scope || "UNKNOWN scope"}{edge.strength ? ` · ${edge.strength}` : ""}</p><p className="mt-2 font-mono text-[11px] text-slate-400">snapshot: {shortId(edge.observed_snapshot_id)}</p></div><div className="flex shrink-0 flex-wrap gap-2"><Badge tone={registryTone(edge.status)}>{(edge.status || "UNKNOWN").toUpperCase()}</Badge>{isCrossRoot(edge) && <Badge tone="amber">CROSS-ROOT</Badge>}</div></div><EvidenceRefs fallback={edge.evidence} refs={edge.evidence_refs} /></div>)}</div></section>;
}

function SourceOfTruthRegistry({ rules, selectedProject }: { rules: SourceOfTruth[]; selectedProject?: Project }) {
  return <section className="panel-shadow rounded-2xl border border-slate-200/80 bg-white p-6"><div className="flex items-start justify-between gap-4"><div><p className="text-[11px] font-bold uppercase tracking-[0.18em] text-slate-400">Source of truth</p><h2 className="mt-2 text-lg font-semibold tracking-tight text-slate-900">{selectedProject ? `${selectedProject.name} authority` : "Portfolio authority"}</h2><p className="mt-1 text-sm text-slate-500">Declared authority records; absence is not inferred as authority.</p></div><Badge tone="blue">{rules.length} rules</Badge></div><div className="mt-5 space-y-3">{rules.length === 0 ? <EmptyState detail={selectedProject ? "No source-of-truth declaration is registered for this project." : "Ingest a Registry snapshot with source_of_truth records to populate this view."} title="No authority observed" /> : rules.map((rule, index) => <div className="rounded-xl border border-slate-100 p-4" key={rule.source_rule_id || `${rule.domain}-${index}`}><div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start"><div className="min-w-0"><p className="truncate text-sm font-semibold text-slate-800">{rule.domain || "UNKNOWN domain"}</p><p className="mt-1 text-xs text-slate-500">Authority: {rule.authority?.project_id || "UNKNOWN project"} · artifact: {rule.authority?.artifact || "UNKNOWN artifact"}</p><p className="mt-2 font-mono text-[11px] text-slate-400">snapshot: {shortId(rule.observed_snapshot_id)}</p></div><Badge tone={registryTone(rule.status)}>{(rule.status || "UNKNOWN").toUpperCase()}</Badge></div><EvidenceRefs fallback={rule.evidence} refs={rule.evidence_refs} /></div>)}</div></section>;
}

function PortfolioProvenance({ provenance }: { provenance: PortfolioProvenance | null }) {
  const snapshotIds = provenance?.snapshot_ids || [];
  return <section className="panel-shadow mt-6 rounded-2xl border border-slate-200/80 bg-white p-6"><div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start"><div><p className="text-[11px] font-bold uppercase tracking-[0.18em] text-slate-400">Portfolio provenance</p><h2 className="mt-2 text-lg font-semibold tracking-tight text-slate-900">Portable snapshot basis</h2><p className="mt-1 text-sm leading-6 text-slate-500">This surface reflects stored Registry snapshots. It does not perform a live scan or claim facts outside the observed records.</p></div><Badge tone="green">READ-ONLY</Badge></div><div className="mt-5 grid gap-4 sm:grid-cols-3"><Info label="Snapshots observed" value={String(provenance?.snapshot_count ?? "UNKNOWN")} /><Info label="Relationship records" value="See registry above" /><Info label="Authority records" value="See source of truth above" /></div><div className="mt-5 flex flex-wrap gap-2">{snapshotIds.length > 0 ? snapshotIds.map((snapshotId) => <span className="rounded-md bg-slate-50 px-2 py-1 font-mono text-[11px] text-slate-500" key={snapshotId}>{shortId(snapshotId)}</span>) : <span className="text-xs text-amber-700">UNKNOWN snapshot provenance</span>}</div></section>;
}

function changeStatusTone(status?: string): Tone {
  if (status === "approved") return "green";
  if (status === "rejected") return "red";
  if (status === "submitted") return "blue";
  if (status === "closed") return "neutral";
  return "amber";
}

function changeTypeLabel(changeType?: string) {
  if (changeType === "project_registration") return "PROJECT REGISTRATION";
  return (changeType || "UNKNOWN").replaceAll("_", " ").toUpperCase();
}

function ProposalsView({ changeRequests, projects, loading, actor, onRefresh }: { changeRequests: ChangeRequest[]; projects: Project[]; loading: boolean; actor: string; onRefresh: () => void }) {
  const [changeType, setChangeType] = useState<ChangeRequest["change_type"]>("feature");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [projectIds, setProjectIds] = useState("");
  const [acceptanceCriteria, setAcceptanceCriteria] = useState("");
  const [sourceOfTruth, setSourceOfTruth] = useState("");
  const [risk, setRisk] = useState("medium");
  const [approvalRequired, setApprovalRequired] = useState(true);
  const [selectedId, setSelectedId] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string>();
  const [formError, setFormError] = useState<string>();

  const selected = changeRequests.find((request) => request.change_id === selectedId);
  const listValues = (value: string) => value.split(",").map((item) => item.trim()).filter(Boolean);

  useEffect(() => {
    if (!selectedId && changeRequests[0]) setSelectedId(changeRequests[0].change_id);
  }, [changeRequests, selectedId]);

  const createDraft = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setMessage(undefined);
    setFormError(undefined);
    if (!actor) {
      setFormError("Set VITE_AINE_ACTOR before creating a proposal. The browser header is trusted context, not authentication.");
      return;
    }
    if (!title.trim() || !description.trim()) {
      setFormError("Title and description are required.");
      return;
    }
    setBusy(true);
    try {
      const response = await api.createChangeRequest({
        change_type: changeType,
        title: title.trim(),
        description: description.trim(),
        scope: { project_ids: listValues(projectIds) },
        acceptance_criteria: listValues(acceptanceCriteria.replaceAll("\n", ",")),
        source_of_truth: listValues(sourceOfTruth),
        evidence_ids: [],
        risk,
        approval_required: approvalRequired,
      });
      const created = response.result?.change_request;
      if (!created) throw new Error("Proposal response did not include a change request");
      setSelectedId(created.change_id);
      setMessage(`Draft ${created.change_id} created in the private Control Plane.`);
      setTitle("");
      setDescription("");
      setProjectIds("");
      setAcceptanceCriteria("");
      setSourceOfTruth("");
      onRefresh();
    } catch (reason: unknown) {
      setFormError(reason instanceof Error ? reason.message : "Unable to create proposal");
    } finally {
      setBusy(false);
    }
  };

  const submitForReview = async () => {
    if (!selected || !actor || selected.status !== "draft") return;
    setBusy(true);
    setMessage(undefined);
    setFormError(undefined);
    try {
      const response = await api.submitChangeRequest(selected.change_id);
      const submitted = response.result?.change_request;
      setMessage(submitted ? `${submitted.change_id} submitted as revision ${submitted.revision}.` : "Proposal submitted for review.");
      onRefresh();
    } catch (reason: unknown) {
      setFormError(reason instanceof Error ? reason.message : "Unable to submit proposal");
    } finally {
      setBusy(false);
    }
  };

  return <>
    <SectionTitle action={<div className="flex flex-wrap gap-2"><Badge tone={actor ? "blue" : "amber"}>{actor ? "CONTROL PLANE WRITE CONTEXT" : "ACTOR REQUIRED"}</Badge><Badge tone="green">SOURCE REPOS READ-ONLY</Badge></div>} description="Capture a feature, fix, requirement, or project-registration intent without editing a scanned repository. Drafts are append-only Control Plane records and can be submitted to the existing approval boundary." eyebrow="Controlled change intent" title="Proposals" />
    {!actor && <div className="mb-6 flex items-start gap-3 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-4 text-sm text-amber-800"><Icon name="lock" size={17} /><div><p className="font-semibold">Proposal creation is disabled until an actor is configured</p><p className="mt-1 leading-6 text-amber-700">Set <code className="rounded bg-amber-100 px-1.5 py-0.5 text-xs">VITE_AINE_ACTOR</code> for local trusted context. This does not replace authentication, authorization, TLS, or an identity provider.</p></div></div>}
    {message && <div className="mb-6 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">{message}</div>}
    {formError && <div className="mb-6 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">{formError}</div>}
    <div className="grid gap-6 xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
      <section className="panel-shadow rounded-2xl border border-slate-200/80 bg-white p-6">
        <div className="flex items-center justify-between"><div><p className="text-[11px] font-bold uppercase tracking-[0.18em] text-slate-400">Intent ledger</p><h2 className="mt-2 text-lg font-semibold tracking-tight text-slate-900">Change requests</h2></div><Badge tone="violet">{loading ? "…" : changeRequests.length}</Badge></div>
        <div className="mt-5 space-y-2">{changeRequests.length === 0 ? <EmptyState detail="Create a draft to record a feature, fix, requirement, or new project boundary." title="No proposals yet" /> : changeRequests.map((request) => <button className={`w-full rounded-xl border p-4 text-left transition ${selected?.change_id === request.change_id ? "border-indigo-200 bg-indigo-50/70" : "border-slate-100 hover:border-indigo-200 hover:bg-slate-50"}`} key={request.change_id} onClick={() => setSelectedId(request.change_id)}><div className="flex items-start gap-3"><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><p className="truncate text-sm font-semibold text-slate-800">{request.title}</p><Badge tone={changeStatusTone(request.status)}>{(request.status || "UNKNOWN").toUpperCase()}</Badge></div><p className="mt-2 text-xs text-slate-500">{changeTypeLabel(request.change_type)} · revision {request.revision} · {request.risk || "UNKNOWN"} risk</p><p className="mt-1 truncate font-mono text-[11px] text-slate-400">{request.change_id}</p></div><Icon className="mt-1 shrink-0 text-slate-300" name="arrow" size={16} /></div></button>)}</div>
        {selected && <div className="mt-6 rounded-xl border border-slate-100 bg-slate-50/70 p-4"><div className="flex items-center justify-between gap-3"><p className="text-xs font-bold uppercase tracking-[0.16em] text-slate-400">Selected boundary</p><Badge tone={changeStatusTone(selected.status)}>{(selected.status || "UNKNOWN").toUpperCase()}</Badge></div><p className="mt-3 text-sm font-semibold text-slate-800">{selected.description}</p><div className="mt-4 grid gap-3 sm:grid-cols-2"><Info label="Requested by" value={selected.requested_by || "UNKNOWN"} /><Info label="Owner" value={selected.owner || "UNKNOWN"} /><Info label="Created" value={formatDate(selected.created_at)} /><Info label="Approval" value={selected.approval_id || (selected.approval_required ? "created on submit" : "not required")} /></div><div className="mt-4 flex flex-wrap gap-2">{(selected.scope?.project_ids || []).length ? selected.scope?.project_ids?.map((projectId) => <Badge key={projectId} tone="blue">{projectId}</Badge>) : <span className="text-xs text-slate-400">No project scope declared</span>}</div>{selected.status === "draft" && <button className="mt-5 inline-flex items-center gap-2 rounded-xl bg-[#111a2c] px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50" disabled={!actor || busy} onClick={submitForReview}>{busy ? "Submitting…" : "Submit for review"}<Icon name="arrow" size={15} /></button>}</div>}
      </section>
      <section className="panel-shadow rounded-2xl border border-slate-200/80 bg-white p-6">
        <div className="mb-5"><p className="text-[11px] font-bold uppercase tracking-[0.18em] text-slate-400">Proposal mode</p><h2 className="mt-2 text-lg font-semibold tracking-tight text-slate-900">Open a controlled change</h2><p className="mt-2 text-sm leading-6 text-slate-500">This form writes only to the Control Plane store. It never edits source files, Git state, dependencies, or deployment configuration.</p></div>
        <form className="space-y-4" onSubmit={createDraft}>
          <div className="grid gap-4 sm:grid-cols-2"><label className="block"><span className="text-xs font-semibold text-slate-600">Change type</span><select className="mt-2 h-11 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-700 outline-none focus:border-indigo-300 focus:ring-4 focus:ring-indigo-100" disabled={!actor || busy} onChange={(event) => setChangeType(event.target.value as ChangeRequest["change_type"])} value={changeType}><option value="feature">Feature</option><option value="fix">Fix</option><option value="requirement">Requirement</option><option value="project_registration">Project registration</option></select></label><label className="block"><span className="text-xs font-semibold text-slate-600">Risk</span><select className="mt-2 h-11 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-700 outline-none focus:border-indigo-300 focus:ring-4 focus:ring-indigo-100" disabled={!actor || busy} onChange={(event) => setRisk(event.target.value)} value={risk}><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option></select></label></div>
          <label className="block"><span className="text-xs font-semibold text-slate-600">Title</span><input className="mt-2 h-11 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-700 outline-none placeholder:text-slate-400 focus:border-indigo-300 focus:ring-4 focus:ring-indigo-100" disabled={!actor || busy} onChange={(event) => setTitle(event.target.value)} placeholder="What should change?" value={title} /></label>
          <label className="block"><span className="text-xs font-semibold text-slate-600">Description</span><textarea className="mt-2 min-h-28 w-full resize-y rounded-xl border border-slate-200 bg-white px-3 py-3 text-sm leading-6 text-slate-700 outline-none placeholder:text-slate-400 focus:border-indigo-300 focus:ring-4 focus:ring-indigo-100" disabled={!actor || busy} onChange={(event) => setDescription(event.target.value)} placeholder="Why is this change needed?" value={description} /></label>
          <label className="block"><span className="text-xs font-semibold text-slate-600">Project IDs <span className="font-normal text-slate-400">(comma separated)</span></span><input className="mt-2 h-11 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-700 outline-none placeholder:text-slate-400 focus:border-indigo-300 focus:ring-4 focus:ring-indigo-100" disabled={!actor || busy} onChange={(event) => setProjectIds(event.target.value)} placeholder={projects.slice(0, 2).map((project) => project.project_id).join(", ") || "project.example"} value={projectIds} /></label>
          <div className="grid gap-4 sm:grid-cols-2"><label className="block"><span className="text-xs font-semibold text-slate-600">Acceptance criteria <span className="font-normal text-slate-400">(one per line)</span></span><textarea className="mt-2 min-h-28 w-full resize-y rounded-xl border border-slate-200 bg-white px-3 py-3 text-sm leading-6 text-slate-700 outline-none placeholder:text-slate-400 focus:border-indigo-300 focus:ring-4 focus:ring-indigo-100" disabled={!actor || busy} onChange={(event) => setAcceptanceCriteria(event.target.value)} placeholder="Verification is evidence-backed" value={acceptanceCriteria} /></label><label className="block"><span className="text-xs font-semibold text-slate-600">Source of truth <span className="font-normal text-slate-400">(comma separated)</span></span><textarea className="mt-2 min-h-28 w-full resize-y rounded-xl border border-slate-200 bg-white px-3 py-3 text-sm leading-6 text-slate-700 outline-none placeholder:text-slate-400 focus:border-indigo-300 focus:ring-4 focus:ring-indigo-100" disabled={!actor || busy} onChange={(event) => setSourceOfTruth(event.target.value)} placeholder="docs/BLUEPRINT.md" value={sourceOfTruth} /></label></div>
          <label className="flex items-start gap-3 rounded-xl border border-slate-100 bg-slate-50/70 p-3"><input checked={approvalRequired} className="mt-0.5 h-4 w-4 accent-indigo-600" disabled={!actor || busy} onChange={(event) => setApprovalRequired(event.target.checked)} type="checkbox" /><span><span className="block text-sm font-semibold text-slate-700">Require human approval on submit</span><span className="mt-1 block text-xs leading-5 text-slate-500">Recommended for changes that could affect more than one project boundary.</span></span></label>
          <button className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-4 py-3 text-sm font-semibold text-white transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50" disabled={!actor || busy} type="submit">{busy ? "Saving…" : "Create draft"}<Icon name="arrow" size={15} /></button>
        </form>
      </section>
    </div>
  </>;
}

function remediationStatusTone(status?: string): Tone {
  if (status === "approved" || status === "completed") return "green";
  if (status === "submitted" || status === "requested" || status === "running") return "blue";
  if (status === "failed" || status === "rejected" || status === "cancelled") return "red";
  return "amber";
}

function RemediationView({ plans, executionRequests, projects, loading, actor, onRefresh }: { plans: RemediationPlan[]; executionRequests: ExecutionRequest[]; projects: Project[]; loading: boolean; actor: string; onRefresh: () => void }) {
  const [title, setTitle] = useState("");
  const [rationale, setRationale] = useState("");
  const [findingId, setFindingId] = useState("");
  const [findingSummary, setFindingSummary] = useState("");
  const [projectIds, setProjectIds] = useState("");
  const [strategy, setStrategy] = useState("");
  const [checks, setChecks] = useState("");
  const [acceptanceCriteria, setAcceptanceCriteria] = useState("");
  const [risk, setRisk] = useState("medium");
  const [approvalRequired, setApprovalRequired] = useState(true);
  const [selectedId, setSelectedId] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string>();
  const [formError, setFormError] = useState<string>();

  const selected = plans.find((plan) => plan.plan_id === selectedId);
  const selectedExecution = executionRequests.find((execution) => execution.plan_id === selected?.plan_id);
  const listValues = (value: string) => value.split(/[\n,]/).map((item) => item.trim()).filter(Boolean);

  useEffect(() => {
    if (!selectedId && plans[0]) setSelectedId(plans[0].plan_id);
  }, [plans, selectedId]);

  const createPlan = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setMessage(undefined);
    setFormError(undefined);
    if (!actor) {
      setFormError("Set VITE_AINE_ACTOR before creating a remediation plan. The header is trusted context, not authentication.");
      return;
    }
    if (!title.trim() || !rationale.trim() || !findingSummary.trim() || !strategy.trim() || !checks.trim()) {
      setFormError("Title, rationale, finding summary, strategy, and validation checks are required.");
      return;
    }
    setBusy(true);
    try {
      const response = await api.createRemediationPlan({
        title: title.trim(),
        rationale: rationale.trim(),
        finding: { finding_id: findingId.trim() || undefined, summary: findingSummary.trim(), severity: risk },
        scope: { project_ids: listValues(projectIds) },
        strategy: { kind: "agent_assisted", description: strategy.trim() },
        validation: { required_checks: listValues(checks) },
        acceptance_criteria: listValues(acceptanceCriteria),
        evidence_ids: [],
        risk,
        approval_required: approvalRequired,
      });
      const created = response.result?.plan;
      if (!created) throw new Error("Remediation response did not include a plan");
      setSelectedId(created.plan_id);
      setMessage(`Remediation plan ${created.plan_id} created as a Control Plane draft.`);
      setTitle("");
      setRationale("");
      setFindingId("");
      setFindingSummary("");
      setProjectIds("");
      setStrategy("");
      setChecks("");
      setAcceptanceCriteria("");
      onRefresh();
    } catch (reason: unknown) {
      setFormError(reason instanceof Error ? reason.message : "Unable to create remediation plan");
    } finally {
      setBusy(false);
    }
  };

  const submitPlan = async () => {
    if (!selected || !actor || selected.status !== "draft") return;
    setBusy(true);
    setMessage(undefined);
    setFormError(undefined);
    try {
      await api.submitRemediationPlan(selected.plan_id);
      setMessage("Plan submitted for human approval. No source repository has been changed.");
      onRefresh();
    } catch (reason: unknown) {
      setFormError(reason instanceof Error ? reason.message : "Unable to submit remediation plan");
    } finally {
      setBusy(false);
    }
  };

  const requestDryRun = async () => {
    if (!selected || !actor || selected.status !== "approved") return;
    setBusy(true);
    setMessage(undefined);
    setFormError(undefined);
    try {
      const response = await api.requestRemediationDryRun(selected.plan_id);
      const execution = response.result?.execution;
      const mutationScope = execution?.mutation_scope;
      const mutationFields = ["source_repositories", "git", "deployment"] as const;
      if (
        !execution
        || execution.mode !== "dry_run"
        || !mutationScope
        || mutationFields.some((field) => mutationScope[field] !== false)
      ) {
        throw new Error("Control Plane returned an unsafe or incomplete dry-run contract");
      }
      setMessage("Dry-run request created. An external Local Runner must execute it and report evidence.");
      onRefresh();
    } catch (reason: unknown) {
      setFormError(reason instanceof Error ? reason.message : "Unable to request dry run");
    } finally {
      setBusy(false);
    }
  };

  return <>
    <SectionTitle action={<div className="flex flex-wrap gap-2"><Badge tone={actor ? "blue" : "amber"}>{actor ? "CONTROL PLANE WRITE CONTEXT" : "ACTOR REQUIRED"}</Badge><Badge tone="green">SOURCE REPOS READ-ONLY</Badge><Badge tone="violet">DRY-RUN ONLY</Badge></div>} description="Turn an evidence-backed finding into an approved remediation plan. The Control Plane records authority and validation; it never executes agents, shell commands, Git, or deployment." eyebrow="Safe change loop" title="Remediation" />
    {!actor && <div className="mb-6 flex items-start gap-3 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-4 text-sm text-amber-800"><Icon name="lock" size={17} /><div><p className="font-semibold">Remediation writes are disabled until an actor is configured</p><p className="mt-1 leading-6 text-amber-700">Set <code className="rounded bg-amber-100 px-1.5 py-0.5 text-xs">VITE_AINE_ACTOR</code> for local trusted context. Approval still requires a human role at the trusted boundary.</p></div></div>}
    {message && <div className="mb-6 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">{message}</div>}
    {formError && <div className="mb-6 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">{formError}</div>}
    <div className="grid gap-6 xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
      <section className="panel-shadow rounded-2xl border border-slate-200/80 bg-white p-6">
        <div className="flex items-center justify-between"><div><p className="text-[11px] font-bold uppercase tracking-[0.18em] text-slate-400">Plan ledger</p><h2 className="mt-2 text-lg font-semibold tracking-tight text-slate-900">Remediation plans</h2></div><Badge tone="violet">{loading ? "…" : plans.length}</Badge></div>
        <div className="mt-5 space-y-2">{plans.length === 0 ? <EmptyState detail="Create a finding-backed plan. It will remain a Control Plane record until explicitly submitted." title="No remediation plans yet" /> : plans.map((plan) => <button className={`w-full rounded-xl border p-4 text-left transition ${selected?.plan_id === plan.plan_id ? "border-indigo-200 bg-indigo-50/70" : "border-slate-100 hover:border-indigo-200 hover:bg-slate-50"}`} key={plan.plan_id} onClick={() => setSelectedId(plan.plan_id)}><div className="flex items-start gap-3"><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><p className="truncate text-sm font-semibold text-slate-800">{plan.title}</p><Badge tone={remediationStatusTone(plan.status)}>{(plan.status || "UNKNOWN").toUpperCase()}</Badge></div><p className="mt-2 text-xs text-slate-500">{plan.finding?.finding_id || "finding"} · {plan.risk || "UNKNOWN"} risk · revision {plan.revision}</p><p className="mt-1 truncate font-mono text-[11px] text-slate-400">{plan.plan_id}</p></div><Icon className="mt-1 shrink-0 text-slate-300" name="arrow" size={16} /></div></button>)}</div>
        {selected && <div className="mt-6 rounded-xl border border-slate-100 bg-slate-50/70 p-4"><div className="flex items-center justify-between gap-3"><p className="text-xs font-bold uppercase tracking-[0.16em] text-slate-400">Selected plan</p><Badge tone={remediationStatusTone(selected.status)}>{(selected.status || "UNKNOWN").toUpperCase()}</Badge></div><p className="mt-3 text-sm font-semibold text-slate-800">{selected.rationale}</p><div className="mt-4 grid gap-3 sm:grid-cols-2"><Info label="Finding" value={selected.finding?.summary || "UNKNOWN"} /><Info label="Owner" value={selected.owner || "UNKNOWN"} /><Info label="Approval" value={selected.approval_id || (selected.approval_required ? "created on submit" : "not required")} /><Info label="Checks" value={(selected.validation?.required_checks || []).join(", ") || "UNKNOWN"} /></div><div className="mt-4 flex flex-wrap gap-2">{(selected.scope?.project_ids || []).length ? selected.scope?.project_ids?.map((projectId) => <Badge key={projectId} tone="blue">{projectId}</Badge>) : <span className="text-xs text-slate-400">No project scope declared</span>}</div><div className="mt-5 flex flex-wrap gap-2">{selected.status === "draft" && <button className="inline-flex items-center gap-2 rounded-xl bg-[#111a2c] px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50" disabled={!actor || busy} onClick={submitPlan}>{busy ? "Submitting…" : "Submit for approval"}<Icon name="arrow" size={15} /></button>}{selected.status === "approved" && <button className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50" disabled={!actor || busy} onClick={requestDryRun}>{busy ? "Requesting…" : "Request dry run"}<Icon name="activity" size={15} /></button>}</div>{selectedExecution && <div className="mt-5 rounded-xl border border-indigo-100 bg-white p-3"><div className="flex items-center justify-between gap-3"><p className="text-xs font-bold uppercase tracking-[0.14em] text-slate-400">Execution request</p><Badge tone={remediationStatusTone(selectedExecution.status)}>{selectedExecution.status.toUpperCase()}</Badge></div><p className="mt-2 truncate font-mono text-[11px] text-slate-400">{selectedExecution.execution_id}</p><p className="mt-2 text-xs leading-5 text-slate-500">{selectedExecution.mode} · {selectedExecution.runner_kind || "local runner"} · source repositories unchanged</p></div>}</div>}
      </section>
      <section className="panel-shadow rounded-2xl border border-slate-200/80 bg-white p-6">
        <div className="mb-5"><p className="text-[11px] font-bold uppercase tracking-[0.18em] text-slate-400">Plan authoring</p><h2 className="mt-2 text-lg font-semibold tracking-tight text-slate-900">Prepare a safe remediation</h2><p className="mt-2 text-sm leading-6 text-slate-500">This form records the finding, proposed strategy, and validation gate. It does not accept local paths and does not grant permission to edit a repository.</p></div>
        <form className="space-y-4" onSubmit={createPlan}>
          <div className="grid gap-4 sm:grid-cols-2"><label className="block"><span className="text-xs font-semibold text-slate-600">Risk</span><select className="mt-2 h-11 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-700 outline-none focus:border-indigo-300 focus:ring-4 focus:ring-indigo-100" disabled={!actor || busy} onChange={(event) => setRisk(event.target.value)} value={risk}><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option><option value="critical">Critical</option></select></label><label className="block"><span className="text-xs font-semibold text-slate-600">Finding ID <span className="font-normal text-slate-400">(optional)</span></span><input className="mt-2 h-11 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-700 outline-none placeholder:text-slate-400 focus:border-indigo-300 focus:ring-4 focus:ring-indigo-100" disabled={!actor || busy} onChange={(event) => setFindingId(event.target.value)} placeholder="DEP-001" value={findingId} /></label></div>
          <label className="block"><span className="text-xs font-semibold text-slate-600">Title</span><input className="mt-2 h-11 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-700 outline-none placeholder:text-slate-400 focus:border-indigo-300 focus:ring-4 focus:ring-indigo-100" disabled={!actor || busy} onChange={(event) => setTitle(event.target.value)} placeholder="Repair unresolved dependency evidence" value={title} /></label>
          <label className="block"><span className="text-xs font-semibold text-slate-600">Finding summary</span><textarea className="mt-2 min-h-24 w-full resize-y rounded-xl border border-slate-200 bg-white px-3 py-3 text-sm leading-6 text-slate-700 outline-none placeholder:text-slate-400 focus:border-indigo-300 focus:ring-4 focus:ring-indigo-100" disabled={!actor || busy} onChange={(event) => setFindingSummary(event.target.value)} placeholder="What evidence-backed problem needs correction?" value={findingSummary} /></label>
          <label className="block"><span className="text-xs font-semibold text-slate-600">Rationale</span><textarea className="mt-2 min-h-24 w-full resize-y rounded-xl border border-slate-200 bg-white px-3 py-3 text-sm leading-6 text-slate-700 outline-none placeholder:text-slate-400 focus:border-indigo-300 focus:ring-4 focus:ring-indigo-100" disabled={!actor || busy} onChange={(event) => setRationale(event.target.value)} placeholder="Why should this remediation be performed?" value={rationale} /></label>
          <label className="block"><span className="text-xs font-semibold text-slate-600">Project IDs <span className="font-normal text-slate-400">(comma separated)</span></span><input className="mt-2 h-11 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-700 outline-none placeholder:text-slate-400 focus:border-indigo-300 focus:ring-4 focus:ring-indigo-100" disabled={!actor || busy} onChange={(event) => setProjectIds(event.target.value)} placeholder={projects.slice(0, 2).map((project) => project.project_id).join(", ") || "project.example"} value={projectIds} /></label>
          <label className="block"><span className="text-xs font-semibold text-slate-600">Strategy</span><textarea className="mt-2 min-h-24 w-full resize-y rounded-xl border border-slate-200 bg-white px-3 py-3 text-sm leading-6 text-slate-700 outline-none placeholder:text-slate-400 focus:border-indigo-300 focus:ring-4 focus:ring-indigo-100" disabled={!actor || busy} onChange={(event) => setStrategy(event.target.value)} placeholder="Describe the proposed agent-assisted change without a local path." value={strategy} /></label>
          <div className="grid gap-4 sm:grid-cols-2"><label className="block"><span className="text-xs font-semibold text-slate-600">Validation checks <span className="font-normal text-slate-400">(one per line)</span></span><textarea className="mt-2 min-h-24 w-full resize-y rounded-xl border border-slate-200 bg-white px-3 py-3 text-sm leading-6 text-slate-700 outline-none placeholder:text-slate-400 focus:border-indigo-300 focus:ring-4 focus:ring-indigo-100" disabled={!actor || busy} onChange={(event) => setChecks(event.target.value)} placeholder="registry.validate\npreflight" value={checks} /></label><label className="block"><span className="text-xs font-semibold text-slate-600">Acceptance criteria <span className="font-normal text-slate-400">(one per line)</span></span><textarea className="mt-2 min-h-24 w-full resize-y rounded-xl border border-slate-200 bg-white px-3 py-3 text-sm leading-6 text-slate-700 outline-none placeholder:text-slate-400 focus:border-indigo-300 focus:ring-4 focus:ring-indigo-100" disabled={!actor || busy} onChange={(event) => setAcceptanceCriteria(event.target.value)} placeholder="Tests and evidence pass" value={acceptanceCriteria} /></label></div>
          <label className="flex items-start gap-3 rounded-xl border border-slate-100 bg-slate-50/70 p-3"><input checked={approvalRequired} className="mt-0.5 h-4 w-4 accent-indigo-600" disabled={!actor || busy} onChange={(event) => setApprovalRequired(event.target.checked)} type="checkbox" /><span><span className="block text-sm font-semibold text-slate-700">Require human approval</span><span className="mt-1 block text-xs leading-5 text-slate-500">Required before a dry-run request can be created when enabled.</span></span></label>
          <button className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-4 py-3 text-sm font-semibold text-white transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50" disabled={!actor || busy} type="submit">{busy ? "Saving…" : "Create remediation draft"}<Icon name="arrow" size={15} /></button>
        </form>
      </section>
    </div>
  </>;
}

function runnerStatusTone(status?: string): Tone {
  if (status === "completed" || status === "pass") return "green";
  if (status === "proposed") return "amber";
  if (status === "requested" || status === "running") return "blue";
  if (status === "failed" || status === "cancelled" || status === "fail") return "red";
  return "amber";
}

function RunnerView({ sessions, patchArtifacts, reports, executionRequests, loading, actor, onRefresh }: { sessions: RunnerSession[]; patchArtifacts: PatchArtifact[]; reports: ValidationReport[]; executionRequests: ExecutionRequest[]; loading: boolean; actor: string; onRefresh: () => void }) {
  const [selectedId, setSelectedId] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string>();
  const [formError, setFormError] = useState<string>();

  useEffect(() => {
    if (!selectedId && sessions[0]) setSelectedId(sessions[0].session_id);
  }, [sessions, selectedId]);

  const selected = sessions.find((session) => session.session_id === selectedId);
  const selectedPatches = patchArtifacts.filter((artifact) => artifact.session_id === selected?.session_id);
  const selectedReports = reports.filter((report) => report.session_id === selected?.session_id);
  const sessionForExecution = (executionId: string) => sessions.find((session) => session.execution_id === executionId);

  const createSession = async (executionId: string) => {
    if (!actor) {
      setFormError("Set VITE_AINE_ACTOR before creating a runner session. This header is trusted context, not authentication.");
      return;
    }
    setBusy(true);
    setMessage(undefined);
    setFormError(undefined);
    try {
      const response = await api.createRunnerSession(executionId);
      const session = response.result?.session;
      if (!session) throw new Error("Runner session response did not include a session");
      setSelectedId(session.session_id);
      setMessage("External runner session recorded. AINE will wait for portable patch and validation reports.");
      onRefresh();
    } catch (reason: unknown) {
      setFormError(reason instanceof Error ? reason.message : "Unable to create runner session");
    } finally {
      setBusy(false);
    }
  };

  return <>
    <SectionTitle action={<div className="flex flex-wrap gap-2"><Badge tone="green">SOURCE REPOS READ-ONLY</Badge><Badge tone="violet">EXTERNAL RUNNER</Badge><Badge tone="amber">NO PATCH APPLY</Badge></div>} description="Inspect the isolated runner boundary, proposed patch metadata, and validation evidence. AINE records results but never starts an agent, reads a workspace, or applies a patch." eyebrow="Evidence boundary" title="Runner evidence" />
    {message && <div className="mb-6 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">{message}</div>}
    {formError && <div className="mb-6 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">{formError}</div>}
    <div className="grid gap-6 xl:grid-cols-[0.85fr_1.15fr]">
      <section className="panel-shadow rounded-2xl border border-slate-200/80 bg-white p-6">
        <div className="flex items-center justify-between"><div><p className="text-[11px] font-bold uppercase tracking-[0.18em] text-slate-400">Execution queue</p><h2 className="mt-2 text-lg font-semibold tracking-tight text-slate-900">External runner requests</h2></div><Badge tone="blue">{loading ? "…" : executionRequests.length}</Badge></div>
        <div className="mt-5 space-y-3">{executionRequests.length === 0 ? <EmptyState detail="Approved dry-run executions appear here. AINE does not launch them automatically." title="No runner requests" /> : executionRequests.map((execution) => { const existing = sessionForExecution(execution.execution_id); return <div className="rounded-xl border border-slate-100 p-4" key={execution.execution_id}><div className="flex items-start justify-between gap-3"><div className="min-w-0"><p className="truncate font-semibold text-slate-800">{execution.plan_id}</p><p className="mt-1 truncate font-mono text-[11px] text-slate-400">{execution.execution_id}</p></div><Badge tone={runnerStatusTone(execution.status)}>{(execution.status || "UNKNOWN").toUpperCase()}</Badge></div><p className="mt-3 text-xs leading-5 text-slate-500">{execution.mode} · {execution.runner_kind || "local_runner"} · mutation scopes remain false</p>{existing ? <button className="mt-4 inline-flex items-center gap-2 rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-2 text-xs font-semibold text-indigo-700" onClick={() => setSelectedId(existing.session_id)}>Inspect session <Icon name="arrow" size={14} /></button> : <button className="mt-4 inline-flex items-center gap-2 rounded-lg bg-[#111a2c] px-3 py-2 text-xs font-semibold text-white transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50" disabled={!actor || busy || !["requested", "running"].includes(execution.status)} onClick={() => createSession(execution.execution_id)}>{busy ? "Recording…" : "Record external session"}<Icon name="external" size={14} /></button>}</div>; })}</div>
      </section>
      <section className="panel-shadow rounded-2xl border border-slate-200/80 bg-white p-6">
        <div className="flex items-center justify-between"><div><p className="text-[11px] font-bold uppercase tracking-[0.18em] text-slate-400">Portable reports</p><h2 className="mt-2 text-lg font-semibold tracking-tight text-slate-900">Session ledger</h2></div><Badge tone="violet">{loading ? "…" : sessions.length}</Badge></div>
        {sessions.length === 0 ? <div className="mt-5"><EmptyState detail="Create a session from an approved dry-run request, then let an isolated runner report evidence through the API." title="No runner sessions" /></div> : <div className="mt-5 grid gap-3 md:grid-cols-2">{sessions.map((session) => <button className={`rounded-xl border p-4 text-left transition ${selected?.session_id === session.session_id ? "border-indigo-200 bg-indigo-50/70" : "border-slate-100 hover:border-indigo-200 hover:bg-slate-50"}`} key={session.session_id} onClick={() => setSelectedId(session.session_id)}><div className="flex items-center justify-between gap-3"><p className="truncate font-semibold text-slate-800">{session.operation_profile || "runner session"}</p><Badge tone={runnerStatusTone(session.status)}>{(session.status || "UNKNOWN").toUpperCase()}</Badge></div><p className="mt-2 truncate font-mono text-[11px] text-slate-400">{session.session_id}</p><p className="mt-2 text-xs text-slate-500">{session.project_ids?.length || 0} project scope · rev {session.revision}</p></button>)}</div>}
        {selected && <div className="mt-6 rounded-xl border border-indigo-100 bg-slate-50/70 p-4"><div className="flex items-center justify-between gap-3"><div><p className="text-xs font-bold uppercase tracking-[0.16em] text-slate-400">Selected session</p><p className="mt-2 truncate font-mono text-[11px] text-slate-500">{selected.session_id}</p></div><Badge tone={runnerStatusTone(selected.status)}>{(selected.status || "UNKNOWN").toUpperCase()}</Badge></div><div className="mt-4 grid gap-3 sm:grid-cols-2"><Info label="Execution" value={selected.execution_id} /><Info label="Project scope" value={selected.project_ids?.join(", ") || "UNKNOWN"} /><Info label="Patch artifacts" value={String(selectedPatches.length)} /><Info label="Validation reports" value={String(selectedReports.length)} /></div><div className="mt-5 rounded-xl border border-amber-200 bg-amber-50 p-3"><p className="text-sm font-semibold text-amber-800">External runner only</p><p className="mt-1 text-xs leading-5 text-amber-700">These records do not authorize source edits, Git changes, deployment, or patch application. Unknown and conflict states remain visible.</p></div></div>}
      </section>
    </div>
    {selected && <div className="mt-6 grid gap-6 xl:grid-cols-2">
      <section className="panel-shadow rounded-2xl border border-slate-200/80 bg-white p-6"><div className="flex items-center justify-between"><div><p className="text-[11px] font-bold uppercase tracking-[0.18em] text-slate-400">Patch metadata</p><h2 className="mt-2 text-lg font-semibold tracking-tight text-slate-900">Proposed artifacts</h2></div><Badge tone="green">{selectedPatches.length}</Badge></div><div className="mt-5 space-y-3">{selectedPatches.length === 0 ? <EmptyState detail="The external runner may report a digest, relative file manifest, and portable artifact reference without sending raw source content." title="No patch artifact reported" /> : selectedPatches.map((artifact) => <div className="rounded-xl border border-slate-100 p-4" key={artifact.patch_id}><div className="flex items-center justify-between gap-3"><p className="font-semibold text-slate-800">{artifact.format || "patch artifact"}</p><Badge tone={runnerStatusTone(artifact.status)}>{(artifact.status || "UNKNOWN").toUpperCase()}</Badge></div><p className="mt-2 text-sm text-slate-600">{artifact.change_summary || "UNKNOWN"}</p><div className="mt-3 flex flex-wrap gap-2">{(artifact.files || []).map((file, index) => <span className="rounded-md bg-slate-50 px-2 py-1 font-mono text-[11px] text-slate-500" key={`${file.path}-${index}`}>{file.change}: {file.path || "UNKNOWN"}</span>)}</div><p className="mt-3 truncate font-mono text-[11px] text-slate-400">{shortId(artifact.content_digest)} · {artifact.file_count || 0} files</p></div>)}</div></section>
      <section className="panel-shadow rounded-2xl border border-slate-200/80 bg-white p-6"><div className="flex items-center justify-between"><div><p className="text-[11px] font-bold uppercase tracking-[0.18em] text-slate-400">Validation evidence</p><h2 className="mt-2 text-lg font-semibold tracking-tight text-slate-900">Checks and uncertainty</h2></div><Badge tone="violet">{selectedReports.length}</Badge></div><div className="mt-5 space-y-3">{selectedReports.length === 0 ? <EmptyState detail="Validation reports are submitted by an external runner and may preserve unknown, conflict, or missing checks." title="No validation report" /> : selectedReports.map((report) => <div className="rounded-xl border border-slate-100 p-4" key={report.report_id}><div className="flex items-center justify-between gap-3"><p className="font-semibold text-slate-800">{report.report_id}</p><Badge tone={runnerStatusTone(report.status)}>{(report.status || "UNKNOWN").toUpperCase()}</Badge></div><p className="mt-2 text-sm leading-6 text-slate-600">{report.summary || "UNKNOWN"}</p><div className="mt-3 space-y-2">{(report.checks || []).map((check, index) => <div className="flex items-center justify-between gap-3 rounded-lg bg-slate-50 px-3 py-2" key={`${check.check_id}-${index}`}><span className="truncate text-xs text-slate-600">{check.check_id || "UNKNOWN"}</span><Badge tone={runnerStatusTone(check.status)}>{(check.status || "UNKNOWN").toUpperCase()}</Badge></div>)}</div>{(report.missing_check_ids || []).length > 0 && <p className="mt-3 text-xs text-amber-700">Missing checks: {report.missing_check_ids?.join(", ")}</p>}</div>)}</div></section>
    </div>}
  </>;
}

function GovernanceView({ insights, loading }: { insights: PortfolioInsights; loading: boolean }) {
  return <>
    <SectionTitle description="Policy, authorization, approval, and audit decisions remain separate and inspectable. AINE does not collapse them into a single risk score." eyebrow="Control boundary" title="Governance" action={<Badge tone="violet">READ-ONLY DECISIONS</Badge>} />
    <div className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
      <section className="panel-shadow rounded-2xl border border-slate-200/80 bg-white p-6"><div className="mb-5"><p className="text-[11px] font-bold uppercase tracking-[0.18em] text-slate-400">Posture signals</p><h2 className="mt-2 text-lg font-semibold tracking-tight text-slate-900">Observed controls</h2></div><SignalList signals={insights.governanceSignals} /></section>
      <section className="panel-shadow rounded-2xl border border-slate-200/80 bg-white p-6"><div className="flex items-center justify-between"><div><p className="text-[11px] font-bold uppercase tracking-[0.18em] text-slate-400">Policy evaluations</p><h2 className="mt-2 text-lg font-semibold tracking-tight text-slate-900">Latest decisions</h2></div><Badge tone="blue">{loading ? "…" : insights.policyEvaluations.length}</Badge></div><div className="mt-5 space-y-3">{insights.policyEvaluations.length === 0 ? <EmptyState detail="Policy decisions appear after the Control Plane evaluates an advisory or enforced policy." title="No policy decisions observed" /> : insights.policyEvaluations.slice(-6).reverse().map((decision) => <div className="rounded-xl border border-slate-100 p-4" key={decision.id}><div className="flex flex-wrap items-center justify-between gap-3"><div><p className="font-semibold text-slate-800">{decision.policyId}</p><p className="mt-1 text-xs text-slate-400">{decision.mode} · {formatDate(decision.createdAt)}</p></div><StatusBadge status={decision.status} /></div><div className="mt-3 flex flex-wrap gap-2"><Badge tone={decision.blocked ? "red" : "neutral"}>{decision.blocked ? "BLOCKED" : "NOT BLOCKED"}</Badge>{decision.requiredChecks.map((check) => <span className="rounded-md bg-slate-50 px-2 py-1 text-[11px] text-slate-500" key={check}>{check}</span>)}</div></div>)}</div></section>
    </div>
    <div className="mt-6 grid gap-6 xl:grid-cols-2">
      <section className="panel-shadow rounded-2xl border border-slate-200/80 bg-white p-6"><div className="flex items-center justify-between"><div><p className="text-[11px] font-bold uppercase tracking-[0.18em] text-slate-400">RBAC / ABAC</p><h2 className="mt-2 text-lg font-semibold tracking-tight text-slate-900">Authorization decisions</h2></div><Badge tone="violet">{insights.authorizationEvaluations.length}</Badge></div><div className="mt-5 space-y-3">{insights.authorizationEvaluations.length === 0 ? <EmptyState detail="Allow, deny, and unknown authorization decisions are shown only when evaluated by the service." title="No authorization decisions observed" /> : insights.authorizationEvaluations.slice(-6).reverse().map((decision) => <div className="rounded-xl border border-slate-100 p-4" key={decision.id}><div className="flex items-center justify-between gap-3"><div className="min-w-0"><p className="truncate font-semibold text-slate-800">{decision.action} · {decision.resource}</p><p className="mt-1 truncate text-xs text-slate-400">{decision.subjectId} · {formatDate(decision.createdAt)}</p></div><StatusBadge status={decision.status} /></div>{decision.reasons.length > 0 && <p className="mt-3 text-xs leading-5 text-slate-500">{decision.reasons.join(" · ")}</p>}</div>)}</div></section>
      <section className="panel-shadow rounded-2xl border border-slate-200/80 bg-white p-6"><div className="flex items-center justify-between"><div><p className="text-[11px] font-bold uppercase tracking-[0.18em] text-slate-400">Human gate</p><h2 className="mt-2 text-lg font-semibold tracking-tight text-slate-900">Approval workflow</h2></div><Badge tone="amber">{insights.approvals.length}</Badge></div><div className="mt-5 space-y-3">{insights.approvals.length === 0 ? <EmptyState detail="Approval requests and decisions are read from the append-only audit stream." title="No approval requests observed" /> : insights.approvals.slice(0, 6).map((approval) => <div className="rounded-xl border border-slate-100 p-4" key={approval.id}><div className="flex items-center justify-between gap-3"><div><p className="font-semibold text-slate-800">{approval.id}</p><p className="mt-1 text-xs text-slate-400">requested by {approval.requestedBy} · {formatDate(approval.createdAt)}</p></div><StatusBadge status={approval.status} /></div><div className="mt-3 flex flex-wrap gap-2">{approval.requiredRoles.length ? approval.requiredRoles.map((role) => <Badge key={role} tone="neutral">{role}</Badge>) : <span className="text-xs text-slate-400">No required role observed</span>}{approval.decisions.map((decision, index) => <Badge key={`${decision}-${index}`} tone={decision === "approve" ? "green" : "red"}>{decision}</Badge>)}</div></div>)}</div></section>
    </div>
  </>;
}

function SecurityView({ adapters, contract, insights, loading }: { adapters: Adapter[]; contract: Contract | null; insights: PortfolioInsights; loading: boolean }) {
  return <>
    <SectionTitle description="Security visibility is evidence-backed: declared boundaries, configured adapters, explicit security evidence, and unresolved gaps are shown separately." eyebrow="Trust boundary" title="Security" action={<Badge tone="green"><span className="mr-1.5 h-1.5 w-1.5 rounded-full bg-emerald-500" /> NO SECRET VALUES</Badge>} />
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">{insights.securitySignals.map((signal) => <SignalCard key={signal.label} signal={signal} />)}</div>
    <div className="mt-6 grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
      <section className="panel-shadow rounded-2xl border border-slate-200/80 bg-white p-6"><div className="flex items-center justify-between"><div><p className="text-[11px] font-bold uppercase tracking-[0.18em] text-slate-400">Explicit records</p><h2 className="mt-2 text-lg font-semibold tracking-tight text-slate-900">Security evidence</h2></div><Badge tone="blue">{loading ? "…" : insights.securityEvidence.length}</Badge></div><div className="mt-5 space-y-3">{insights.securityEvidence.length === 0 ? <EmptyState detail="Only records explicitly tagged as security evidence are shown here. No tag means UNKNOWN, not pass." title="No security evidence observed" /> : insights.securityEvidence.map((item, index) => <div className="flex items-center gap-4 rounded-xl border border-slate-100 p-4" key={item.record_id || item.evidence_id || index}><div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-rose-50 text-rose-600"><Icon name="lock" size={18} /></div><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><p className="font-semibold text-slate-800">{item.kind || "security evidence"}</p><StatusBadge status={evidenceInsightStatus(item)} /></div><p className="mt-1 truncate font-mono text-xs text-slate-400">{shortId(item.record_id || item.evidence_id)} · {item.schema || "UNKNOWN schema"}</p></div><p className="text-xs text-slate-400">{formatDate(item.observed_at || item.created_at)}</p></div>)}</div></section>
      <section className="panel-shadow rounded-2xl border border-slate-200/80 bg-white p-6"><p className="text-[11px] font-bold uppercase tracking-[0.18em] text-slate-400">Boundary inventory</p><h2 className="mt-2 text-lg font-semibold tracking-tight text-slate-900">Declared controls</h2><div className="mt-5 space-y-4"><Info label="Contract version" value={contract?.contract_version || "UNKNOWN"} /><Info label="Service read-only" value={contract?.read_only === true ? "true (declared)" : "UNKNOWN"} /><Info label="Configured adapters" value={String(adapters.length)} /><Info label="Identity adapters" value={String(adapters.filter((adapter) => adapter.metadata?.kind === "identity").length)} /></div><div className="mt-6 rounded-xl border border-amber-200 bg-amber-50 p-4"><p className="text-sm font-semibold text-amber-800">Deployment boundary remains external</p><p className="mt-2 text-xs leading-5 text-amber-700">The frontend provides no authentication. Non-loopback use still requires TLS, identity, authorization, and network controls outside this UI.</p></div></section>
    </div>
  </>;
}

function EvalsView({ insights, loading, stale }: { insights: PortfolioInsights; loading: boolean; stale: boolean }) {
  const openChecks = insights.checks.filter((check) => check.status !== "pass").length;
  return <>
    <SectionTitle description="Evaluation results connect policy decisions and portable validation evidence to the checks that produced them. Missing evidence stays unresolved." eyebrow="Verification layer" title="Evals" action={<Badge tone="blue">EVIDENCE-LINKED</Badge>} />
    <div className="grid gap-4 sm:grid-cols-3"><MetricCard detail="Policy decisions and tagged records" icon="check" label="Evaluations" stale={stale} tone="blue" value={loading ? "—" : insights.evaluationRecords.length} /><MetricCard detail="Required checks reconstructed from decisions" icon="activity" label="Checks observed" stale={stale} tone="violet" value={loading ? "—" : insights.checks.length} /><MetricCard detail="Failed, unknown, or contradictory states" icon="shield" label="Open gaps" stale={stale} tone={openChecks ? "amber" : "green"} value={loading ? "—" : openChecks} /></div>
    <div className="mt-6 grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
      <section className="panel-shadow rounded-2xl border border-slate-200/80 bg-white p-6"><div className="flex items-center justify-between"><div><p className="text-[11px] font-bold uppercase tracking-[0.18em] text-slate-400">Evaluation ledger</p><h2 className="mt-2 text-lg font-semibold tracking-tight text-slate-900">Observed results</h2></div><Badge tone="blue">{insights.evaluationRecords.length}</Badge></div><div className="mt-5 space-y-3">{insights.evaluationRecords.length === 0 ? <EmptyState detail="Policy evaluations or explicitly tagged eval, test, validation, and preflight records will appear here." title="No evaluations observed" /> : insights.evaluationRecords.slice(0, 10).map((evaluation) => <div className="rounded-xl border border-slate-100 p-4" key={evaluation.id}><div className="flex items-center justify-between gap-3"><div className="min-w-0"><p className="truncate font-semibold text-slate-800">{evaluation.label}</p><p className="mt-1 truncate text-xs text-slate-400">{evaluation.source} · {formatDate(evaluation.createdAt)}</p></div><StatusBadge status={evaluation.status} /></div><p className="mt-3 text-xs leading-5 text-slate-500">{evaluation.detail}</p>{evaluation.evidenceIds.length > 0 && <p className="mt-2 truncate font-mono text-[11px] text-slate-400">evidence: {evaluation.evidenceIds.map(shortId).join(", ")}</p>}</div>)}</div></section>
      <section className="panel-shadow rounded-2xl border border-slate-200/80 bg-white p-6"><div className="flex items-center justify-between"><div><p className="text-[11px] font-bold uppercase tracking-[0.18em] text-slate-400">Check matrix</p><h2 className="mt-2 text-lg font-semibold tracking-tight text-slate-900">Required checks</h2></div><Badge tone="violet">{insights.checks.length}</Badge></div><div className="mt-5 space-y-2">{insights.checks.length === 0 ? <EmptyState detail="Required checks are exposed when a policy decision includes them." title="No checks reconstructed" /> : insights.checks.map((check) => <div className="flex items-center gap-3 rounded-xl border border-slate-100 px-3 py-3" key={check.id}><span className={`flex h-8 w-8 items-center justify-center rounded-lg ${check.status === "pass" ? "bg-emerald-50 text-emerald-600" : check.status === "fail" || check.status === "conflict" ? "bg-rose-50 text-rose-600" : "bg-amber-50 text-amber-600"}`}><Icon name="check" size={16} /></span><div className="min-w-0 flex-1"><p className="truncate text-sm font-semibold text-slate-700">{check.checkId}</p><p className="mt-1 truncate text-xs text-slate-400">{check.policyId}</p></div><StatusBadge status={check.status} /></div>)}</div></section>
    </div>
  </>;
}

function Info({ label, value }: { label: string; value: string }) {
  return <div><p className="text-xs text-slate-400">{label}</p><p className="mt-1 truncate text-sm font-semibold text-slate-700">{value}</p></div>;
}

function RelationshipRow({ edge, projectId }: { edge: Dependency; projectId: string }) {
  const source = edge.source?.project_id || "UNKNOWN";
  const target = edge.target?.project_id || "UNKNOWN";
  const direction = source === projectId ? "→" : "←";
  const peer = source === projectId ? target : source;
  const evidence = evidenceWithFallback(edge.evidence_refs, edge.evidence);
  return <div className="flex items-start gap-3 rounded-xl border border-slate-100 px-3 py-3"><span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-xs font-bold text-slate-500">{direction}</span><div className="min-w-0 flex-1"><p className="truncate text-sm font-medium text-slate-700">{peer}</p><p className="mt-1 text-xs text-slate-400">{edge.relationship_type || edge.kind || "dependency"} · {edge.scope || "unknown scope"}{edge.strength ? ` · ${edge.strength}` : ""}</p><p className="mt-2 font-mono text-[11px] text-slate-400">snapshot: {shortId(edge.observed_snapshot_id)}</p>{evidence.length > 0 && <p className="mt-2 truncate font-mono text-[11px] text-slate-400">evidence: {evidence.join(", ")}</p>}</div><Badge tone={registryTone(edge.status)}>{edge.status || "unknown"}</Badge></div>;
}

function EvidenceView({ evidence, loading, search, setSearch }: { evidence: EvidenceRecord[]; loading: boolean; search: string; setSearch: (value: string) => void }) {
  const filtered = evidence.filter((record) => !search.trim() || JSON.stringify(record).toLowerCase().includes(search.toLowerCase()));
  return <><SectionTitle action={<div className="relative w-full sm:w-72"><Icon className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" name="search" size={16} /><input className="h-10 w-full rounded-xl border border-slate-200 bg-white pl-10 pr-3 text-sm outline-none focus:border-indigo-300 focus:ring-4 focus:ring-indigo-100" onChange={(event) => setSearch(event.target.value)} placeholder="Search evidence" value={search} /></div>} description="Portable evidence records persisted by the Control Plane. Identity, provenance, and uncertainty remain inspectable." eyebrow="Evidence ledger" title="Evidence" /><section className="panel-shadow overflow-hidden rounded-2xl border border-slate-200/80 bg-white"><div className="border-b border-slate-100 px-6 py-4"><p className="text-xs text-slate-400">{loading ? "Loading records…" : `${filtered.length} records shown`}</p></div>{filtered.length === 0 ? <div className="p-6"><EmptyState detail="Evidence appears after a Registry snapshot or external adapter result is stored." title="No evidence records" /></div> : <div className="divide-y divide-slate-100">{filtered.map((record, index) => <div className="flex flex-col gap-3 px-6 py-5 sm:flex-row sm:items-center" key={record.record_id || record.evidence_id || index}><div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-emerald-50 text-emerald-600"><Icon name="file" size={18} /></div><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><p className="font-semibold text-slate-800">{record.kind || "evidence record"}</p><Badge tone={record.schema ? "green" : "amber"}>{record.schema || "UNKNOWN schema"}</Badge></div><p className="mt-1 truncate font-mono text-xs text-slate-400">{shortId(record.record_id || record.evidence_id)}</p></div><div className="text-left sm:text-right"><p className="text-xs font-medium text-slate-500">{formatDate(record.observed_at || record.created_at)}</p><p className="mt-1 text-[11px] text-slate-400">read-only record</p></div></div>)}</div>}</section></>;
}

function AuditView({ audit, loading }: { audit: AuditEvent[]; loading: boolean }) {
  const ordered = [...audit].sort((left, right) => String(right.created_at || "").localeCompare(String(left.created_at || "")));
  return <><SectionTitle description="An append-only view of snapshot ingestion, policy evaluation, and governance events." eyebrow="Accountability" title="Audit trail" /><section className="panel-shadow rounded-2xl border border-slate-200/80 bg-white p-6">{loading ? <p className="text-sm text-slate-400">Loading audit events…</p> : ordered.length === 0 ? <EmptyState detail="Events will appear when the Control Plane stores a snapshot or evaluates a decision." title="No audit events" /> : <div className="relative ml-3 border-l border-slate-200">{ordered.map((event, index) => <div className="relative pb-8 pl-8 last:pb-0" key={event.event_id || `${event.event_type}-${index}`}><span className="absolute -left-[7px] top-1 h-3 w-3 rounded-full border-2 border-white bg-indigo-500 shadow-sm" /><div className="flex flex-col justify-between gap-2 sm:flex-row sm:items-start"><div><p className="font-semibold text-slate-800">{event.event_type || "Unknown event"}</p><p className="mt-1 text-sm text-slate-500">Aggregate: <span className="font-mono text-xs">{event.aggregate_id || "portfolio"}</span></p></div><p className="text-xs text-slate-400">{formatDate(event.created_at)}</p></div></div>)}</div>}</section></>;
}

export default App;
