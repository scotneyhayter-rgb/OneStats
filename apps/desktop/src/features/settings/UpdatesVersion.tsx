import { AlertTriangle, CheckCircle2, Loader2, RefreshCw, ShieldCheck, Wrench } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import { api, ApiError, type CompatibilityResult, type ServerCapability } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { APP_VERSION } from "../../lib/version";

/** Desktop-side update status machine (full download/install flow runs via the Tauri updater once a
 * signed release service is configured — see docs/74-update-system.md). */
type CheckState = "idle" | "checking" | "up_to_date" | "available" | "no_service" | "error";

function fmtTime(d: Date | null): string {
  return d ? d.toLocaleString() : "—";
}

export function UpdatesVersion() {
  const { user } = useAuth();
  const [cap, setCap] = useState<ServerCapability | null>(null);
  const [compat, setCompat] = useState<CompatibilityResult | null>(null);
  const [state, setState] = useState<CheckState>("idle");
  const [lastCheck, setLastCheck] = useState<Date | null>(null);
  const [serviceNote, setServiceNote] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const check = useCallback(async () => {
    setState("checking"); setErr(null);
    try {
      const [c, k] = await Promise.all([api.capability(), api.updatesCompatibility(APP_VERSION)]);
      setCap(c); setCompat(k); setLastCheck(new Date());
      // Ask the server whether a remote release service is configured (the Tauri updater fetches &
      // verifies the signed manifest directly; the server never proxies arbitrary downloads).
      try {
        const svc = await api.systemUpdateCheck();
        if (!svc.configured) { setState("no_service"); setServiceNote(svc.note); }
        else { setState("up_to_date"); setServiceNote(null); }
      } catch {
        // systemUpdateCheck is Super-Admin only; ordinary users simply can't see release-service config.
        setState("up_to_date"); setServiceNote(null);
      }
    } catch (e) {
      setState("error");
      setErr(e instanceof ApiError ? e.message : "Could not reach the update service.");
    }
  }, []);

  useEffect(() => { void check(); }, [check]);

  const db = cap?.database;
  const compatBad = compat && !compat.can_operate;

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardContent className="flex flex-col gap-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 className="flex items-center gap-2 text-sm font-semibold">
                <ShieldCheck className="h-4 w-4 text-brand" /> Updates &amp; Version
              </h3>
              <p className="text-xs text-muted-foreground">
                Your OneStats versions and update status. Updates are cryptographically verified before
                installing; your cricket data and settings are always preserved.
              </p>
            </div>
            <Button size="sm" variant="outline" onClick={() => void check()} disabled={state === "checking"}>
              {state === "checking" ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
              Check for updates
            </Button>
          </div>

          {/* Compatibility banner */}
          {compatBad && (
            <div className="flex items-start gap-2 rounded-[var(--radius-app)] border border-warning/40 bg-warning/10 p-3 text-xs text-warning">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <div>{compat?.message}</div>
            </div>
          )}

          {/* Current installation */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <Field label="Desktop app" value={APP_VERSION} />
            <Field label="Server" value={cap?.server_version ?? (err ? "unavailable" : "…")} />
            <Field label="Database schema" value={db ? `${db.current_level ?? "?"}${db.up_to_date ? "" : " (update pending)"}` : "…"} />
            <Field label="Release channel" value={cap?.channel ?? "…"} />
            <Field label="API version" value={cap ? `v${cap.api_version}` : "…"} />
            <Field label="Last checked" value={fmtTime(lastCheck)} />
          </div>

          {/* Status line */}
          <div className="flex items-center gap-2 rounded-[var(--radius-app)] border border-border bg-muted/40 p-2.5 text-xs">
            {state === "checking" && <><Loader2 className="h-4 w-4 animate-spin text-brand" /> Checking for updates…</>}
            {state === "up_to_date" && !compatBad && <><CheckCircle2 className="h-4 w-4 text-success" /> OneStats is up to date.</>}
            {state === "no_service" && <><Wrench className="h-4 w-4 text-muted-foreground" /> {serviceNote ?? "No automatic update service is configured; updates are delivered via the installer."}</>}
            {state === "error" && <><AlertTriangle className="h-4 w-4 text-danger" /> {err}</>}
            {cap?.maintenance.mode && <Badge variant="warning" className="ml-auto">Server in maintenance</Badge>}
          </div>

          {user?.is_super_admin && (
            <div className="flex items-center justify-between gap-2 border-t border-border pt-3">
              <p className="text-xs text-muted-foreground">Server updates, maintenance mode and backups are managed by Super Admins.</p>
              <a href="#/admin/system-updates"
                className="whitespace-nowrap rounded-[var(--radius-app)] border border-brand bg-brand/10 px-3 py-1.5 text-sm font-medium text-brand">
                System Updates →
              </a>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[var(--radius-app)] border border-border bg-card p-2">
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="truncate text-sm font-semibold text-card-foreground" title={value}>{value}</div>
    </div>
  );
}
