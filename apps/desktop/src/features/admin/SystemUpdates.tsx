import { AlertTriangle, CheckCircle2, ClipboardCheck, Database, HardDrive, Loader2, Play, RefreshCw, ShieldAlert, XCircle } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { AppShell } from "../../components/layout/AppShell";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import { Modal } from "../../components/ui/dialog";
import { EmptyState } from "../../components/states/States";
import { api, ApiError, type PreCheckResult, type SystemUpdateStatus } from "../../lib/api";
import { useAuth } from "../../lib/auth";

function fmtBytes(n: number | null): string {
  if (n == null) return "unknown";
  const gb = n / 1_000_000_000;
  return gb >= 1 ? `${gb.toFixed(1)} GB free` : `${Math.round(n / 1_000_000)} MB free`;
}

export function SystemUpdates() {
  const { user } = useAuth();
  const [status, setStatus] = useState<SystemUpdateStatus | null>(null);
  const [pre, setPre] = useState<PreCheckResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [maintModal, setMaintModal] = useState<null | "on" | "off">(null);
  const [maintMessage, setMaintMessage] = useState("OneStats is being updated. Please try again shortly.");

  const load = useCallback(async () => {
    setErr(null);
    try { setStatus(await api.systemUpdateStatus()); }
    catch (e) { setErr(e instanceof ApiError ? e.message : "Could not load system update status."); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const runPreCheck = async () => {
    setBusy("pre"); setErr(null); setMsg(null);
    try { setPre(await api.systemUpdatePreCheck()); await load(); }
    catch (e) { setErr(e instanceof ApiError ? e.message : "Pre-update checks failed to run."); }
    finally { setBusy(null); }
  };

  const setMaintenance = async (on: boolean) => {
    setBusy("maint"); setErr(null); setMsg(null);
    try {
      await api.systemUpdateMaintenance(on, on ? maintMessage : undefined);
      setMsg(on ? "Maintenance mode ON — new writes are blocked." : "Maintenance mode OFF — normal operation resumed.");
      setMaintModal(null); await load();
    } catch (e) { setErr(e instanceof ApiError ? e.message : "Could not change maintenance mode."); }
    finally { setBusy(null); }
  };

  if (!user?.is_super_admin) {
    return (
      <AppShell title="System Updates" subtitle="Server & database update management">
        <EmptyState title="Super Administrator required" description="Only a Super Admin can manage server updates." />
      </AppShell>
    );
  }

  const db = status?.database;
  return (
    <AppShell title="System Updates" subtitle="Server, database & release management (Super Admin)">
      <div className="mx-auto flex max-w-4xl flex-col gap-4">
        {err && <div className="rounded-[var(--radius-app)] border border-danger/40 bg-danger/10 p-2 text-xs text-danger">{err}</div>}
        {msg && <div className="rounded-[var(--radius-app)] border border-success/40 bg-success/10 p-2 text-xs text-success">{msg}</div>}

        {loading ? (
          <p className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> Loading…</p>
        ) : status ? (
          <>
            {/* Scope notice */}
            <div className="flex items-start gap-2 rounded-[var(--radius-app)] border border-warning/40 bg-warning/10 p-3 text-xs text-warning">
              <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" />
              <div>A server update affects <b>every workspace</b> on this installation. Take a verified backup and use a maintenance window.</div>
            </div>

            {/* Installed versions */}
            <Card><CardContent className="flex flex-col gap-3">
              <h3 className="text-sm font-semibold">Installed</h3>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <Tile label="Server" value={status.server_version} />
                <Tile label="API" value={`v${status.api_version}`} />
                <Tile label="Channel" value={status.channel} />
                <Tile label="DB schema" value={db ? String(db.current_level ?? "?") : "?"}
                  tone={db && !db.up_to_date ? "warn" : "ok"} />
              </div>
              {db && !db.up_to_date && (
                <p className="flex items-center gap-1.5 text-xs text-warning">
                  <AlertTriangle className="h-3.5 w-3.5" /> Database migration pending — code expects schema {db.expected_level} ({db.expected_head}), database is at {db.current_head}.
                </p>
              )}
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <HardDrive className="h-3.5 w-3.5" /> Backup destination: {status.backup.writable ? "ready" : "NOT writable"} · {fmtBytes(status.backup.free_bytes)}
              </div>
              <div className="text-xs text-muted-foreground">
                Release service: {status.release_service.configured ? status.release_service.manifest_url : "not configured (installer-based updates)"}
              </div>
            </CardContent></Card>

            {/* Actions */}
            <Card><CardContent className="flex flex-col gap-3">
              <h3 className="text-sm font-semibold">Server update controls</h3>
              <div className="flex flex-wrap gap-2">
                <Button variant="outline" onClick={() => void load()}><RefreshCw className="h-4 w-4" /> Refresh</Button>
                <Button variant="outline" onClick={() => void runPreCheck()} disabled={busy === "pre"}>
                  {busy === "pre" ? <Loader2 className="h-4 w-4 animate-spin" /> : <ClipboardCheck className="h-4 w-4" />} Run pre-update checks
                </Button>
                {status.maintenance.mode ? (
                  <Button onClick={() => setMaintModal("off")} disabled={busy === "maint"}>Exit maintenance mode</Button>
                ) : (
                  <Button variant="outline" onClick={() => setMaintModal("on")} disabled={busy === "maint"}>Enter maintenance mode</Button>
                )}
                <Button disabled title="Requires a signed release + privileged maintenance service (deferred)">
                  <Play className="h-4 w-4" /> Begin server update
                </Button>
              </div>
              {status.maintenance.mode && (
                <p className="flex items-center gap-1.5 text-xs text-warning"><AlertTriangle className="h-3.5 w-3.5" /> Maintenance mode is ON — new writes are blocked. {status.maintenance.message}</p>
              )}
              <p className="text-[11px] text-muted-foreground">
                Applying a verified update package and database migrations runs through a privileged
                maintenance service outside the app, and is enabled once a signed release is configured.
              </p>
            </CardContent></Card>

            {/* Pre-check results */}
            {pre && (
              <Card><CardContent className="flex flex-col gap-2">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold">Pre-update checks</h3>
                  <Badge variant={pre.ready ? "success" : "danger"}>{pre.ready ? "Ready" : "Not ready"}</Badge>
                </div>
                <ul className="flex flex-col gap-1">
                  {pre.checks.map((c) => (
                    <li key={c.name} className="flex items-center gap-2 text-xs">
                      {c.ok ? <CheckCircle2 className="h-4 w-4 text-success" /> : <XCircle className="h-4 w-4 text-danger" />}
                      <span className="font-medium">{c.name.replace(/_/g, " ")}</span>
                      <span className="text-muted-foreground">— {c.detail}</span>
                      {!c.critical && <Badge variant="muted" className="ml-1">advisory</Badge>}
                    </li>
                  ))}
                </ul>
              </CardContent></Card>
            )}

            {/* History */}
            <Card><CardContent className="flex flex-col gap-2">
              <h3 className="flex items-center gap-2 text-sm font-semibold"><Database className="h-4 w-4 text-brand" /> Update history</h3>
              {status.recent_events.length === 0 ? (
                <p className="text-xs text-muted-foreground">No update events recorded yet.</p>
              ) : (
                <div className="overflow-hidden rounded-[var(--radius-app)] border border-border">
                  <table className="w-full text-xs">
                    <thead><tr className="bg-muted text-left text-muted-foreground">
                      <th className="px-2 py-1">When</th><th className="px-2 py-1">Component</th><th className="px-2 py-1">Event</th><th className="px-2 py-1">Outcome</th>
                    </tr></thead>
                    <tbody>
                      {status.recent_events.map((e, i) => (
                        <tr key={i} className="border-t border-border">
                          <td className="px-2 py-1">{new Date(e.at).toLocaleString()}</td>
                          <td className="px-2 py-1">{e.component}</td>
                          <td className="px-2 py-1">{e.event.replace(/_/g, " ")}</td>
                          <td className="px-2 py-1">{e.outcome === "error" ? <span className="text-danger">error</span> : e.outcome ?? "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent></Card>
          </>
        ) : null}
      </div>

      {/* Maintenance confirm */}
      <Modal open={maintModal !== null} title={maintModal === "on" ? "Enter maintenance mode" : "Exit maintenance mode"} onClose={() => setMaintModal(null)}>
        <div className="flex flex-col gap-4">
          {maintModal === "on" ? (
            <>
              <p className="text-sm text-muted-foreground">New writes (scorecards, edits, uploads) will be blocked across all workspaces until you exit. Reads stay available.</p>
              <label className="flex flex-col gap-1 text-sm">
                <span className="font-medium">Message shown to users</span>
                <input className="rounded-[var(--radius-app)] border border-border bg-card px-2 py-1 text-sm"
                  value={maintMessage} onChange={(e) => setMaintMessage(e.target.value)} maxLength={300} />
              </label>
            </>
          ) : (
            <p className="text-sm text-muted-foreground">Resume normal operation and allow writes again?</p>
          )}
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setMaintModal(null)}>Cancel</Button>
            <Button onClick={() => void setMaintenance(maintModal === "on")} disabled={busy === "maint"}>
              {busy === "maint" ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              {maintModal === "on" ? "Enter maintenance mode" : "Exit maintenance mode"}
            </Button>
          </div>
        </div>
      </Modal>
    </AppShell>
  );
}

function Tile({ label, value, tone }: { label: string; value: string; tone?: "ok" | "warn" }) {
  return (
    <div className="rounded-[var(--radius-app)] border border-border bg-card p-2">
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className={`text-sm font-semibold ${tone === "warn" ? "text-warning" : "text-card-foreground"}`}>{value}</div>
    </div>
  );
}
