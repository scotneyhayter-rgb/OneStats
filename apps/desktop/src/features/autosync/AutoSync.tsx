/**
 * OneStats AutoSync (Phase 9) — automatic match discovery dashboard + review.
 *
 * Shows real AutoSync status from the database, configured sources (enable/disable), a Sync Now that
 * runs a real job, the discovery review queue (accept → import as draft, reject, bulk), and historical
 * coverage. Imported matches are drafts; Phase 7 approval still governs official statistics. No
 * fabricated counts — everything is read from the backend.
 */
import { CheckCircle2, PlayCircle, RefreshCw, XCircle } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { AppShell } from "../../components/layout/AppShell";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import { Select } from "../../components/ui/select";
import {
  api,
  ApiError,
  type AutoSyncConnector,
  type AutoSyncDashboard,
  type DiscoveryCoverage,
  type DiscoveryItem,
  type SyncSource,
} from "../../lib/api";
import { NoWorkspace, useManage } from "../manage/_shared";

const CLASS_VARIANT: Record<string, "brand" | "warning" | "muted" | "success" | "outline"> = {
  new: "brand", possible_duplicate: "warning", additional_evidence: "success",
  existing: "muted", insufficient: "outline", conflicting: "warning",
};

export function AutoSync() {
  const { workspaceId } = useManage();
  const [dash, setDash] = useState<AutoSyncDashboard | null>(null);
  const [sources, setSources] = useState<SyncSource[]>([]);
  const [connectors, setConnectors] = useState<AutoSyncConnector[]>([]);
  const [items, setItems] = useState<DiscoveryItem[]>([]);
  const [coverage, setCoverage] = useState<DiscoveryCoverage[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!workspaceId) return;
    try {
      const [d, s, c, i, cov] = await Promise.all([
        api.autosyncDashboard(workspaceId), api.autosyncSources(workspaceId),
        api.autosyncConnectors(workspaceId), api.autosyncReview(workspaceId), api.autosyncCoverage(workspaceId),
      ]);
      setDash(d); setSources(s); setConnectors(c); setItems(i); setCoverage(cov); setSelected(new Set());
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load AutoSync.");
    }
  }, [workspaceId]);
  useEffect(() => { void load(); }, [load]);

  if (!workspaceId) return <NoWorkspace />;

  const act = async (fn: () => Promise<unknown>, msg: string) => {
    setBusy(true); setError(null); setFlash(null);
    try { await fn(); setFlash(msg); await load(); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Action failed."); }
    finally { setBusy(false); }
  };

  const syncNow = (source_system: string) =>
    act(() => api.autosyncSyncNow(workspaceId, { source_system, kind: "manual" }), "Sync run.");
  const checkUpdates = (source_system: string) =>
    act(() => api.autosyncSyncNow(workspaceId, { source_system, kind: "updated" }), "Checked for scorecard updates.");
  const toggle = (id: string) => setSelected((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const bulk = (action: "accept" | "reject") =>
    act(() => api.autosyncBulk(workspaceId, { item_ids: [...selected], action }), `Bulk ${action} done.`);

  const stat = (label: string, n: number | string) => (
    <div className="rounded-[var(--radius-app)] border border-border p-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="text-xl font-semibold tabular-nums">{n}</div>
    </div>
  );

  return (
    <AppShell title="AutoSync" subtitle="Automatic match discovery and synchronisation">
      <div className="mx-auto flex max-w-5xl flex-col gap-4">
        {error && <p className="rounded-[var(--radius-app)] border border-danger/40 bg-danger/5 px-3 py-2 text-sm text-danger">{error}</p>}
        {flash && <p className="rounded-[var(--radius-app)] border border-success/40 bg-success/5 px-3 py-2 text-sm text-success">{flash}</p>}

        {/* dashboard */}
        <Card><CardContent className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold">Status</h3>
            <Button size="sm" variant="outline" disabled={busy} onClick={() => void load()}><RefreshCw className="h-4 w-4" aria-hidden /> Refresh</Button>
          </div>
          {dash && (
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {stat("Enabled sources", dash.sources)}
              {stat("Awaiting review", dash.pending_review)}
              {stat("New matches", dash.new_matches)}
              {stat("Possible duplicates", dash.possible_duplicates)}
              {stat("Updated scorecards", dash.updated_scorecards)}
              {stat("Jobs running", dash.jobs_running)}
              {stat("Jobs failed", dash.jobs_failed)}
              {stat("Last success", dash.last_success_at ? new Date(dash.last_success_at).toLocaleString() : "—")}
            </div>
          )}
        </CardContent></Card>

        {/* sources */}
        <Card><CardContent className="flex flex-col gap-3">
          <h3 className="text-sm font-semibold">Sources</h3>
          {sources.length === 0 && <p className="text-xs text-muted-foreground">No sources configured yet. Add one from an available connector.</p>}
          {sources.map((s) => (
            <div key={s.id} className="flex flex-wrap items-center gap-2 text-sm">
              <Badge variant={s.enabled ? "success" : "muted"}>{s.enabled ? "on" : "off"}</Badge>
              <span className="font-medium">{s.name}</span>
              <span className="text-xs text-muted-foreground">{s.connector_id} · {s.reliability}</span>
              <div className="ml-auto flex gap-1">
                <Button size="sm" disabled={busy || !s.enabled} onClick={() => void syncNow(s.connector_id)}><PlayCircle className="h-4 w-4" aria-hidden /> Sync Now</Button>
                <Button size="sm" variant="outline" disabled={busy || !s.enabled} onClick={() => void checkUpdates(s.connector_id)}>Check updates</Button>
                <Button size="sm" variant="outline" disabled={busy} onClick={() => void act(() => api.autosyncSetSourceEnabled(workspaceId, s.id, !s.enabled), "Source updated.")}>{s.enabled ? "Disable" : "Enable"}</Button>
              </div>
            </div>
          ))}
          <AddSource connectors={connectors} busy={busy} onAdd={(body) => act(() => api.autosyncAddSource(workspaceId, body), "Source added.")} />
        </CardContent></Card>

        {/* review queue */}
        <Card><CardContent className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold">Review queue ({items.length})</h3>
            {selected.size > 0 && (
              <div className="flex gap-1">
                <Button size="sm" disabled={busy} onClick={() => void bulk("accept")}>Accept {selected.size}</Button>
                <Button size="sm" variant="outline" disabled={busy} onClick={() => void bulk("reject")}>Reject {selected.size}</Button>
              </div>
            )}
          </div>
          {items.length === 0 && <p className="text-xs text-muted-foreground">Nothing awaiting review.</p>}
          {items.map((it) => {
            const m = (it.candidate?.match ?? {}) as Record<string, unknown>;
            return (
              <div key={it.id} className="flex flex-wrap items-center gap-2 border-t border-border pt-2 text-sm first:border-0 first:pt-0">
                <input type="checkbox" aria-label={`Select ${it.source_ref}`} checked={selected.has(it.id)} onChange={() => toggle(it.id)} />
                <Badge variant={CLASS_VARIANT[it.classification] ?? "outline"}>{it.classification.replace(/_/g, " ")}</Badge>
                <span>{String((it.candidate as Record<string, unknown>)?.home_team_name ?? "?")} v {String((it.candidate as Record<string, unknown>)?.away_team_name ?? "?")}</span>
                <span className="text-xs text-muted-foreground">{String(m.match_date ?? "")} · {it.source_system}{it.kind === "updated_scorecard" ? " · update" : ""}</span>
                <div className="ml-auto flex gap-1">
                  <Button size="sm" disabled={busy} onClick={() => void act(() => api.autosyncAccept(workspaceId, it.id), "Accepted — imported as draft.")}><CheckCircle2 className="h-4 w-4" aria-hidden /> Accept</Button>
                  <Button size="sm" variant="outline" disabled={busy} onClick={() => void act(() => api.autosyncReject(workspaceId, it.id), "Rejected.")}><XCircle className="h-4 w-4" aria-hidden /> Reject</Button>
                </div>
              </div>
            );
          })}
          <p className="text-[11px] text-muted-foreground">Accepting imports a <strong>draft</strong> match — review and approve it before it counts towards official statistics.</p>
        </CardContent></Card>

        {/* coverage */}
        {coverage.length > 0 && (
          <Card><CardContent className="flex flex-col gap-2">
            <h3 className="text-sm font-semibold">Historical coverage</h3>
            <div className="flex flex-wrap gap-2 text-xs">
              {coverage.map((c) => (
                <Badge key={c.id} variant={c.status === "searched" ? "success" : c.status === "failed" ? "warning" : "outline"}>
                  {c.scope_key}: {c.status} ({c.matches_found})
                </Badge>
              ))}
            </div>
          </CardContent></Card>
        )}
      </div>
    </AppShell>
  );
}

function AddSource({ connectors, busy, onAdd }: {
  connectors: AutoSyncConnector[]; busy: boolean; onAdd: (b: Record<string, unknown>) => Promise<void>;
}) {
  const [connectorId, setConnectorId] = useState("");
  const [name, setName] = useState("");
  const chosen = connectors.find((c) => c.connector_id === connectorId);
  return (
    <div className="mt-2 flex flex-wrap items-end gap-2 border-t border-border pt-3">
      <label className="flex flex-col gap-1 text-xs">Connector
        <Select value={connectorId} disabled={busy} onChange={(e) => setConnectorId(e.target.value)} className="w-64">
          <option value="">— choose —</option>
          {connectors.map((c) => <option key={c.connector_id} value={c.connector_id}>{c.provider} ({c.status})</option>)}
        </Select>
      </label>
      <label className="flex flex-col gap-1 text-xs">Name
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Our league"
          className="h-8 w-48 rounded-[var(--radius-app)] border border-border bg-card px-2 text-sm" />
      </label>
      <Button size="sm" disabled={busy || !connectorId || !name.trim()}
        onClick={() => void onAdd({ connector_id: connectorId, name: name.trim(), provider: chosen?.provider,
          access_method: chosen?.access_method, auth_required: chosen?.auth_required })}>Add source</Button>
      {chosen?.status === "interface_only" && (
        <p className="w-full text-[11px] text-warning">This provider's connector isn't implemented yet (awaiting verified access): {chosen.notes}</p>
      )}
    </div>
  );
}
