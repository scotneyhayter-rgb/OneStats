/**
 * Workspace Dashboard — the home command centre.
 *
 * A real, database-backed overview for the current workspace: identity, live summary counts, items
 * needing attention, historical-research progress, recent activity and quick actions. All figures come
 * from the backend (member-gated, role-aware on the server); empty workspaces get onboarding guidance.
 * No fabricated values, no non-functional buttons.
 */
import {
  AlertTriangle, Building2, DatabaseBackup, FileCheck2, Image as ImageIcon, PlusCircle, RefreshCw,
  ScrollText, Server, Trophy, Users,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AppShell } from "../components/layout/AppShell";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card, CardContent } from "../components/ui/card";
import { api, ApiError, type WorkspaceDashboard } from "../lib/api";
import { useWorkspace } from "../lib/workspace-context";

export function Dashboard() {
  const { current } = useWorkspace();
  const navigate = useNavigate();
  const [data, setData] = useState<WorkspaceDashboard | null>(null);
  const [logo, setLogo] = useState<string | null>(null);
  const [version, setVersion] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!current) return;
    try {
      setData(await api.workspaceDashboard(current.id));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load the dashboard.");
    }
  }, [current]);

  useEffect(() => {
    void load();
    api.health().then((h) => setVersion(`${h.version} (${h.env})`)).catch(() => setVersion(null));
  }, [load]);

  useEffect(() => {
    let revoked = false;
    setLogo(null);
    if (current) {
      api.brandingLogoObjectUrl(current.id).then((u) => { if (!revoked) setLogo(u); }).catch(() => {});
    }
    return () => { revoked = true; };
  }, [current]);

  if (!current) {
    return (
      <AppShell title="Dashboard" subtitle="Select or create a workspace">
        <Card><CardContent>
          <p className="text-sm text-muted-foreground">
            No workspace selected. Use <b>My Workspaces</b> in the sidebar to create or open one.
          </p>
        </CardContent></Card>
      </AppShell>
    );
  }

  const t = data?.totals;
  const at = data?.attention;
  const rs = data?.research;

  const summary = (label: string, n: number | undefined, icon: React.ReactNode, to?: string) => (
    <button type="button" disabled={!to} onClick={() => to && navigate(to)}
      className={`flex flex-col gap-1 rounded-[var(--radius-app)] border border-border p-3 text-left ${to ? "hover:border-brand" : ""}`}>
      <div className="flex items-center gap-2 text-xs text-muted-foreground">{icon}{label}</div>
      <div className="text-2xl font-semibold tabular-nums">{n ?? "—"}</div>
    </button>
  );

  const attentionItems = [
    { label: "Scorecards awaiting approval", n: at?.scorecards_awaiting_approval ?? 0, to: "/matches" },
    { label: "Possible duplicate matches", n: at?.possible_duplicate_matches ?? 0, to: "/manage/autosync" },
    { label: "Research conflicts", n: at?.research_conflicts ?? 0, to: "/manage/research" },
    { label: "Failed AutoSync jobs", n: at?.failed_autosync_jobs ?? 0, to: "/manage/autosync" },
  ].filter((i) => i.n > 0);

  const action = (label: string, icon: React.ReactNode, to: string) => (
    <Button size="sm" variant="outline" onClick={() => navigate(to)}>{icon}{label}</Button>
  );

  return (
    <AppShell title="Dashboard" subtitle={current.name}>
      <div className="mx-auto flex max-w-5xl flex-col gap-4">
        {error && <p className="rounded-[var(--radius-app)] border border-danger/40 bg-danger/5 px-3 py-2 text-sm text-danger">{error}</p>}

        {/* identity + quick actions */}
        <Card><CardContent className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center gap-3">
            {logo
              ? <img src={logo} alt={current.name} className="h-12 w-12 rounded object-contain" />
              : <div className="flex h-12 w-12 items-center justify-center rounded bg-muted/40 text-muted-foreground"><Building2 className="h-6 w-6" aria-hidden /></div>}
            <div>
              <div className="text-lg font-semibold">{current.name}</div>
              <div className="text-sm text-muted-foreground">
                {[current.short_name, current.type].filter(Boolean).join(" · ")}
                {current.roles?.length ? ` · ${current.roles.join(", ")}` : ""}
              </div>
            </div>
            <Button size="sm" variant="outline" className="ml-auto" onClick={() => void load()}>
              <RefreshCw className="h-4 w-4" aria-hidden /> Refresh
            </Button>
          </div>
          <div className="flex flex-wrap gap-2">
            {action("Add Match", <PlusCircle className="h-4 w-4" aria-hidden />, "/matches")}
            {action("Import Data", <DatabaseBackup className="h-4 w-4" aria-hidden />, "/manage/import")}
            {action("Research Centre", <ScrollText className="h-4 w-4" aria-hidden />, "/manage/research")}
            {action("Upload Media", <ImageIcon className="h-4 w-4" aria-hidden />, "/manage/media")}
            {action("Review Approvals", <FileCheck2 className="h-4 w-4" aria-hidden />, "/matches")}
            {action("Sync Now", <RefreshCw className="h-4 w-4" aria-hidden />, "/manage/autosync")}
          </div>
        </CardContent></Card>

        {data?.is_empty && (
          <Card><CardContent className="flex flex-col gap-2">
            <h3 className="text-sm font-semibold">Welcome — let's set up this workspace</h3>
            <p className="text-sm text-muted-foreground">
              This workspace is empty. A good order to start: add your organisation, set up a competition
              and season, then add or import matches. Historical records can be reconstructed in the
              Research Centre.
            </p>
            <div className="flex flex-wrap gap-2">
              {action("Organisations", <Building2 className="h-4 w-4" aria-hidden />, "/manage/organisations")}
              {action("Competitions", <Trophy className="h-4 w-4" aria-hidden />, "/manage/competitions")}
              {action("Import Data", <DatabaseBackup className="h-4 w-4" aria-hidden />, "/manage/import")}
            </div>
          </CardContent></Card>
        )}

        {/* live summary */}
        <Card><CardContent className="flex flex-col gap-3">
          <h3 className="text-sm font-semibold">Summary</h3>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {summary("Matches", t?.matches, <Trophy className="h-4 w-4" aria-hidden />, "/matches")}
            {summary("Players", t?.players, <Users className="h-4 w-4" aria-hidden />, "/people")}
            {summary("Approved scorecards", t?.approved_scorecards, <FileCheck2 className="h-4 w-4" aria-hidden />)}
            {summary("Seasons", t?.seasons, <ScrollText className="h-4 w-4" aria-hidden />)}
            {summary("Competitions", t?.competitions, <Trophy className="h-4 w-4" aria-hidden />, "/manage/competitions")}
            {summary("Organisations", t?.organisations, <Building2 className="h-4 w-4" aria-hidden />, "/manage/organisations")}
            {summary("Media assets", t?.media_assets, <ImageIcon className="h-4 w-4" aria-hidden />, "/manage/media")}
          </div>
        </CardContent></Card>

        {/* attention + research */}
        <div className="grid gap-4 md:grid-cols-2">
          <Card><CardContent className="flex flex-col gap-2">
            <h3 className="flex items-center gap-2 text-sm font-semibold">
              <AlertTriangle className="h-4 w-4 text-warning" aria-hidden /> Attention required
            </h3>
            {attentionItems.length === 0
              ? <p className="text-xs text-muted-foreground">Nothing needs attention right now.</p>
              : attentionItems.map((i) => (
                <button key={i.label} type="button" onClick={() => navigate(i.to)}
                  className="flex items-center gap-2 rounded-[var(--radius-app)] border border-border px-2 py-1.5 text-left text-sm hover:border-brand">
                  <Badge variant="warning">{i.n}</Badge>
                  <span>{i.label}</span>
                </button>
              ))}
          </CardContent></Card>

          <Card><CardContent className="flex flex-col gap-2">
            <h3 className="flex items-center gap-2 text-sm font-semibold">
              <ScrollText className="h-4 w-4 text-muted-foreground" aria-hidden /> Historical research
            </h3>
            <div className="grid grid-cols-2 gap-2 text-sm">
              {summary("Active projects", rs?.projects_active, null, "/manage/research")}
              {summary("Incomplete scorecards", rs?.incomplete_scorecards, null, "/manage/research")}
              {summary("Open research tasks", rs?.open_research_tasks, null, "/manage/research")}
              {summary("Sources", rs?.sources, null, "/manage/research")}
            </div>
          </CardContent></Card>
        </div>

        {/* recent activity */}
        <Card><CardContent className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold">Recent activity</h3>
          {(!data || data.recent_activity.length === 0)
            ? <p className="text-xs text-muted-foreground">No activity yet.</p>
            : data.recent_activity.map((a, idx) => (
              <div key={idx} className="flex items-center gap-2 text-sm">
                <Badge variant="muted">{a.category}</Badge>
                <span className="text-muted-foreground">{a.action}</span>
                <span className="ml-auto text-xs text-muted-foreground">
                  {a.at ? new Date(a.at).toLocaleString() : ""}
                </span>
              </div>
            ))}
        </CardContent></Card>

        <div className="flex items-center justify-end gap-2 text-xs text-muted-foreground">
          <Server className="h-3.5 w-3.5" aria-hidden /> OneStats API {version ? `v${version}` : "checking…"}
        </div>
      </div>
    </AppShell>
  );
}
