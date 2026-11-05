import { isTauri } from "@tauri-apps/api/core";
import { AlertTriangle, CheckCircle2, Download, Loader2, LogIn, RefreshCw, RotateCw, ShieldCheck, Wrench } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import { api, ApiError, type CompatibilityResult, type ServerCapability } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { APP_VERSION } from "../../lib/version";

/** Desktop-side update status machine. When a signed release service is configured AND the app is
 * running inside the Tauri runtime, "Check for updates" drives the official Tauri 2 updater
 * (check → download → signature-verify → install → relaunch). Without a configured service — or in a
 * plain browser/dev shell with no Tauri runtime — it falls back to the honest installer-based state.
 * See docs/74-update-system.md. */
type CheckState =
  | "idle" | "checking" | "up_to_date" | "available"
  | "downloading" | "installing" | "relaunching"
  | "no_service" | "error";

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
  // True only when the capability call returned 401 — the server is reachable, the session expired.
  const [authExpired, setAuthExpired] = useState(false);
  const [newVersion, setNewVersion] = useState<string | null>(null);
  const [progress, setProgress] = useState<number | null>(null);

  // Ask the native Tauri updater whether a newer signed release is available. Imported dynamically so
  // the plugin is only loaded inside the real app (never in a browser/vitest environment).
  const checkTauriUpdate = useCallback(async () => {
    try {
      const { check: checkUpdate } = await import("@tauri-apps/plugin-updater");
      const update = await checkUpdate();
      if (!update) { setState("up_to_date"); setNewVersion(null); return; }
      setNewVersion(update.version);
      setState("available");
    } catch (e) {
      setState("error");
      setErr(e instanceof Error ? e.message : "Could not check for updates.");
    }
  }, []);

  const check = useCallback(async () => {
    setState("checking"); setErr(null); setAuthExpired(false);
    try {
      const [c, k] = await Promise.all([api.capability(), api.updatesCompatibility(APP_VERSION)]);
      setCap(c); setCompat(k); setLastCheck(new Date());
    } catch (e) {
      // Distinguish an expired session (server reachable, 401) from a server that is truly unreachable.
      if (e instanceof ApiError && e.status === 401) {
        setAuthExpired(true);
        setErr("Your session has expired — please sign in again.");
      } else if (e instanceof ApiError && e.status && e.status >= 500) {
        setErr("The OneStats server is currently unreachable. Please try again shortly.");
      } else {
        setErr(e instanceof ApiError ? e.message : "Could not reach the update service.");
      }
      setState("error");
      return;
    }
    // Ask the server whether a remote release service is configured (the Tauri updater fetches &
    // verifies the signed manifest directly; the server never proxies arbitrary downloads).
    let configured = false;
    try {
      const svc = await api.systemUpdateCheck();
      configured = svc.configured;
      setServiceNote(svc.configured ? null : svc.note);
    } catch {
      // systemUpdateCheck is Super-Admin only; ordinary users simply can't see release-service config.
      setState("up_to_date"); setServiceNote(null);
      return;
    }
    if (!configured) { setState("no_service"); return; }
    // A signed release service is configured. Drive the real updater when running inside the app;
    // in a browser/dev shell without the native runtime we cannot run it, so report up to date.
    if (!isTauri()) { setState("up_to_date"); setServiceNote(null); return; }
    await checkTauriUpdate();
  }, [checkTauriUpdate]);

  // Download, verify and install the pending update, then relaunch. The signature is verified against
  // the embedded trusted public key by the plugin before anything is installed.
  const installUpdate = useCallback(async () => {
    setErr(null);
    try {
      const { check: checkUpdate } = await import("@tauri-apps/plugin-updater");
      const { relaunch } = await import("@tauri-apps/plugin-process");
      const update = await checkUpdate();
      if (!update) { setState("up_to_date"); setNewVersion(null); return; }
      setState("downloading"); setProgress(0);
      let downloaded = 0;
      let total = 0;
      await update.downloadAndInstall((event) => {
        switch (event.event) {
          case "Started":
            total = event.data.contentLength ?? 0;
            setProgress(0);
            break;
          case "Progress":
            downloaded += event.data.chunkLength;
            setProgress(total > 0 ? Math.min(100, Math.round((downloaded / total) * 100)) : null);
            break;
          case "Finished":
            setState("installing");
            setProgress(100);
            break;
        }
      });
      setState("relaunching");
      await relaunch();
    } catch (e) {
      setState("error");
      setErr(e instanceof Error ? e.message : "The update could not be installed.");
    }
  }, []);

  useEffect(() => { void check(); }, [check]);

  const db = cap?.database;
  const compatBad = compat && !compat.can_operate;
  const busy = state === "checking" || state === "downloading" || state === "installing" || state === "relaunching";
  const serverValue = cap?.server_version ?? (authExpired ? "sign in required" : err ? "unavailable" : "…");

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
            <Button size="sm" variant="outline" onClick={() => void check()} disabled={busy}>
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
            <Field label="Server" value={serverValue} />
            <Field label="Database schema" value={db ? `${db.current_level ?? "?"}${db.up_to_date ? "" : " (update pending)"}` : "…"} />
            <Field label="Release channel" value={cap?.channel ?? "…"} />
            <Field label="API version" value={cap ? `v${cap.api_version}` : "…"} />
            <Field label="Last checked" value={fmtTime(lastCheck)} />
          </div>

          {/* Status line */}
          <div className="flex items-center gap-2 rounded-[var(--radius-app)] border border-border bg-muted/40 p-2.5 text-xs">
            {state === "checking" && <><Loader2 className="h-4 w-4 animate-spin text-brand" /> Checking for updates…</>}
            {state === "up_to_date" && !compatBad && <><CheckCircle2 className="h-4 w-4 text-success" /> OneStats is up to date.</>}
            {state === "available" && (
              <>
                <Download className="h-4 w-4 text-brand" />
                <span>Version {newVersion} is available.</span>
                <Button size="sm" className="ml-auto" onClick={() => void installUpdate()}>
                  <Download className="h-4 w-4" /> Install &amp; restart
                </Button>
              </>
            )}
            {state === "downloading" && (
              <>
                <Loader2 className="h-4 w-4 animate-spin text-brand" />
                <span>Downloading update{newVersion ? ` ${newVersion}` : ""}…{progress !== null ? ` ${progress}%` : ""}</span>
              </>
            )}
            {state === "installing" && <><Loader2 className="h-4 w-4 animate-spin text-brand" /> Verifying and installing…</>}
            {state === "relaunching" && <><RotateCw className="h-4 w-4 animate-spin text-brand" /> Restarting OneStats…</>}
            {state === "no_service" && <><Wrench className="h-4 w-4 text-muted-foreground" /> {serviceNote ?? "No automatic update service is configured; updates are delivered via the installer."}</>}
            {state === "error" && (
              <>
                {authExpired ? <LogIn className="h-4 w-4 text-warning" /> : <AlertTriangle className="h-4 w-4 text-danger" />}
                <span className={authExpired ? "text-warning" : undefined}>{err}</span>
              </>
            )}
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
