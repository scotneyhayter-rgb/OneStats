/**
 * Platform ("All Workspaces") dashboard — Super Administrator only.
 *
 * A real, database-backed cross-workspace overview: platform summary, a sortable
 * organisation-comparison table, system health and recent platform (account) activity. Every
 * figure comes from the backend `/platform/dashboard` (Super-Admin-gated server-side). Cross-
 * workspace totals are WORKSPACE RECORD counts — the same match or player can appear in more than
 * one workspace — and are labelled as such, never presented as global-unique figures.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Activity, ArrowUpDown, Building2, Database, RefreshCw, ShieldCheck, Users } from "lucide-react";
import { AppShell } from "../../components/layout/AppShell";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import { EmptyState, LoadingState } from "../../components/states/States";
import { api, ApiError, type PlatformDashboard as PD, type PlatformOrgRow } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { useWorkspace } from "../../lib/workspace-context";

type SortKey = keyof Pick<PlatformOrgRow, "name" | "type" | "status" | "matches" | "players" | "approved_scorecards" | "awaiting_approval" | "seasons" | "members">;

const NUM_COLS: { key: SortKey; label: string }[] = [
  { key: "matches", label: "Matches" },
  { key: "players", label: "Players" },
  { key: "approved_scorecards", label: "Approved" },
  { key: "awaiting_approval", label: "Awaiting" },
  { key: "seasons", label: "Seasons" },
  { key: "members", label: "Members" },
];

export function PlatformDashboard() {
  const { user } = useAuth();
  const { setCurrent } = useWorkspace();
  const navigate = useNavigate();
  const [data, setData] = useState<PD | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [sort, setSort] = useState<{ key: SortKey; dir: "asc" | "desc" }>({ key: "matches", dir: "desc" });

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await api.platformDashboard());
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load the platform dashboard.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const rows = useMemo(() => {
    const list = [...(data?.organisations ?? [])];
    const { key, dir } = sort;
    list.sort((a, b) => {
      const av = a[key], bv = b[key];
      const cmp = typeof av === "number" && typeof bv === "number"
        ? av - bv
        : String(av).localeCompare(String(bv));
      return dir === "asc" ? cmp : -cmp;
    });
    return list;
  }, [data, sort]);

  const toggleSort = (key: SortKey) =>
    setSort((s) => (s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: key === "name" ? "asc" : "desc" }));

  const openWorkspace = (id: string) => { setCurrent(id); navigate("/dashboard"); };

  if (!user?.is_super_admin) {
    return (
      <AppShell title="All Workspaces" subtitle="Platform overview">
        <EmptyState title="Super Administrator only" description="This platform overview is available to Super Administrators." />
      </AppShell>
    );
  }

  const s = data?.summary;
  const h = data?.system_health;

  const stat = (label: string, n: number | undefined, icon: React.ReactNode) => (
    <div className="flex flex-col gap-1 rounded-[var(--radius-app)] border border-border p-3">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">{icon}{label}</div>
      <div className="text-2xl font-semibold tabular-nums">{n ?? "—"}</div>
    </div>
  );

  return (
    <AppShell title="All Workspaces" subtitle="Platform overview — Super Administrator">
      <div className="mx-auto flex max-w-6xl flex-col gap-4">
        {error && <p className="rounded-[var(--radius-app)] border border-danger/40 bg-danger/5 px-3 py-2 text-sm text-danger">{error}</p>}

        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            A consolidated, read-only view across every workspace on this platform.
          </p>
          <Button size="sm" variant="outline" onClick={() => void load()}>
            <RefreshCw className="h-4 w-4" aria-hidden /> Refresh
          </Button>
        </div>

        {loading ? (
          <LoadingState label="Loading platform overview…" />
        ) : data?.is_empty ? (
          <EmptyState title="No workspaces yet" description="Create the first workspace to see the platform overview." />
        ) : (
          <>
            {/* platform summary */}
            <Card><CardContent className="flex flex-col gap-3">
              <h3 className="text-sm font-semibold">Platform summary</h3>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
                {stat("Workspaces", s?.workspaces, <Building2 className="h-4 w-4" aria-hidden />)}
                {stat("Active workspaces", s?.active_workspaces, <Building2 className="h-4 w-4" aria-hidden />)}
                {stat("Users", s?.users_total, <Users className="h-4 w-4" aria-hidden />)}
                {stat("Super Admins", s?.super_admins, <ShieldCheck className="h-4 w-4" aria-hidden />)}
                {stat("Workspace match records", s?.workspace_match_records, <Database className="h-4 w-4" aria-hidden />)}
                {stat("Workspace player records", s?.workspace_player_records, <Database className="h-4 w-4" aria-hidden />)}
                {stat("Approved scorecards", s?.workspace_approved_scorecards, <Database className="h-4 w-4" aria-hidden />)}
                {stat("Awaiting approval", s?.workspace_awaiting_approval, <Database className="h-4 w-4" aria-hidden />)}
              </div>
              <p className="text-xs text-muted-foreground">
                Totals are <b>workspace record counts</b>. The same match or player can exist in more than one
                workspace, so these are not global-unique figures.
              </p>
            </CardContent></Card>

            {/* organisation comparison */}
            <Card><CardContent className="flex flex-col gap-2">
              <h3 className="text-sm font-semibold">Organisation comparison</h3>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[720px] text-sm">
                  <thead>
                    <tr className="border-b border-border text-left text-xs text-muted-foreground">
                      <th className="py-2 pr-3">
                        <button type="button" onClick={() => toggleSort("name")} className="inline-flex items-center gap-1 hover:text-foreground">
                          Organisation <ArrowUpDown className="h-3 w-3" aria-hidden />
                        </button>
                      </th>
                      <th className="py-2 pr-3">
                        <button type="button" onClick={() => toggleSort("type")} className="inline-flex items-center gap-1 hover:text-foreground">
                          Type <ArrowUpDown className="h-3 w-3" aria-hidden />
                        </button>
                      </th>
                      {NUM_COLS.map((c) => (
                        <th key={c.key} className="py-2 pr-3 text-right">
                          <button type="button" onClick={() => toggleSort(c.key)} className="inline-flex items-center gap-1 hover:text-foreground">
                            {c.label} <ArrowUpDown className="h-3 w-3" aria-hidden />
                          </button>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr key={r.workspace_id} className="border-b border-border/60 hover:bg-muted/30">
                        <td className="py-2 pr-3">
                          <button type="button" onClick={() => openWorkspace(r.workspace_id)} className="text-left font-medium hover:text-brand hover:underline">
                            {r.name}
                          </button>
                          {r.status !== "active" && <Badge variant="muted" className="ml-2">{r.status}</Badge>}
                        </td>
                        <td className="py-2 pr-3 text-muted-foreground">{r.type}</td>
                        <td className="py-2 pr-3 text-right tabular-nums">{r.matches}</td>
                        <td className="py-2 pr-3 text-right tabular-nums">{r.players}</td>
                        <td className="py-2 pr-3 text-right tabular-nums">{r.approved_scorecards}</td>
                        <td className="py-2 pr-3 text-right tabular-nums">{r.awaiting_approval}</td>
                        <td className="py-2 pr-3 text-right tabular-nums">{r.seasons}</td>
                        <td className="py-2 pr-3 text-right tabular-nums">{r.members}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="text-xs text-muted-foreground">Select an organisation to manage it.</p>
            </CardContent></Card>

            {/* system health + activity */}
            <div className="grid gap-4 md:grid-cols-2">
              <Card><CardContent className="flex flex-col gap-2">
                <h3 className="flex items-center gap-2 text-sm font-semibold">
                  <Activity className="h-4 w-4 text-muted-foreground" aria-hidden /> System health
                </h3>
                <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
                  <dt className="text-muted-foreground">Database</dt>
                  <dd>{h?.database_connected ? <Badge variant="success">Connected</Badge> : <Badge variant="danger">Down</Badge>}</dd>
                  <dt className="text-muted-foreground">Maintenance mode</dt>
                  <dd>{h?.maintenance_mode ? <Badge variant="warning">On</Badge> : <Badge variant="muted">Off</Badge>}</dd>
                  <dt className="text-muted-foreground">Active sessions</dt>
                  <dd className="tabular-nums">{h?.active_sessions ?? "—"}</dd>
                  <dt className="text-muted-foreground">Super Admins</dt>
                  <dd className="tabular-nums">{h?.super_admins ?? "—"}</dd>
                  <dt className="text-muted-foreground">Version</dt>
                  <dd>{h?.version ? `v${h.version} (${h.env})` : "—"}</dd>
                </dl>
              </CardContent></Card>

              <Card><CardContent className="flex flex-col gap-2">
                <h3 className="text-sm font-semibold">Platform activity</h3>
                {(data?.platform_activity.length ?? 0) === 0
                  ? <p className="text-xs text-muted-foreground">No recent account activity.</p>
                  : data?.platform_activity.map((a, i) => (
                    <div key={i} className="flex items-center gap-2 text-sm">
                      <Badge variant="muted">{a.action}</Badge>
                      <span className="ml-auto text-xs text-muted-foreground">{a.at ? new Date(a.at).toLocaleString() : ""}</span>
                    </div>
                  ))}
              </CardContent></Card>
            </div>
          </>
        )}
      </div>
    </AppShell>
  );
}
