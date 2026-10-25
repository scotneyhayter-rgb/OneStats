/**
 * OneStats Historical Research Centre (Phase 10) — Matches → Research Centre.
 *
 * Stage 10.1 foundation: a real, database-backed research dashboard, the Source Library and Research
 * Projects. Reconstruction keeps one canonical match record with full provenance (reusing the Phase 6
 * scorecard model and the Phase 7 approval workflow — research findings never change official statistics
 * without verification). All figures are read from the backend; nothing is fabricated. The remaining
 * research areas (reconstruction, discovery review, gaps, verify) build out in later Phase 10 stages.
 */
import { FileText, FolderGit2, Library, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { AppShell } from "../../components/layout/AppShell";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import { Select } from "../../components/ui/select";
import {
  api,
  ApiError,
  type ResearchDashboard,
  type ResearchProject,
  type ResearchSource,
} from "../../lib/api";
import { NoWorkspace, useManage } from "../manage/_shared";

type Tab = "overview" | "sources" | "projects";

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

export function ResearchCentre() {
  const { workspaceId } = useManage();
  const [tab, setTab] = useState<Tab>("overview");
  const [dash, setDash] = useState<ResearchDashboard | null>(null);
  const [projects, setProjects] = useState<ResearchProject[]>([]);
  const [sources, setSources] = useState<ResearchSource[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!workspaceId) return;
    try {
      const [d, p, s] = await Promise.all([
        api.researchDashboard(workspaceId),
        api.researchProjects(workspaceId),
        api.researchSources(workspaceId),
      ]);
      setDash(d);
      setProjects(p);
      setSources(s);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load the Research Centre.");
    }
  }, [workspaceId]);
  useEffect(() => {
    void load();
  }, [load]);

  if (!workspaceId) return <NoWorkspace />;

  const act = async (fn: () => Promise<unknown>, msg: string) => {
    setBusy(true);
    setError(null);
    setFlash(null);
    try {
      await fn();
      setFlash(msg);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Action failed.");
    } finally {
      setBusy(false);
    }
  };

  const stat = (label: string, n: number | string) => (
    <div className="rounded-[var(--radius-app)] border border-border p-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="text-xl font-semibold tabular-nums">{n}</div>
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
          {tabBtn("sources", "Source Library", <Library className="h-4 w-4" aria-hidden />)}
          {tabBtn("projects", "Research Projects", <FolderGit2 className="h-4 w-4" aria-hidden />)}
          <Button size="sm" variant="outline" className="ml-auto" disabled={busy} onClick={() => void load()}>
            <RefreshCw className="h-4 w-4" aria-hidden /> Refresh
          </Button>
        </div>

        {tab === "overview" && (
          <>
            <Card>
              <CardContent className="flex flex-col gap-3">
                <h3 className="text-sm font-semibold">Research overview</h3>
                {dash && (
                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                    {stat("Active projects", dash.projects_active)}
                    {stat("Sources", dash.sources_total)}
                    {stat("Matches under investigation", dash.matches_under_investigation)}
                    {stat("Incomplete scorecards", dash.draft_scorecards)}
                    {stat("Awaiting verification", dash.awaiting_verification)}
                    {stat("Conflicting evidence", dash.conflicting_evidence)}
                    {stat("Open research tasks", dash.open_tasks)}
                    {stat("Verified matches", dash.verified)}
                  </div>
                )}
              </CardContent>
            </Card>
            <Card>
              <CardContent className="flex flex-col gap-2">
                <h3 className="text-sm font-semibold">Recently added sources</h3>
                {dash && dash.sources_recent.length === 0 && (
                  <p className="text-xs text-muted-foreground">No sources yet. Add one in the Source Library.</p>
                )}
                {dash?.sources_recent.map((s) => (
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
        )}

        {tab === "sources" && (
          <Card>
            <CardContent className="flex flex-col gap-3">
              <h3 className="text-sm font-semibold">Source Library ({sources.length})</h3>
              <p className="text-xs text-muted-foreground">
                A historical source — a newspaper report, scorebook, photograph or other document. Publication
                date is recorded separately from the match date, and copyright/usage is preserved.
              </p>
              {sources.map((s) => (
                <div key={s.id} className="flex flex-wrap items-center gap-2 border-t border-border pt-2 text-sm first:border-0">
                  <span className="font-medium">{s.title}</span>
                  <Badge variant="muted">{s.source_type.replace(/_/g, " ")}</Badge>
                  {s.publication && <span className="text-xs text-muted-foreground">{s.publication}</span>}
                  {s.publication_date && (
                    <span className="text-xs text-muted-foreground">pub. {s.publication_date}</span>
                  )}
                  {s.copyright_status && <Badge variant="outline">{s.copyright_status}</Badge>}
                </div>
              ))}
              <AddSource busy={busy} onAdd={(body) => act(() => api.researchCreateSource(workspaceId, body), "Source added.")} />
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
      </div>
    </AppShell>
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
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="e.g. Rhymney CC 1891–1900"
          className="w-56 rounded-[var(--radius-app)] border border-border bg-background px-2 py-1 text-sm"
        />
      </label>
      <label className="flex flex-col gap-1 text-xs">
        <span className="text-muted-foreground">Description (optional)</span>
        <input
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          className="w-64 rounded-[var(--radius-app)] border border-border bg-background px-2 py-1 text-sm"
        />
      </label>
      <Button size="sm" type="submit" disabled={busy || !title.trim()}>
        Create project
      </Button>
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
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="e.g. The Ararat Advertiser, 6 Nov 1931, p.3"
          className="w-64 rounded-[var(--radius-app)] border border-border bg-background px-2 py-1 text-sm"
        />
      </label>
      <label className="flex flex-col gap-1 text-xs">
        <span className="text-muted-foreground">Type</span>
        <Select value={sourceType} onChange={(e) => setSourceType(e.target.value)}>
          {SOURCE_TYPES.map((t) => (
            <option key={t.value} value={t.value}>
              {t.label}
            </option>
          ))}
        </Select>
      </label>
      <label className="flex flex-col gap-1 text-xs">
        <span className="text-muted-foreground">Publication</span>
        <input
          value={publication}
          onChange={(e) => setPublication(e.target.value)}
          className="w-40 rounded-[var(--radius-app)] border border-border bg-background px-2 py-1 text-sm"
        />
      </label>
      <label className="flex flex-col gap-1 text-xs">
        <span className="text-muted-foreground">Publication date</span>
        <input
          type="date"
          value={publicationDate}
          onChange={(e) => setPublicationDate(e.target.value)}
          className="rounded-[var(--radius-app)] border border-border bg-background px-2 py-1 text-sm"
        />
      </label>
      <label className="flex flex-col gap-1 text-xs">
        <span className="text-muted-foreground">Copyright</span>
        <input
          value={copyright}
          onChange={(e) => setCopyright(e.target.value)}
          placeholder="e.g. public_domain"
          className="w-36 rounded-[var(--radius-app)] border border-border bg-background px-2 py-1 text-sm"
        />
      </label>
      <Button size="sm" type="submit" disabled={busy || !title.trim()}>
        Add source
      </Button>
    </form>
  );
}
