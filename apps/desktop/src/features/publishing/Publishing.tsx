/**
 * Website Publishing (Phase 15) — hosting-neutral. Publish a report (or a player profile) to a permanent
 * public URL backed by a durable snapshot: serve it from the built-in public edge (preview / future
 * central service) or download the static files for existing website hosting (e.g. the RMCC site's
 * External URL field). Publish / unpublish / revoke, auto-staleness after approved-stat changes, refresh,
 * and club branding. Admin only.
 */
import { Copy, Download, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AppShell } from "../../components/layout/AppShell";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import { Input } from "../../components/ui/input";
import { Select } from "../../components/ui/select";
import { api, ApiError, type Publication, type ReportCatalogue } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { canManage } from "../../lib/permissions";
import { useWorkspace } from "../../lib/workspace-context";

export function Publishing() {
  const { current } = useWorkspace();
  const { user } = useAuth();
  const admin = canManage(user, current);
  const [cat, setCat] = useState<ReportCatalogue | null>(null);
  const [pubs, setPubs] = useState<Publication[]>([]);
  const [reportId, setReportId] = useState("");
  const [title, setTitle] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!current) return;
    try {
      const [c, p] = await Promise.all([api.statsCatalogue(current.id), api.publicationsList(current.id)]);
      setCat(c); setPubs(p);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load publishing.");
    }
  }, [current]);
  useEffect(() => { void load(); }, [load]);

  const reports = useMemo(() => (cat?.categories ?? []).flatMap((c) => c.reports), [cat]);

  const publish = useCallback(async () => {
    if (!current || !reportId) return;
    setError(null); setMsg(null);
    const r = reports.find((x) => x.id === reportId);
    try {
      await api.publicationCreate(current.id, { kind: "report", report_id: reportId, title: title.trim() || r?.name || reportId });
      setMsg("Published. A permanent public URL was created."); setTitle(""); setReportId("");
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Publish failed.");
    }
  }, [current, reportId, title, reports, load]);

  const act = useCallback(async (fn: () => Promise<unknown>, ok: string) => {
    setError(null); setMsg(null);
    try { await fn(); setMsg(ok); await load(); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Action failed."); }
  }, [load]);

  const copy = (text: string) => { try { void navigator.clipboard.writeText(text); setMsg("Copied."); } catch { /* clipboard unavailable */ } };

  const download = useCallback(async (p: Publication) => {
    if (!current) return;
    try {
      const { files } = await api.publicationExport(current.id, p.id);
      for (const [name, content] of Object.entries(files)) {
        const blob = new Blob([content], { type: name.endsWith(".json") ? "application/json" : "text/html" });
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob); a.download = name; a.click();
        URL.revokeObjectURL(a.href);
      }
      setMsg("Static files downloaded — upload these to your website host.");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Export failed.");
    }
  }, [current]);

  if (!current) return <AppShell title="Website Publishing" subtitle="Select a workspace"><div /></AppShell>;
  if (!admin) return <AppShell title="Website Publishing" subtitle={current.name}><p className="text-sm text-muted-foreground">Publishing is available to workspace administrators.</p></AppShell>;

  const statusBadge = (s: string) => s === "published" ? <Badge variant="success">published</Badge>
    : s === "revoked" ? <Badge variant="danger">revoked</Badge> : <Badge variant="muted">unpublished</Badge>;

  return (
    <AppShell title="Website Publishing" subtitle={current.name}>
      <div className="mx-auto flex max-w-4xl flex-col gap-4">
        {error && <p className="rounded-[var(--radius-app)] border border-danger/40 bg-danger/5 px-3 py-2 text-sm text-danger">{error}</p>}
        {msg && <p className="text-xs text-success">{msg}</p>}

        <Card><CardContent className="flex flex-wrap items-center gap-2">
          <div className="text-sm"><span className="font-medium">Public records portal</span>
            <span className="ml-2 text-xs text-muted-foreground">a mobile-first page listing everything you publish</span></div>
          <Button size="sm" variant="outline" className="ml-auto"
            onClick={() => window.open(api.publicPreviewUrl(`/api/v1/public/club/${current.id}`), "_blank")}>
            Open portal
          </Button>
        </CardContent></Card>

        <Card><CardContent className="flex flex-col gap-3">
          <h3 className="text-sm font-semibold">Publish a report</h3>
          <p className="text-xs text-muted-foreground">Creates a permanent public URL backed by a snapshot (approved data only, club-branded). It keeps serving the last published snapshot even while this computer is offline.</p>
          <div className="flex flex-wrap items-end gap-2">
            <label className="flex flex-col gap-1 text-xs">Report
              <Select value={reportId} onChange={(e) => setReportId(e.target.value)} className="w-64">
                <option value="">— choose a report —</option>
                {(cat?.categories ?? []).map((c) => (
                  <optgroup key={c.category} label={c.category}>
                    {c.reports.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
                  </optgroup>
                ))}
              </Select>
            </label>
            <label className="flex flex-1 flex-col gap-1 text-xs">Public title (optional)
              <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Defaults to the report name" />
            </label>
            <Button size="sm" disabled={!reportId} onClick={() => void publish()}>Publish</Button>
          </div>
        </CardContent></Card>

        <Card><CardContent className="flex flex-col gap-2">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold">Published reports &amp; profiles</h3>
            <Button size="sm" variant="outline" className="ml-auto" onClick={() => void act(() => api.publicationRefreshAll(current.id), "All published snapshots refreshed.")}>
              <RefreshCw className="h-4 w-4" aria-hidden /> Refresh all
            </Button>
          </div>
          {pubs.length === 0 ? <p className="text-xs text-muted-foreground">Nothing published yet.</p> :
            <div className="flex flex-col divide-y divide-border">
              {pubs.map((p) => (
                <div key={p.id} className="flex flex-wrap items-center gap-2 py-2 text-sm">
                  <span className="font-medium">{p.title}</span>
                  <Badge variant="muted">{p.kind === "player_profile" ? "profile" : "report"}</Badge>
                  {statusBadge(p.status)}
                  {p.stale && <Badge variant="warning">needs refresh</Badge>}
                  <code className="truncate rounded bg-muted/40 px-1.5 py-0.5 text-xs text-muted-foreground">{p.public_path}</code>
                  <div className="ml-auto flex flex-wrap gap-1">
                    <Button size="sm" variant="ghost" onClick={() => copy(p.public_url || (p.public_path ?? ""))} aria-label="Copy URL"><Copy className="h-4 w-4" aria-hidden /></Button>
                    {p.public_path && <Button size="sm" variant="ghost" onClick={() => window.open(api.publicPreviewUrl(p.public_path!), "_blank")}>Preview</Button>}
                    <Button size="sm" variant="ghost" onClick={() => void download(p)} aria-label="Download static files"><Download className="h-4 w-4" aria-hidden /></Button>
                    {p.status === "published"
                      ? <Button size="sm" variant="ghost" onClick={() => void act(() => api.publicationRefresh(current.id, p.id), "Snapshot refreshed.")}>Refresh</Button>
                      : <Button size="sm" variant="ghost" onClick={() => void act(() => api.publicationSetStatus(current.id, p.id, "published"), "Re-published.")}>Publish</Button>}
                    {p.status === "published" && <Button size="sm" variant="ghost" onClick={() => void act(() => api.publicationSetStatus(current.id, p.id, "unpublished"), "Unpublished.")}>Unpublish</Button>}
                    {p.status !== "revoked" && <Button size="sm" variant="ghost" onClick={() => void act(() => api.publicationSetStatus(current.id, p.id, "revoked"), "Revoked — the URL no longer resolves.")}>Revoke</Button>}
                  </div>
                </div>
              ))}
            </div>}
          <p className="text-xs text-muted-foreground">Download gives you a self-contained HTML + JSON pair to upload to existing website hosting (e.g. the club site's External URL field). Public serving never exposes the database.</p>
        </CardContent></Card>
      </div>
    </AppShell>
  );
}
