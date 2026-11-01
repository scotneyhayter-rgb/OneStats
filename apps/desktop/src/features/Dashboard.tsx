/**
 * Workspace Dashboard — the home command centre, as ONE shared, role-adaptive architecture.
 *
 * A single dashboard composed from reusable sections (features/dashboard/parts): identity + quick
 * actions, a role-filtered "My Tasks" list, a live summary, historical-research progress and recent
 * activity. What each user sees is driven by their permissions in the CURRENTLY selected workspace
 * (a viewer sees read-only summaries; an editor sees drafts; a verifier sees approvals; an admin
 * sees everything) — not six separate UIs. All figures come from the backend (member-gated,
 * role-aware on the server) and nothing is fabricated; empty workspaces get onboarding guidance.
 */
import {
  Building2, DatabaseBackup, FileCheck2, Image as ImageIcon, ListChecks, PlusCircle,
  RefreshCw, ScrollText, Server, Trophy, Users,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AppShell } from "../components/layout/AppShell";
import { Button } from "../components/ui/button";
import { Card, CardContent } from "../components/ui/card";
import { api, ApiError, type WorkspaceDashboard } from "../lib/api";
import { useWorkspace } from "../lib/workspace-context";
import { useAuth } from "../lib/auth";
import { can, roleLabels } from "../lib/permissions";
import { ActivityList, MyTasks, QuickActionBar, SectionCard, StatGrid, StatTile, type QuickAction } from "./dashboard/parts";
import { deriveMyTasks } from "./dashboard/tasks";

export function Dashboard() {
  const { current } = useWorkspace();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [data, setData] = useState<WorkspaceDashboard | null>(null);
  const [logo, setLogo] = useState<string | null>(null);
  const [version, setVersion] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const has = useCallback((perm: string) => can(user, current, perm), [user, current]);

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

  const tasks = useMemo(() => deriveMyTasks(data, has), [data, has]);

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
  const rs = data?.research;
  const open = (to: string) => navigate(to);

  const quickActions: QuickAction[] = [
    { label: "Add Match", icon: <PlusCircle className="h-4 w-4" aria-hidden />, to: "/matches", perm: "match.manage" },
    { label: "Import Data", icon: <DatabaseBackup className="h-4 w-4" aria-hidden />, to: "/manage/import", perm: "import.manage" },
    { label: "Research Centre", icon: <ScrollText className="h-4 w-4" aria-hidden />, to: "/manage/research", perm: "research.manage" },
    { label: "Upload Media", icon: <ImageIcon className="h-4 w-4" aria-hidden />, to: "/manage/media", perm: "media.manage" },
    { label: "Review Approvals", icon: <FileCheck2 className="h-4 w-4" aria-hidden />, to: "/matches", perm: "scorecard.approve" },
    { label: "Sync Now", icon: <RefreshCw className="h-4 w-4" aria-hidden />, to: "/manage/autosync", perm: "import.manage" },
  ];

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
                {current.roles?.length ? ` · ${roleLabels(current.roles)}` : ""}
              </div>
            </div>
            <Button size="sm" variant="outline" className="ml-auto" onClick={() => void load()}>
              <RefreshCw className="h-4 w-4" aria-hidden /> Refresh
            </Button>
          </div>
          <QuickActionBar actions={quickActions} has={has} onOpen={open} />
        </CardContent></Card>

        {data?.is_empty && (
          <Card><CardContent className="flex flex-col gap-2">
            <h3 className="text-sm font-semibold">Welcome — let's set up this workspace</h3>
            <p className="text-sm text-muted-foreground">
              This workspace is empty. A good order to start: add your organisation, set up a competition
              and season, then add or import matches. Historical records can be reconstructed in the
              Research Centre.
            </p>
            <QuickActionBar
              has={has}
              onOpen={open}
              actions={[
                { label: "Organisations", icon: <Building2 className="h-4 w-4" aria-hidden />, to: "/manage/organisations", perm: "organisation.manage" },
                { label: "Competitions", icon: <Trophy className="h-4 w-4" aria-hidden />, to: "/manage/competitions", perm: "competition.manage" },
                { label: "Import Data", icon: <DatabaseBackup className="h-4 w-4" aria-hidden />, to: "/manage/import", perm: "import.manage" },
              ]}
            />
          </CardContent></Card>
        )}

        {/* My Tasks — role-filtered, only shown when the user has an actionable role */}
        {tasks.length > 0 && (
          <SectionCard title="My Tasks" icon={<ListChecks className="h-4 w-4 text-muted-foreground" aria-hidden />}>
            <MyTasks tasks={tasks} onOpen={open} />
          </SectionCard>
        )}

        {/* live summary — figures from the authoritative backend */}
        <SectionCard title="Summary">
          <StatGrid>
            <StatTile label="Matches" value={t?.matches} icon={<Trophy className="h-4 w-4" aria-hidden />} onClick={() => open("/matches")} />
            <StatTile label="Players" value={t?.players} icon={<Users className="h-4 w-4" aria-hidden />} onClick={() => open("/people")} />
            <StatTile label="Approved scorecards" value={t?.approved_scorecards} icon={<FileCheck2 className="h-4 w-4" aria-hidden />} />
            <StatTile label="Seasons" value={t?.seasons} icon={<ScrollText className="h-4 w-4" aria-hidden />} />
            <StatTile label="Competitions" value={t?.competitions} icon={<Trophy className="h-4 w-4" aria-hidden />} onClick={has("competition.manage") ? () => open("/manage/competitions") : undefined} />
            <StatTile label="Organisations" value={t?.organisations} icon={<Building2 className="h-4 w-4" aria-hidden />} onClick={has("organisation.manage") ? () => open("/manage/organisations") : undefined} />
            <StatTile label="Media assets" value={t?.media_assets} icon={<ImageIcon className="h-4 w-4" aria-hidden />} onClick={has("media.manage") ? () => open("/manage/media") : undefined} />
          </StatGrid>
        </SectionCard>

        {/* historical research progress — shown to roles that work with research */}
        {has("research.manage") && (
          <SectionCard title="Historical research" icon={<ScrollText className="h-4 w-4 text-muted-foreground" aria-hidden />}>
            <div className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
              <StatTile label="Active projects" value={rs?.projects_active} onClick={() => open("/manage/research")} />
              <StatTile label="Incomplete scorecards" value={rs?.incomplete_scorecards} onClick={() => open("/manage/research")} />
              <StatTile label="Open research tasks" value={rs?.open_research_tasks} onClick={() => open("/manage/research")} />
              <StatTile label="Sources" value={rs?.sources} onClick={() => open("/manage/research")} />
            </div>
          </SectionCard>
        )}

        {/* recent activity */}
        <SectionCard title="Recent activity">
          <ActivityList items={data?.recent_activity ?? []} />
        </SectionCard>

        <div className="flex items-center justify-end gap-2 text-xs text-muted-foreground">
          <Server className="h-3.5 w-3.5" aria-hidden /> OneStats API {version ? `v${version}` : "checking…"}
        </div>
      </div>
    </AppShell>
  );
}
