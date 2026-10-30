/**
 * OneStats Historical Research Centre (Phase 10) — Matches → Research Centre.
 *
 * A professional research workspace for reconstructing historical matches from original sources while
 * keeping ONE canonical match record with full provenance (reusing the Phase 6 scorecard model and the
 * Phase 7 approval workflow). Areas: Dashboard, Source Library (upload + OCR + correction + viewer),
 * Historical Research Timeline (season coverage), Research Gaps, Review & Verify, Research Projects and
 * Tasks. All figures are read from the backend — nothing is fabricated; unknown stays unknown.
 */
import { CalendarRange, FileText, FolderGit2, Library, ListChecks, Newspaper, RefreshCw, ScrollText, ShieldCheck } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { NewspaperSearch } from "./NewspaperSearch";
import { SeasonCompleteness } from "./SeasonCompleteness";
import { AppShell } from "../../components/layout/AppShell";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import { Select } from "../../components/ui/select";
import {
  api,
  ApiError,
  type GapCategory,
  type ProvenanceClaim,
  type ResearchDashboard,
  type ResearchExtraction,
  type ResearchGaps,
  type ResearchMatchRow,
  type ResearchProject,
  type ResearchSource,
  type ResearchTask,
  type ResearchTimeline,
  type SeasonCompletenessRow,
} from "../../lib/api";
import { NoWorkspace, useManage } from "../manage/_shared";

type Tab = "overview" | "seasons" | "sources" | "newspapers" | "timeline" | "gaps" | "review" | "projects" | "tasks";

const SOURCE_TYPES: { value: string; label: string }[] = [
  { value: "newspaper_article", label: "Newspaper article" },
  { value: "newspaper_clipping", label: "Newspaper clipping" },
  { value: "newspaper_edition", label: "Newspaper edition" },
  { value: "scorebook", label: "Scorebook (scanned)" },
  { value: "handwritten_scorecard", label: "Handwritten scorecard" },
  { value: "printed_scorecard", label: "Printed scorecard" },
  { value: "photograph", label: "Photograph" },
  { value: "pdf", label: "PDF document" },
  { value: "image", label: "Image" },
  { value: "club_record", label: "Club record" },
  { value: "annual_report", label: "Association annual report" },
  { value: "publication", label: "Cricket publication" },
  { value: "archived_website", label: "Archived website" },
  { value: "online_database", label: "Online cricket database" },
  { value: "manual_reference", label: "Manual reference" },
];

const COVERAGE_VARIANT: Record<string, "success" | "warning" | "muted" | "brand" | "outline"> = {
  comprehensive: "success", partial: "brand", significant_gaps: "warning",
  unassessed: "muted", inactive: "outline",
};

export function ResearchCentre() {
  const { workspaceId } = useManage();
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>("overview");
  const [gapsSub, setGapsSub] = useState<"overview" | "seasons" | "matches" | "tasks">("overview");
  const [dash, setDash] = useState<ResearchDashboard | null>(null);
  const [scRows, setScRows] = useState<SeasonCompletenessRow[]>([]);
  const [projects, setProjects] = useState<ResearchProject[]>([]);
  const [sources, setSources] = useState<ResearchSource[]>([]);
  const [timeline, setTimeline] = useState<ResearchTimeline | null>(null);
  const [gaps, setGaps] = useState<ResearchGaps | null>(null);
  const [tasks, setTasks] = useState<ResearchTask[]>([]);
  const [matches, setMatches] = useState<ResearchMatchRow[]>([]);
  const [openMatch, setOpenMatch] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);

  const loadFor = useCallback(async (which: Tab) => {
    if (!workspaceId) return;
    try {
      if (which === "overview") {
        setDash(await api.researchDashboard(workspaceId));
        setScRows((await api.researchSeasonCompleteness(workspaceId).catch(() => null))?.seasons ?? []);
      }
      else if (which === "sources") setSources(await api.researchSources(workspaceId));
      else if (which === "timeline") setTimeline(await api.researchTimeline(workspaceId));
      else if (which === "gaps") setGaps(await api.researchGaps(workspaceId));
      else if (which === "review") setMatches(await api.researchMatches(workspaceId));
      else if (which === "projects") setProjects(await api.researchProjects(workspaceId));
      else if (which === "tasks") setTasks(await api.researchTasks(workspaceId));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load the Research Centre.");
    }
  }, [workspaceId]);

  useEffect(() => {
    void loadFor(tab);
  }, [loadFor, tab]);

  if (!workspaceId) return <NoWorkspace />;

  const act = async (fn: () => Promise<unknown>, msg: string) => {
    setBusy(true);
    setError(null);
    setFlash(null);
    try {
      await fn();
      setFlash(msg);
      await loadFor(tab);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Action failed.");
    } finally {
      setBusy(false);
    }
  };

  const uploadFile = async (sourceId: string, file: File) => {
    setBusy(true);
    setError(null);
    setFlash(null);
    try {
      const r = await api.researchUploadSourceFile(workspaceId, sourceId, file);
      setFlash(r.duplicate_of
        ? "Document uploaded — identical content already exists on another source."
        : "Document uploaded.");
      await loadFor("sources");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Upload failed.");
    } finally {
      setBusy(false);
    }
  };

  // One prominent headline indicator: a larger number with a colour accent only when it warrants attention.
  const bigStat = (label: string, n: number, accent: "success" | "warning" | "brand" | "muted") => (
    <div className="rounded-[var(--radius-app)] border border-border p-4">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="text-3xl font-semibold tabular-nums"
        style={{ color: n > 0 && accent !== "muted" ? `var(--${accent === "brand" ? "brand" : accent})` : undefined }}>
        {n}
      </div>
    </div>
  );

  const tabBtn = (key: Tab, label: string, icon: React.ReactNode) => (
    <button
      type="button"
      onClick={() => setTab(key)}
      className={`flex items-center gap-1.5 rounded-[var(--radius-app)] border px-3 py-1.5 text-sm ${
        tab === key ? "border-brand bg-brand/10 font-medium text-brand" : "border-border text-muted-foreground"
      }`}
    >
      {icon}
      {label}
    </button>
  );

  return (
    <AppShell title="Research Centre" subtitle="Reconstruct historical matches from original sources">
      <div className="mx-auto flex max-w-5xl flex-col gap-4">
        {error && (
          <p className="rounded-[var(--radius-app)] border border-danger/40 bg-danger/5 px-3 py-2 text-sm text-danger">{error}</p>
        )}
        {flash && (
          <p className="rounded-[var(--radius-app)] border border-success/40 bg-success/5 px-3 py-2 text-sm text-success">{flash}</p>
        )}

        <div className="flex flex-wrap items-center gap-2">
          {tabBtn("overview", "Dashboard", <RefreshCw className="h-4 w-4" aria-hidden />)}
          {tabBtn("seasons", "Seasons", <CalendarRange className="h-4 w-4" aria-hidden />)}
          {tabBtn("sources", "Source Library", <Library className="h-4 w-4" aria-hidden />)}
          {tabBtn("newspapers", "Newspaper Search", <Newspaper className="h-4 w-4" aria-hidden />)}
          {tabBtn("timeline", "Timeline", <ScrollText className="h-4 w-4" aria-hidden />)}
          {tabBtn("gaps", "Research Gaps", <FileText className="h-4 w-4" aria-hidden />)}
          {tabBtn("review", "Review & Verify", <ShieldCheck className="h-4 w-4" aria-hidden />)}
          {tabBtn("projects", "Research Projects", <FolderGit2 className="h-4 w-4" aria-hidden />)}
          {tabBtn("tasks", "Tasks", <ListChecks className="h-4 w-4" aria-hidden />)}
          <Button size="sm" variant="outline" className="ml-auto" disabled={busy} onClick={() => void loadFor(tab)}>
            <RefreshCw className="h-4 w-4" aria-hidden /> Refresh
          </Button>
        </div>

        {tab === "seasons" && (
          <Card>
            <CardContent className="flex flex-col gap-3">
              <div>
                <h3 className="text-sm font-semibold">Season Research Overview</h3>
                <p className="text-xs text-muted-foreground">
                  Historical seasons and their research completeness. Fixture coverage stays “unknown” until the
                  expected fixtures are established — a season is never called complete just from entered matches.
                </p>
              </div>
              <SeasonCompleteness onCreateTask={() => setTab("tasks")} />
            </CardContent>
          </Card>
        )}

        {tab === "overview" && dash && (() => {
          const seasonsToResearch = scRows.filter((s) => s.status !== "verified").length;
          const needsAttention = dash.draft_scorecards + dash.conflicting_evidence + dash.awaiting_verification;
          const priorities: { label: string; go: () => void }[] = [];
          const n = (x: number) => (x === 1 ? "" : "s");
          if (dash.draft_scorecards > 0) priorities.push({ label: `Review ${dash.draft_scorecards} incomplete scorecard${n(dash.draft_scorecards)}`, go: () => setTab("review") });
          if (dash.conflicting_evidence > 0) priorities.push({ label: `Resolve ${dash.conflicting_evidence} conflicting source${n(dash.conflicting_evidence)}`, go: () => setTab("review") });
          if (dash.awaiting_verification > 0) priorities.push({ label: `Verify ${dash.awaiting_verification} scorecard${n(dash.awaiting_verification)} awaiting approval`, go: () => setTab("review") });
          if (seasonsToResearch > 0) priorities.push({ label: `Research ${seasonsToResearch} season${n(seasonsToResearch)} needing attention`, go: () => setTab("seasons") });
          if (dash.open_tasks > 0) priorities.push({ label: `Continue ${dash.open_tasks} open research task${n(dash.open_tasks)}`, go: () => setTab("tasks") });
          return (
          <>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {bigStat("Verified matches", dash.verified, "success")}
              {bigStat("Needs attention", needsAttention, "warning")}
              {bigStat("Seasons to research", seasonsToResearch, "warning")}
              {bigStat("Open tasks", dash.open_tasks, "brand")}
            </div>
            <Card>
              <CardContent className="flex flex-col gap-2">
                <h3 className="text-sm font-semibold">Research priorities</h3>
                <p className="text-xs text-muted-foreground">The most useful next actions, from your records.</p>
                {priorities.length === 0 && (
                  <p className="text-sm text-muted-foreground">Nothing outstanding — every known record is verified.</p>
                )}
                {priorities.map((p, i) => (
                  <button key={i} type="button" onClick={p.go}
                    className="flex items-center justify-between rounded-[var(--radius-app)] border border-border px-3 py-2 text-left text-sm hover:border-brand">
                    <span>{p.label}</span><span className="text-muted-foreground" aria-hidden>→</span>
                  </button>
                ))}
              </CardContent>
            </Card>
            <Card>
              <CardContent className="flex flex-col gap-2">
                <h3 className="text-sm font-semibold">Recently added sources</h3>
                {dash.sources_recent.length === 0 && (
                  <p className="text-xs text-muted-foreground">No sources yet. Add one in the Source Library.</p>
                )}
                {dash.sources_recent.map((s) => (
                  <div key={s.id} className="flex items-center gap-2 text-sm">
                    <FileText className="h-4 w-4 text-muted-foreground" aria-hidden />
                    <span className="font-medium">{s.title}</span>
                    <Badge variant="muted">{s.source_type.replace(/_/g, " ")}</Badge>
                    <span className="ml-auto text-xs text-muted-foreground">
                      {s.created_at ? new Date(s.created_at).toLocaleDateString() : ""}
                    </span>
                  </div>
                ))}
              </CardContent>
            </Card>
          </>
          );
        })()}

        {tab === "sources" && (
          <Card>
            <CardContent className="flex flex-col gap-3">
              <h3 className="text-sm font-semibold">Source Library ({sources.length})</h3>
              <p className="text-xs text-muted-foreground">
                A historical source — newspaper report, scorebook, photograph or other document. Publication
                date is recorded separately from the match date, and copyright/usage is preserved.
              </p>
              {sources.map((s) => (
                <SourceRow key={s.id} workspaceId={workspaceId} source={s} busy={busy}
                  onUpload={uploadFile}
                  onExtract={() => act(() => api.researchExtract(workspaceId, s.id), "OCR run (review the text).")} />
              ))}
              <AddSource busy={busy} onAdd={(body) => act(() => api.researchCreateSource(workspaceId, body), "Source added.")} />
            </CardContent>
          </Card>
        )}

        {tab === "sources" && <AliasPanel workspaceId={workspaceId} />}

        {tab === "newspapers" && (
          <Card>
            <CardContent className="flex flex-col gap-3">
              <h3 className="text-sm font-semibold">Newspaper Search</h3>
              <NewspaperSearch workspaceId={workspaceId} onSaved={(m) => setFlash(m)} />
            </CardContent>
          </Card>
        )}

        {tab === "timeline" && timeline && (
          <Card>
            <CardContent className="flex flex-col gap-3">
              <h3 className="text-sm font-semibold">Historical Research Timeline</h3>
              <p className="text-xs text-muted-foreground">{timeline.methodology.note}</p>
              {timeline.seasons.length === 0 && <p className="text-xs text-muted-foreground">No seasons yet.</p>}
              {timeline.seasons.map((s) => (
                <div key={s.season_id} className="flex flex-wrap items-center gap-2 border-t border-border pt-2 text-sm first:border-0">
                  <span className="font-medium">{s.label}</span>
                  <Badge variant={COVERAGE_VARIANT[s.coverage_class] ?? "muted"}>
                    {s.coverage_class.replace(/_/g, " ")}
                  </Badge>
                  <span className="text-xs text-muted-foreground">
                    {s.verified_matches}/{s.total_matches} verified · {s.matches_without_result} without result
                    {s.disputed_matches > 0 ? ` · ${s.disputed_matches} disputed` : ""}
                  </span>
                  {s.assessment_basis && <span className="text-xs text-muted-foreground italic">assessed</span>}
                </div>
              ))}
            </CardContent>
          </Card>
        )}

        {tab === "gaps" && gaps && (() => {
          const cats = Object.entries(gaps) as [string, GapCategory][];
          const totalGaps = cats.reduce((a, [, c]) => a + c.count, 0);
          const top = [...cats].filter(([, c]) => c.count > 0).sort((a, b) => b[1].count - a[1].count);
          const subBtn = (key: typeof gapsSub, label: string) => (
            <button type="button" onClick={() => setGapsSub(key)}
              className={`rounded-[var(--radius-app)] border px-3 py-1 text-xs ${gapsSub === key ? "border-brand bg-brand/10 font-medium text-brand" : "border-border text-muted-foreground hover:text-foreground"}`}>
              {label}
            </button>
          );
          return (
          <Card>
            <CardContent className="flex flex-col gap-3">
              <h3 className="text-sm font-semibold">Research Gaps</h3>
              <div className="flex flex-wrap gap-2">
                {subBtn("overview", "Overview")}
                {subBtn("seasons", "Seasons")}
                {subBtn("matches", "Matches")}
                {subBtn("tasks", "Research Tasks")}
              </div>

              {gapsSub === "overview" && (
                <div className="flex flex-col gap-2">
                  <p className="text-xs text-muted-foreground">
                    The most significant unresolved issues, from real data. An unsearched period is never reported
                    as complete.
                  </p>
                  {totalGaps === 0 && <p className="text-sm text-muted-foreground">No outstanding gaps in the known records.</p>}
                  {top.slice(0, 5).map(([key, cat]) => (
                    <div key={key} className="flex items-center gap-2 rounded-[var(--radius-app)] border border-border px-3 py-2 text-sm">
                      <span className="font-medium">{key.replace(/_/g, " ")}</span>
                      <Badge variant="warning">{cat.count}</Badge>
                      <Button size="sm" variant="outline" className="ml-auto" disabled={busy}
                        onClick={() => void act(() => api.researchCreateTask(workspaceId,
                          { title: `Address: ${key.replace(/_/g, " ")}`, gap_kind: key }), "Research task created.")}>
                        Create task
                      </Button>
                    </div>
                  ))}
                </div>
              )}

              {gapsSub === "seasons" && <SeasonCompleteness onCreateTask={() => setTab("tasks")} />}

              {gapsSub === "matches" && (
                <div className="flex flex-col gap-2">
                  <p className="text-xs text-muted-foreground">Match-level gaps by category; open a category to work through it.</p>
                  {cats.map(([key, cat]) => (
                    <div key={key} className="flex flex-col gap-1 border-t border-border pt-2 first:border-0">
                      <div className="flex items-center gap-2 text-sm">
                        <span className="font-medium">{key.replace(/_/g, " ")}</span>
                        <Badge variant={cat.count > 0 ? "warning" : "muted"}>{cat.count}</Badge>
                        <Button size="sm" variant="outline" className="ml-auto" disabled={busy || cat.count === 0}
                          onClick={() => void act(() => api.researchCreateTask(workspaceId,
                            { title: `Address: ${key.replace(/_/g, " ")}`, gap_kind: key }), "Research task created.")}>
                          Create task
                        </Button>
                      </div>
                      {(cat.sample ?? []).slice(0, 3).map((s) => (
                        <button key={s.match_id} type="button"
                          onClick={() => navigate(`/matches?open=${s.match_id}`)}
                          className="ml-1 flex items-center gap-1 text-left text-xs text-muted-foreground hover:text-brand hover:underline">
                          · {s.match_date ?? "date unknown"}{s.round ? ` · ${s.round}` : ""}
                          <span aria-hidden>→</span>
                        </button>
                      ))}
                    </div>
                  ))}
                </div>
              )}

              {gapsSub === "tasks" && (
                <div className="flex flex-col gap-2">
                  <p className="text-xs text-muted-foreground">Research tasks track the work to close these gaps.</p>
                  <Button size="sm" variant="outline" className="self-start" onClick={() => setTab("tasks")}>
                    Open Research Tasks
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>
          );
        })()}

        {tab === "review" && (
          <Card>
            <CardContent className="flex flex-col gap-3">
              <h3 className="text-sm font-semibold">Review &amp; Verify ({matches.length})</h3>
              <p className="text-xs text-muted-foreground">
                Reconstructions under review. Only verified records feed official statistics; a partially
                verified record contributes only the data it actually has; disputed records are held out.
              </p>
              <StartReconstruction busy={busy}
                onStart={(body) => act(() => api.researchStartReconstruction(workspaceId, body), "Provisional historical match created.")} />
              {matches.map((m) => (
                <div key={m.match_id} className="flex flex-col gap-2 border-t border-border pt-2 first:border-0">
                  <div className="flex flex-wrap items-center gap-2 text-sm">
                    <Badge variant={m.approval_status === "approved" ? "success"
                      : m.approval_status === "disputed" ? "warning" : "muted"}>{m.approval_status.replace(/_/g, " ")}</Badge>
                    <span className="text-xs text-muted-foreground">
                      {m.match_date ?? "date unknown"} · {m.sources} source{m.sources === 1 ? "" : "s"}
                    </span>
                    <div className="ml-auto flex flex-wrap gap-1">
                      <Button size="sm" variant="outline" disabled={busy}
                        onClick={() => setOpenMatch(openMatch === m.match_id ? null : m.match_id)}>
                        {openMatch === m.match_id ? "Close" : "Open"}
                      </Button>
                      {m.approval_status === "draft" && (
                        <Button size="sm" variant="outline" disabled={busy}
                          onClick={() => void act(() => api.researchSubmitForReview(workspaceId, m.match_id), "Submitted for review.")}>
                          Submit
                        </Button>
                      )}
                      <Button size="sm" disabled={busy}
                        onClick={() => void act(() => api.researchVerify(workspaceId, m.match_id, "verified_partial"), "Verified (partial).")}>
                        Verify partial
                      </Button>
                      <Button size="sm" variant="outline" disabled={busy}
                        onClick={() => void act(() => api.researchVerify(workspaceId, m.match_id, "approved"), "Verified.")}>
                        Verify
                      </Button>
                      <Button size="sm" variant="outline" disabled={busy}
                        onClick={() => void act(() => api.researchVerify(workspaceId, m.match_id, "disputed"), "Marked disputed.")}>
                        Dispute
                      </Button>
                    </div>
                  </div>
                  {openMatch === m.match_id && (
                    <ReconstructionDetail workspaceId={workspaceId} matchId={m.match_id}
                      onChanged={() => void loadFor("review")} />
                  )}
                </div>
              ))}
              {matches.length === 0 && <p className="text-xs text-muted-foreground">Nothing under review yet.</p>}
            </CardContent>
          </Card>
        )}

        {tab === "projects" && (
          <Card>
            <CardContent className="flex flex-col gap-3">
              <h3 className="text-sm font-semibold">Research Projects ({projects.length})</h3>
              <p className="text-xs text-muted-foreground">
                A project scopes a line of research (a club, competition, season or date range) so sources,
                notes and tasks can be grouped and progressed over time.
              </p>
              {projects.map((p) => (
                <div key={p.id} className="flex flex-wrap items-center gap-2 border-t border-border pt-2 text-sm first:border-0">
                  <span className="font-medium">{p.title}</span>
                  <Badge variant={p.status === "active" ? "success" : "muted"}>{p.status}</Badge>
                  {p.owner && <span className="text-xs text-muted-foreground">{p.owner}</span>}
                  {p.description && <span className="text-xs text-muted-foreground">{p.description}</span>}
                </div>
              ))}
              <AddProject busy={busy} onAdd={(body) => act(() => api.researchCreateProject(workspaceId, body), "Project created.")} />
            </CardContent>
          </Card>
        )}

        {tab === "tasks" && (
          <Card>
            <CardContent className="flex flex-col gap-3">
              <h3 className="text-sm font-semibold">Research Tasks ({tasks.length})</h3>
              {tasks.map((t) => (
                <div key={t.id} className="flex flex-wrap items-center gap-2 border-t border-border pt-2 text-sm first:border-0">
                  <span className="font-medium">{t.title}</span>
                  <Badge variant={t.status === "resolved" ? "success" : t.status === "open" ? "warning" : "muted"}>
                    {t.status.replace(/_/g, " ")}
                  </Badge>
                  {t.gap_kind && <span className="text-xs text-muted-foreground">{t.gap_kind.replace(/_/g, " ")}</span>}
                  {t.status !== "resolved" && (
                    <Button size="sm" variant="outline" className="ml-auto" disabled={busy}
                      onClick={() => void act(() => api.researchUpdateTask(workspaceId, t.id, { status: "resolved" }), "Task resolved.")}>
                      Mark resolved
                    </Button>
                  )}
                </div>
              ))}
              {tasks.length === 0 && <p className="text-xs text-muted-foreground">No research tasks yet. Create one from Research Gaps.</p>}
            </CardContent>
          </Card>
        )}
      </div>
    </AppShell>
  );
}

function StartReconstruction({ busy, onStart }: { busy: boolean; onStart: (body: Record<string, unknown>) => void }) {
  const [precision, setPrecision] = useState("unknown");
  const [date, setDate] = useState("");
  const [endDate, setEndDate] = useState("");
  return (
    <form className="flex flex-wrap items-end gap-2 text-xs"
      onSubmit={(e) => {
        e.preventDefault();
        onStart({
          date_precision: precision,
          match_date: precision === "unknown" || precision === "season" ? null : date || null,
          match_date_end: precision === "range" ? endDate || null : null,
        });
        setDate("");
        setEndDate("");
      }}>
      <label className="flex flex-col gap-1">
        <span className="text-muted-foreground">Date precision</span>
        <Select value={precision} onChange={(e) => setPrecision(e.target.value)} className="w-40">
          {["unknown", "exact", "year", "month", "approx", "range", "season"].map((p) => (
            <option key={p} value={p}>{p}</option>
          ))}
        </Select>
      </label>
      {precision !== "unknown" && precision !== "season" && (
        <label className="flex flex-col gap-1">
          <span className="text-muted-foreground">{precision === "range" ? "Start date" : "Date"}</span>
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)}
            className="rounded-[var(--radius-app)] border border-border bg-background px-2 py-1" />
        </label>
      )}
      {precision === "range" && (
        <label className="flex flex-col gap-1">
          <span className="text-muted-foreground">End date</span>
          <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)}
            className="rounded-[var(--radius-app)] border border-border bg-background px-2 py-1" />
        </label>
      )}
      <Button size="sm" type="submit" disabled={busy}>Start a reconstruction</Button>
    </form>
  );
}

function AliasPanel({ workspaceId }: { workspaceId: string }) {
  const [names, setNames] = useState("");
  const [entityType, setEntityType] = useState("club");
  const [term, setTerm] = useState("");
  const [expanded, setExpanded] = useState<string[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const saveGroup = async () => {
    const lines = names.split("\n").map((l) => l.trim()).filter(Boolean);
    if (lines.length === 0) return;
    setBusy(true);
    setMsg(null);
    try {
      const entityId = crypto.randomUUID();
      for (const alias of lines) {
        await api.researchCreateAlias(workspaceId, { entity_type: entityType, alias, entity_id: entityId });
      }
      setMsg(`Saved ${lines.length} name variant(s) as one alias group.`);
      setNames("");
    } catch {
      setMsg("Could not save aliases.");
    } finally {
      setBusy(false);
    }
  };
  const expand = async () => {
    if (!term.trim()) return;
    setExpanded((await api.researchExpandAliases(workspaceId, term)).expanded);
  };

  return (
    <Card>
      <CardContent className="flex flex-col gap-3">
        <h3 className="text-sm font-semibold">Historical names &amp; aliases</h3>
        <p className="text-xs text-muted-foreground">
          Record how a club/competition/place appeared historically — former names, abbreviations,
          spellings, newspaper transcription errors — so a search finds it under every variant. Original
          source text is never rewritten.
        </p>
        <div className="flex flex-wrap items-end gap-2 text-xs">
          <label className="flex flex-col gap-1">
            <span className="text-muted-foreground">Entity type</span>
            <Select value={entityType} onChange={(e) => setEntityType(e.target.value)} className="w-40">
              {["club", "competition", "grade", "team", "person", "venue", "place", "other"].map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </Select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-muted-foreground">Name variants (one per line)</span>
            <textarea value={names} onChange={(e) => setNames(e.target.value)} rows={3}
              placeholder={"Rhymney CC\nRhymney Cricket Club\nRymney CC"}
              className="w-72 rounded-[var(--radius-app)] border border-border bg-background p-2" />
          </label>
          <Button size="sm" disabled={busy} onClick={() => void saveGroup()}>Save alias group</Button>
        </div>
        <div className="flex flex-wrap items-end gap-2 border-t border-border pt-2 text-xs">
          <label className="flex flex-col gap-1">
            <span className="text-muted-foreground">Expand a search term</span>
            <input value={term} onChange={(e) => setTerm(e.target.value)} placeholder="e.g. Rhymney CC"
              className="w-56 rounded-[var(--radius-app)] border border-border bg-background px-2 py-1" />
          </label>
          <Button size="sm" variant="outline" disabled={busy || !term.trim()} onClick={() => void expand()}>Expand</Button>
          {expanded && (
            <div className="flex flex-wrap items-center gap-1">
              {expanded.map((t) => <Badge key={t} variant="muted">{t}</Badge>)}
            </div>
          )}
        </div>
        {msg && <p className="text-xs text-success">{msg}</p>}
      </CardContent>
    </Card>
  );
}

function ReconstructionDetail({ workspaceId, matchId, onChanged }: {
  workspaceId: string;
  matchId: string;
  onChanged: () => void;
}) {
  const [allSources, setAllSources] = useState<ResearchSource[]>([]);
  const [linked, setLinked] = useState<ResearchSource[]>([]);
  const [claims, setClaims] = useState<ProvenanceClaim[]>([]);
  const [conflicts, setConflicts] = useState<{ field_path: string; claims: ProvenanceClaim[] }[]>([]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  // claim form
  const [field, setField] = useState("match.result");
  const [claimSource, setClaimSource] = useState("");
  const [claimed, setClaimed] = useState("");
  const [normalised, setNormalised] = useState("");
  // attach form
  const [attachSource, setAttachSource] = useState("");

  const load = useCallback(async () => {
    const [all, lk, pv, cf] = await Promise.all([
      api.researchSources(workspaceId),
      api.researchMatchSources(workspaceId, matchId),
      api.researchMatchProvenance(workspaceId, matchId),
      api.researchConflicts(workspaceId, matchId),
    ]);
    setAllSources(all);
    setLinked(lk);
    setClaims(pv);
    setConflicts(cf);
    if (!claimSource && lk[0]) setClaimSource(lk[0].id);
  }, [workspaceId, matchId, claimSource]);
  useEffect(() => { void load(); }, [load]);

  const run = async (fn: () => Promise<unknown>, done: string) => {
    setBusy(true);
    setMsg(null);
    try {
      await fn();
      setMsg(done);
      await load();
      onChanged();
    } catch {
      setMsg("Action failed.");
    } finally {
      setBusy(false);
    }
  };

  const sourceLabel = (id: string | null) =>
    allSources.find((s) => s.id === id)?.title ?? (id ? "source" : "—");
  const unlinked = allSources.filter((s) => !linked.some((l) => l.id === s.id));

  return (
    <div className="flex flex-col gap-3 rounded-[var(--radius-app)] border border-border bg-muted/20 p-3">
      {msg && <p className="text-xs text-success">{msg}</p>}

      {/* attach sources */}
      <div className="flex flex-col gap-1">
        <div className="text-xs font-semibold">Sources on this match ({linked.length})</div>
        {linked.map((s) => <div key={s.id} className="text-xs text-muted-foreground">• {s.title}</div>)}
        <div className="flex flex-wrap items-end gap-2">
          <Select value={attachSource} onChange={(e) => setAttachSource(e.target.value)} className="w-56">
            <option value="">Attach a source…</option>
            {unlinked.map((s) => <option key={s.id} value={s.id}>{s.title}</option>)}
          </Select>
          <Button size="sm" disabled={busy || !attachSource}
            onClick={() => void run(() => api.researchAttachSource(workspaceId, matchId, { source_id: attachSource, role: "supporting" }), "Source attached.")}>
            Attach
          </Button>
        </div>
      </div>

      {/* record a claim (batting/bowling/result/etc. from a source) */}
      <div className="flex flex-col gap-1 border-t border-border pt-2">
        <div className="text-xs font-semibold">Record a claim from a source</div>
        <div className="flex flex-wrap items-end gap-2 text-xs">
          <label className="flex flex-col gap-1">
            <span className="text-muted-foreground">Field</span>
            <Select value={field} onChange={(e) => setField(e.target.value)} className="w-56">
              <option value="match.result">match.result</option>
              <option value="match.date">match.date</option>
              <option value="match.venue">match.venue</option>
              <option value="batting.home.Smith.runs">batting.home.&lt;player&gt;.runs</option>
              <option value="bowling.away.Jones.wickets">bowling.away.&lt;player&gt;.wickets</option>
              <option value="match.captain.home">match.captain.home</option>
              <option value="match.wicketkeeper.home">match.wicketkeeper.home</option>
            </Select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-muted-foreground">Source</span>
            <Select value={claimSource} onChange={(e) => setClaimSource(e.target.value)} className="w-48">
              <option value="">(no source)</option>
              {linked.map((s) => <option key={s.id} value={s.id}>{s.title}</option>)}
            </Select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-muted-foreground">Source's wording</span>
            <input value={claimed} onChange={(e) => setClaimed(e.target.value)} placeholder="e.g. won by 5 wkts / 54"
              className="w-40 rounded-[var(--radius-app)] border border-border bg-background px-2 py-1" />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-muted-foreground">Normalised (blank = unknown)</span>
            <input value={normalised} onChange={(e) => setNormalised(e.target.value)} placeholder="e.g. home_win / 54"
              className="w-40 rounded-[var(--radius-app)] border border-border bg-background px-2 py-1" />
          </label>
          <Button size="sm" disabled={busy || !field}
            onClick={() => void run(() => api.researchRecordClaim(workspaceId, matchId, {
              field_path: field, source_id: claimSource || null, claimed_value: claimed || null,
              normalised_value: normalised || null,
            }), "Claim recorded.").then(() => { setClaimed(""); setNormalised(""); })}>
            Record claim
          </Button>
        </div>
      </div>

      {/* provenance */}
      <div className="flex flex-col gap-1 border-t border-border pt-2">
        <div className="text-xs font-semibold">Field provenance ({claims.length})</div>
        {claims.map((c) => (
          <div key={c.id} className="flex flex-wrap items-center gap-2 text-xs">
            <span className="font-medium">{c.field_path}</span>
            <span className="text-muted-foreground">= {c.normalised_value ?? "unknown"}</span>
            <span className="text-muted-foreground">({sourceLabel(c.source_id)})</span>
            <Badge variant={c.status === "accepted" ? "success" : c.status === "rejected" ? "warning"
              : c.status === "superseded" ? "muted" : "outline"}>{c.status}</Badge>
          </div>
        ))}
      </div>

      {/* conflicts side by side */}
      {conflicts.length > 0 && (
        <div className="flex flex-col gap-2 border-t border-border pt-2">
          <div className="text-xs font-semibold text-warning">Conflicting evidence ({conflicts.length})</div>
          {conflicts.map((c) => (
            <div key={c.field_path} className="flex flex-col gap-1 rounded-[var(--radius-app)] border border-warning/40 p-2">
              <div className="text-xs font-medium">{c.field_path}</div>
              {c.claims.map((cl) => (
                <div key={cl.id} className="flex flex-wrap items-center gap-2 text-xs">
                  <span className="text-muted-foreground">{sourceLabel(cl.source_id)}:</span>
                  <span className="font-medium">{cl.normalised_value ?? "unknown"}</span>
                  <span className="text-muted-foreground">“{cl.claimed_value ?? ""}”</span>
                  <div className="ml-auto flex gap-1">
                    <Button size="sm" disabled={busy}
                      onClick={() => void run(() => api.researchAcceptClaim(workspaceId, cl.id, "accepted in review"), "Resolved.")}>
                      Accept
                    </Button>
                    <Button size="sm" variant="outline" disabled={busy}
                      onClick={() => void run(() => api.researchRejectClaim(workspaceId, cl.id, "rejected in review"), "Rejected (retained).")}>
                      Reject
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function SourceRow({ workspaceId, source, busy, onUpload, onExtract }: {
  workspaceId: string;
  source: ResearchSource;
  busy: boolean;
  onUpload: (sourceId: string, file: File) => void;
  onExtract: () => void;
}) {
  const [docUrl, setDocUrl] = useState<string | null>(null);
  const [extractions, setExtractions] = useState<ResearchExtraction[] | null>(null);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const viewDoc = async () => {
    try {
      setDocUrl(await api.researchSourceFileObjectUrl(workspaceId, source.id));
    } catch {
      setDocUrl(null);
    }
  };
  const loadText = async () => {
    const list = await api.researchExtractions(workspaceId, source.id);
    setExtractions(list);
    setDraft(Object.fromEntries(list.map((e) => [e.id, e.corrected_text ?? e.ocr_text ?? ""])));
  };
  const saveCorrection = async (extractionId: string) => {
    setSaving(true);
    setMsg(null);
    try {
      await api.researchCorrect(workspaceId, extractionId, draft[extractionId] ?? "");
      setMsg("Transcription saved.");
      await loadText();
    } catch {
      setMsg("Could not save.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex flex-col gap-1 border-t border-border pt-2 first:border-0">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-medium">{source.title}</span>
        <Badge variant="muted">{source.source_type.replace(/_/g, " ")}</Badge>
        {source.publication && <span className="text-xs text-muted-foreground">{source.publication}</span>}
        {source.publication_date && <span className="text-xs text-muted-foreground">pub. {source.publication_date}</span>}
        {source.copyright_status && <Badge variant="outline">{source.copyright_status}</Badge>}
        <span className="ml-auto flex items-center gap-2">
          <Badge variant={source.ocr_status === "done" ? "success" : "muted"}>{source.ocr_status}</Badge>
          {source.ocr_status !== "none" && (
            <button type="button" className="text-xs text-brand" disabled={busy} onClick={() => void viewDoc()}>View</button>
          )}
          {source.ocr_status !== "none" && (
            <button type="button" className="text-xs text-brand" disabled={busy} onClick={onExtract}>Run OCR</button>
          )}
          {source.ocr_status !== "none" && (
            <button type="button" className="text-xs text-brand" disabled={busy} onClick={() => void loadText()}>Transcribe</button>
          )}
          <label className="cursor-pointer text-xs text-brand">
            <input type="file" accept="image/*,application/pdf" className="hidden" disabled={busy}
              onChange={(e) => { const f = e.target.files?.[0]; if (f) onUpload(source.id, f); e.target.value = ""; }} />
            {source.ocr_status === "none" ? "Upload document" : "Replace"}
          </label>
        </span>
      </div>
      {docUrl && (
        <div className="rounded-[var(--radius-app)] border border-border p-2">
          <img src={docUrl} alt={source.title} className="max-h-96 w-auto" />
        </div>
      )}
      {extractions && (
        <div className="flex flex-col gap-2 rounded-[var(--radius-app)] border border-border p-2">
          {extractions.length === 0 && <p className="text-xs text-muted-foreground">No extraction yet — click Run OCR first.</p>}
          {extractions.map((e) => (
            <div key={e.id} className="flex flex-col gap-1 text-xs">
              <div className="text-muted-foreground">
                Page {e.page} · method {e.method}{e.confidence != null ? ` · confidence ${(e.confidence * 100).toFixed(0)}%` : ""}
              </div>
              {e.ocr_text != null && (
                <div>
                  <div className="text-muted-foreground">Machine OCR (read-only, preserved):</div>
                  <pre className="whitespace-pre-wrap rounded bg-muted/40 p-2">{e.ocr_text || "(empty)"}</pre>
                </div>
              )}
              <div className="text-muted-foreground">Corrected transcription:</div>
              <textarea
                value={draft[e.id] ?? ""}
                onChange={(ev) => setDraft((d) => ({ ...d, [e.id]: ev.target.value }))}
                rows={3}
                className="w-full rounded-[var(--radius-app)] border border-border bg-background p-2"
                placeholder="Type or correct the transcription here"
              />
              <Button size="sm" className="self-start" disabled={saving} onClick={() => void saveCorrection(e.id)}>
                Save transcription
              </Button>
            </div>
          ))}
          {msg && <p className="text-xs text-success">{msg}</p>}
        </div>
      )}
    </div>
  );
}

function AddProject({ busy, onAdd }: { busy: boolean; onAdd: (body: Record<string, unknown>) => void }) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  return (
    <form
      className="flex flex-wrap items-end gap-2 border-t border-border pt-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (!title.trim()) return;
        onAdd({ title: title.trim(), description: description.trim() || null });
        setTitle("");
        setDescription("");
      }}
    >
      <label className="flex flex-col gap-1 text-xs">
        <span className="text-muted-foreground">Project title</span>
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Rhymney CC 1891–1900"
          className="w-56 rounded-[var(--radius-app)] border border-border bg-background px-2 py-1 text-sm" />
      </label>
      <label className="flex flex-col gap-1 text-xs">
        <span className="text-muted-foreground">Description (optional)</span>
        <input value={description} onChange={(e) => setDescription(e.target.value)}
          className="w-64 rounded-[var(--radius-app)] border border-border bg-background px-2 py-1 text-sm" />
      </label>
      <Button size="sm" type="submit" disabled={busy || !title.trim()}>Create project</Button>
    </form>
  );
}

function AddSource({ busy, onAdd }: { busy: boolean; onAdd: (body: Record<string, unknown>) => void }) {
  const [title, setTitle] = useState("");
  const [sourceType, setSourceType] = useState("newspaper_article");
  const [publication, setPublication] = useState("");
  const [publicationDate, setPublicationDate] = useState("");
  const [copyright, setCopyright] = useState("");
  return (
    <form
      className="flex flex-wrap items-end gap-2 border-t border-border pt-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (!title.trim()) return;
        onAdd({
          title: title.trim(),
          source_type: sourceType,
          publication: publication.trim() || null,
          publication_date: publicationDate || null,
          publication_date_precision: publicationDate ? "exact" : "unknown",
          copyright_status: copyright.trim() || null,
        });
        setTitle("");
        setPublication("");
        setPublicationDate("");
        setCopyright("");
      }}
    >
      <label className="flex flex-col gap-1 text-xs">
        <span className="text-muted-foreground">Title / citation</span>
        <input value={title} onChange={(e) => setTitle(e.target.value)}
          placeholder="e.g. The Ararat Advertiser, 6 Nov 1931, p.3"
          className="w-64 rounded-[var(--radius-app)] border border-border bg-background px-2 py-1 text-sm" />
      </label>
      <label className="flex flex-col gap-1 text-xs">
        <span className="text-muted-foreground">Type</span>
        <Select value={sourceType} onChange={(e) => setSourceType(e.target.value)}>
          {SOURCE_TYPES.map((t) => (
            <option key={t.value} value={t.value}>{t.label}</option>
          ))}
        </Select>
      </label>
      <label className="flex flex-col gap-1 text-xs">
        <span className="text-muted-foreground">Publication</span>
        <input value={publication} onChange={(e) => setPublication(e.target.value)}
          className="w-40 rounded-[var(--radius-app)] border border-border bg-background px-2 py-1 text-sm" />
      </label>
      <label className="flex flex-col gap-1 text-xs">
        <span className="text-muted-foreground">Publication date</span>
        <input type="date" value={publicationDate} onChange={(e) => setPublicationDate(e.target.value)}
          className="rounded-[var(--radius-app)] border border-border bg-background px-2 py-1 text-sm" />
      </label>
      <label className="flex flex-col gap-1 text-xs">
        <span className="text-muted-foreground">Copyright</span>
        <input value={copyright} onChange={(e) => setCopyright(e.target.value)} placeholder="e.g. public_domain"
          className="w-36 rounded-[var(--radius-app)] border border-border bg-background px-2 py-1 text-sm" />
      </label>
      <Button size="sm" type="submit" disabled={busy || !title.trim()}>Add source</Button>
    </form>
  );
}
