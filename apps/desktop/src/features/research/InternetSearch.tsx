/**
 * Search the Internet — the Internet Research Engine's primary action in the Research Centre.
 *
 * A natural-language research box launches a GENUINE background research job in the packaged backend
 * (not a placeholder, not a redirect to an external search site). Running jobs report live progress;
 * findings appear as they are discovered and are opened for review. Nothing is auto-approved — every
 * finding is a lead a researcher confirms, and acceptance still flows through the existing
 * reconstruction + approval workflow. Confidence is shown as a hint; "unknown" is shown as unknown.
 */
import { Globe, Loader2, Pause, Play, Search, StopCircle, ExternalLink } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import { Select } from "../../components/ui/select";
import { api, ApiError, type ResearchFinding, type ResearchJob } from "../../lib/api";

const DEPTHS = [
  { value: "quick", label: "Quick" },
  { value: "standard", label: "Standard" },
  { value: "deep", label: "Deep" },
];
const ACTIVE: ResearchJob["status"][] = ["pending", "running", "paused", "interrupted"];
const EXAMPLES = [
  "Find missing Rhymney/Moyston scorecards",
  "Research the 1924/25 season",
  "Research Horsham Cricket Association matches 1950 to 1960",
];

const STATUS_VARIANT: Record<ResearchJob["status"], "success" | "warning" | "muted" | "brand" | "danger"> = {
  pending: "muted", running: "brand", paused: "warning", succeeded: "success",
  failed: "danger", cancelled: "muted", interrupted: "warning",
};
// Review classification → badge tone (a finding may duplicate, extend, or be new vs existing records).
const CLASS_VARIANT: Record<string, "success" | "warning" | "muted" | "brand" | "danger" | "outline"> = {
  possible_duplicate: "warning", additional_evidence: "success", new: "brand",
  conflicting: "danger", insufficient: "muted",
};

export function InternetSearch({ workspaceId }: { workspaceId: string }) {
  const [query, setQuery] = useState("");
  const [depth, setDepth] = useState("standard");
  const [jobs, setJobs] = useState<ResearchJob[]>([]);
  const [openJob, setOpenJob] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadJobs = useCallback(async () => {
    try {
      setJobs(await api.researchJobs(workspaceId));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load research jobs.");
    }
  }, [workspaceId]);

  useEffect(() => { void loadJobs(); }, [loadJobs]);

  // Poll while any job is active, so progress and findings appear live.
  useEffect(() => {
    const anyActive = jobs.some((j) => ACTIVE.includes(j.status));
    if (anyActive && !timer.current) {
      timer.current = setInterval(() => void loadJobs(), 2500);
    } else if (!anyActive && timer.current) {
      clearInterval(timer.current);
      timer.current = null;
    }
    return () => {
      if (timer.current) { clearInterval(timer.current); timer.current = null; }
    };
  }, [jobs, loadJobs]);

  const start = async () => {
    if (!query.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await api.researchStartInternetSearch(workspaceId, { query: query.trim(), depth });
      setQuery("");
      await loadJobs();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not start the search.");
    } finally {
      setBusy(false);
    }
  };

  const act = async (fn: () => Promise<unknown>) => {
    try { await fn(); await loadJobs(); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Action failed."); }
  };

  return (
    <div className="flex flex-col gap-4">
      {/* Primary search panel */}
      <Card>
        <CardContent className="flex flex-col gap-3">
          <div className="flex items-center gap-2">
            <Globe className="h-5 w-5 text-brand" aria-hidden />
            <h3 className="text-sm font-semibold">Search the Internet</h3>
          </div>
          <p className="text-xs text-muted-foreground">
            Describe what you are looking for in plain English. OneStats researches online sources in the
            background, and brings back leads for you to review. Nothing is added to your records
            automatically — you confirm every finding.
          </p>
          <textarea
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) void start(); }}
            rows={2}
            placeholder="e.g. Find missing Rhymney/Moyston scorecards for the 1924/25 season"
            className="w-full rounded-[var(--radius-app)] border border-border bg-background p-2 text-sm"
          />
          <div className="flex flex-wrap items-end gap-2">
            <label className="flex flex-col gap-1 text-xs">
              <span className="text-muted-foreground">Search depth</span>
              <Select value={depth} onChange={(e) => setDepth(e.target.value)} className="w-36">
                {DEPTHS.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
              </Select>
            </label>
            <Button disabled={busy || !query.trim()} onClick={() => void start()} className="gap-1.5">
              {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : <Search className="h-4 w-4" aria-hidden />}
              Search the Internet
            </Button>
            <div className="flex flex-wrap gap-1">
              {EXAMPLES.map((ex) => (
                <button key={ex} type="button" onClick={() => setQuery(ex)}
                  className="rounded-full border border-border px-2 py-0.5 text-[11px] text-muted-foreground hover:border-brand hover:text-brand">
                  {ex}
                </button>
              ))}
            </div>
          </div>
          {error && <p className="text-xs text-danger">{error}</p>}
        </CardContent>
      </Card>

      {/* Research activity */}
      <Card>
        <CardContent className="flex flex-col gap-3">
          <h3 className="text-sm font-semibold">Research activity</h3>
          {jobs.length === 0 && (
            <p className="text-xs text-muted-foreground">
              No internet research yet. Start a search above to discover records from online sources.
            </p>
          )}
          {jobs.map((j) => (
            <JobRow key={j.id} workspaceId={workspaceId} job={j}
              open={openJob === j.id}
              onToggle={() => setOpenJob(openJob === j.id ? null : j.id)}
              onPause={() => void act(() => api.researchPauseJob(workspaceId, j.id))}
              onResume={() => void act(() => api.researchResumeJob(workspaceId, j.id))}
              onCancel={() => void act(() => api.researchCancelJob(workspaceId, j.id))} />
          ))}
        </CardContent>
      </Card>
    </div>
  );
}

function JobRow({ workspaceId, job, open, onToggle, onPause, onResume, onCancel }: {
  workspaceId: string;
  job: ResearchJob;
  open: boolean;
  onToggle: () => void;
  onPause: () => void;
  onResume: () => void;
  onCancel: () => void;
}) {
  const p = job.progress ?? {};
  const examined = p.sources_examined ?? 0;
  const findings = p.findings ?? 0;
  const active = ACTIVE.includes(job.status);
  const pendingReview = job.finding_counts?.pending_review ?? 0;
  return (
    <div className="flex flex-col gap-2 border-t border-border pt-2 first:border-0">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <Badge variant={STATUS_VARIANT[job.status]}>
          {job.status === "running" && <Loader2 className="mr-1 inline h-3 w-3 animate-spin" aria-hidden />}
          {job.status}
        </Badge>
        <span className="font-medium">{job.query}</span>
        <span className="text-xs text-muted-foreground">· {job.depth}</span>
        <span className="ml-auto flex items-center gap-1">
          {job.status === "running" && (
            <Button size="sm" variant="outline" onClick={onPause} className="gap-1"><Pause className="h-3.5 w-3.5" aria-hidden />Pause</Button>
          )}
          {job.status === "paused" && (
            <Button size="sm" variant="outline" onClick={onResume} className="gap-1"><Play className="h-3.5 w-3.5" aria-hidden />Resume</Button>
          )}
          {active && (
            <Button size="sm" variant="outline" onClick={onCancel} className="gap-1"><StopCircle className="h-3.5 w-3.5" aria-hidden />Cancel</Button>
          )}
          <Button size="sm" onClick={onToggle}>{open ? "Hide findings" : `Findings${pendingReview ? ` (${pendingReview})` : ""}`}</Button>
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
        <span>{p.phase ?? "queued"}</span>
        <span>· {examined} source{examined === 1 ? "" : "s"} examined</span>
        <span>· {findings} finding{findings === 1 ? "" : "s"}</span>
        {typeof p.candidates_remaining === "number" && p.candidates_remaining > 0 && (
          <span>· {p.candidates_remaining} to go</span>
        )}
        {active && <span className="h-1 w-24 overflow-hidden rounded bg-muted">
          <span className="block h-full w-1/3 animate-pulse bg-brand" />
        </span>}
        {job.last_error && <span className="text-danger">· {job.last_error}</span>}
      </div>
      {open && <JobFindings workspaceId={workspaceId} jobId={job.id} />}
    </div>
  );
}

function JobFindings({ workspaceId, jobId }: { workspaceId: string; jobId: string }) {
  const [findings, setFindings] = useState<ResearchFinding[] | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setFindings(await api.researchJobFindings(workspaceId, jobId));
  }, [workspaceId, jobId]);
  useEffect(() => { void load(); }, [load]);

  const review = async (id: string, status: string) => {
    setBusy(true);
    try { await api.researchReviewFinding(workspaceId, id, { status }); await load(); }
    finally { setBusy(false); }
  };

  if (findings === null) return <p className="text-xs text-muted-foreground">Loading findings…</p>;
  if (findings.length === 0) {
    return <p className="rounded-[var(--radius-app)] border border-border bg-muted/20 p-2 text-xs text-muted-foreground">
      No findings yet. As the search examines sources, cricket-relevant leads will appear here for review.
    </p>;
  }
  return (
    <div className="flex flex-col gap-2 rounded-[var(--radius-app)] border border-border bg-muted/20 p-2">
      <p className="text-[11px] text-muted-foreground">
        Leads from online sources — unverified. Review each and confirm before anything enters your records.
      </p>
      {findings.map((f) => (
        <div key={f.id} className="flex flex-col gap-1 border-t border-border pt-2 first:border-0">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <Badge variant="muted">{f.kind.replace(/_/g, " ")}</Badge>
            {f.classification !== "unknown" && (
              <Badge variant={CLASS_VARIANT[f.classification] ?? "outline"}>{f.classification.replace(/_/g, " ")}</Badge>
            )}
            <span className="font-medium">{f.title ?? f.summary ?? f.url}</span>
            <Badge variant={f.status === "accepted" ? "success" : f.status === "rejected" ? "muted" : "outline"}>
              {f.status.replace(/_/g, " ")}
            </Badge>
            <span className="text-xs text-muted-foreground">
              confidence {f.confidence == null ? "unknown" : `${Math.round(f.confidence * 100)}%`}
            </span>
          </div>
          {typeof f.extracted?.classification_reason === "string" && (
            <p className="text-[11px] italic text-muted-foreground">{f.extracted.classification_reason as string}</p>
          )}
          {(() => {
            const ps = (f.extracted?.player_suggestions ?? null) as Record<string, { display_name: string }[]> | null;
            if (!ps || Object.keys(ps).length === 0) return null;
            const line = Object.entries(ps).slice(0, 4)
              .map(([name, cands]) => `${name} → ${cands.map((c) => c.display_name).join(", ")}`)
              .join("; ");
            return (
              <p className="text-[11px] text-muted-foreground">
                Possible existing players: {line} (suggestions only — confirm before linking)
              </p>
            );
          })()}
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <a href={f.url} target="_blank" rel="noreferrer"
              className="inline-flex items-center gap-1 text-brand hover:underline">
              {f.source_host ?? "source"} <ExternalLink className="h-3 w-3" aria-hidden />
            </a>
            {f.raw_excerpt && <span className="text-muted-foreground line-clamp-1">“{f.raw_excerpt.slice(0, 160)}”</span>}
            {f.status === "pending_review" && (
              <span className="ml-auto flex gap-1">
                <Button size="sm" disabled={busy} onClick={() => void review(f.id, "accepted")}>Keep</Button>
                <Button size="sm" variant="outline" disabled={busy} onClick={() => void review(f.id, "rejected")}>Dismiss</Button>
              </span>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
