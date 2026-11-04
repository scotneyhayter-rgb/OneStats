/**
 * Cricsheet Import Management — the International workspace's scorecard import console.
 *
 * Covers: Import Scorecards / Update Now (start-continue the per-format backfill), View Import Progress
 * (backfill status + genuine counts), View Imported Matches & Review Imported Scorecards (awaiting
 * verification), Resolve Import Errors (failed), Resolve Player Identities (ambiguous same-name imports),
 * and View Source Information (the agreed allow-list + per-file provenance). Every number comes straight
 * from the import log / backfill state — nothing is fabricated. The background worker performs downloads;
 * these controls only set state. Imported scorecards stay UNAPPROVED until a person verifies them.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { Database, Loader2, Pause, Play, RefreshCw, StopCircle } from "lucide-react";
import { AppShell } from "../../components/layout/AppShell";
import { EmptyState } from "../../components/states/States";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import {
  api, ApiError,
  type CricsheetBackfill, type CricsheetImportRow, type CricsheetSummary, type IdentityReviewRow,
} from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { canManage } from "../../lib/permissions";
import { useWorkspace } from "../../lib/workspace-context";

const FORMATS = ["test", "odi", "t20i"] as const;
const FORMAT_LABEL: Record<string, string> = { test: "Test", odi: "ODI", t20i: "T20I" };
const ACTIVE: CricsheetBackfill["status"][] = ["pending", "running"];
const STATUS_VARIANT: Record<CricsheetBackfill["status"], "success" | "brand" | "warning" | "muted" | "danger"> = {
  pending: "brand", running: "brand", paused: "warning", completed: "success", cancelled: "muted", failed: "danger",
};
// The agreed fetch allow-list (mirrors services/api/onestats/domain/intl/sources.py).
const ALLOWED_SOURCES = [
  { name: "Cricsheet", host: "cricsheet.org", role: "fetched", use: "ball-by-ball scorecards (primary)" },
  { name: "Wikipedia / Wikidata", host: "wikipedia.org", role: "fetched", use: "match index + identity" },
  { name: "ESPNcricinfo", host: "—", role: "benchmark", use: "human cross-check — never fetched (bot-blocked)" },
  { name: "CricketStatz", host: "—", role: "benchmark", use: "trusted numbers — never overwritten" },
];

type Tab = "review" | "errors" | "identities" | "sources";

export function ImportManagement() {
  const { current } = useWorkspace();
  const { user } = useAuth();
  const admin = canManage(user, current);
  const workspaceId = current?.id ?? null;

  const [summary, setSummary] = useState<CricsheetSummary | null>(null);
  const [tab, setTab] = useState<Tab>("review");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!workspaceId) return;
    setError(null);
    try {
      setSummary(await api.cricsheetSummary(workspaceId));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load import status.");
    }
  }, [workspaceId]);

  useEffect(() => { void load(); }, [load]);

  const control = async (fmt: string, action: "start" | "pause" | "resume" | "cancel") => {
    if (!workspaceId) return;
    setBusy(`${fmt}-${action}`); setError(null);
    try { await api.cricsheetControl(workspaceId, fmt, action); await load(); }
    catch (e) { setError(e instanceof ApiError ? e.message : "The action could not be completed."); }
    finally { setBusy(null); }
  };

  const byFormat = useMemo(() => {
    const m = new Map<string, CricsheetBackfill>();
    for (const b of summary?.backfills ?? []) m.set(b.format, b);
    return m;
  }, [summary]);

  if (!current) {
    return (
      <AppShell title="Import Scorecards" subtitle="Cricsheet import management">
        <EmptyState title="No workspace selected" description="Choose a workspace to continue." />
      </AppShell>
    );
  }

  const imp = summary?.imports;

  return (
    <AppShell title="Import Scorecards" subtitle="Cricsheet import — progress, review and sources">
      <div className="mx-auto flex max-w-5xl flex-col gap-4">
        {error && <p className="rounded-[var(--radius-app)] border border-danger/40 bg-danger/10 p-2 text-xs text-danger">{error}</p>}

        {/* Progress tiles */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Tile label="Imported (awaiting review)" value={imp?.awaiting_verification} />
          <Tile label="Skipped" value={imp?.skipped} />
          <Tile label="Failed" value={imp?.failed} tone={imp?.failed ? "danger" : undefined} />
          <Tile label="Logged total" value={imp?.total} />
        </div>

        {/* Backfill per format: Import Scorecards / Update Now + View Import Progress */}
        <Card><CardContent className="flex flex-col gap-3">
          <div className="flex items-center gap-2">
            <Database className="h-5 w-5 text-brand" aria-hidden />
            <h3 className="text-sm font-semibold">Historical import (backfill)</h3>
            <Button size="sm" variant="outline" className="ml-auto gap-1" onClick={() => void load()}>
              <RefreshCw className="h-3.5 w-3.5" aria-hidden /> Refresh
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            Imports the complete available Cricsheet collection per format, in batches, accuracy first.
            The background worker performs the downloads; imported matches await verification and never
            overwrite an approved scorecard. Cricsheet is not assumed complete — anything it lacks stays
            in the research queue for other sources.
          </p>
          <div className="grid gap-3 sm:grid-cols-3">
            {FORMATS.map((fmt) => (
              <BackfillCard key={fmt} fmt={fmt} row={byFormat.get(fmt) ?? null} admin={admin}
                busy={busy} onControl={control} />
            ))}
          </div>
        </CardContent></Card>

        {/* Tabs: review / errors / identities / sources */}
        <div className="flex flex-wrap gap-1" role="tablist" aria-label="Import views">
          {([["review", "Review imported"], ["errors", "Import errors"],
             ["identities", "Player identities"], ["sources", "Source info"]] as [Tab, string][]).map(([k, label]) => (
            <button key={k} type="button" role="tab" aria-selected={tab === k} onClick={() => setTab(k)}
              className={`rounded-full px-3 py-1 text-xs font-medium ${tab === k ? "bg-muted text-foreground" : "text-muted-foreground hover:text-foreground"}`}>
              {label}
            </button>
          ))}
        </div>

        {tab === "review" && <ImportList workspaceId={current.id} statusFilter="awaiting_verification"
          empty="No imported scorecards awaiting review yet." />}
        {tab === "errors" && <ImportList workspaceId={current.id} statusFilter="failed"
          empty="No import errors." />}
        {tab === "identities" && <IdentityReviews workspaceId={current.id} />}
        {tab === "sources" && <SourceInfo />}
      </div>
    </AppShell>
  );
}

function Tile({ label, value, tone }: { label: string; value?: number; tone?: "danger" }) {
  return (
    <div className="rounded-[var(--radius-app)] border border-border p-3">
      <div className={`text-2xl font-semibold tabular-nums ${tone === "danger" ? "text-danger" : ""}`}>
        {value ?? "—"}
      </div>
      <div className="text-[11px] text-muted-foreground">{label}</div>
    </div>
  );
}

function BackfillCard({ fmt, row, admin, busy, onControl }: {
  fmt: string; row: CricsheetBackfill | null; admin: boolean; busy: string | null;
  onControl: (fmt: string, action: "start" | "pause" | "resume" | "cancel") => void;
}) {
  const status = row?.status;
  const pct = row && row.total_seen > 0 ? Math.round((row.processed / row.total_seen) * 100) : null;
  const active = status ? ACTIVE.includes(status) : false;
  return (
    <div className="flex flex-col gap-2 rounded-[var(--radius-app)] border border-border p-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold">{FORMAT_LABEL[fmt]}</span>
        {status ? <Badge variant={STATUS_VARIANT[status]}>{status}</Badge> : <Badge variant="muted">not started</Badge>}
      </div>
      {row && (
        <div className="text-xs text-muted-foreground">
          {row.processed}/{row.total_seen || "?"} processed{pct != null ? ` (${pct}%)` : ""} ·
          {" "}{row.imported} imported · {row.skipped} skipped · {row.failed} failed
        </div>
      )}
      {row?.last_error && <p className="text-[11px] text-danger">Last error: {row.last_error}</p>}
      {admin && (
        <div className="flex flex-wrap gap-1">
          {(!status || status === "completed" || status === "cancelled") && (
            <Button size="sm" disabled={busy !== null} onClick={() => onControl(fmt, "start")} className="gap-1">
              {busy === `${fmt}-start` ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden /> : <Play className="h-3.5 w-3.5" aria-hidden />}
              {status === "completed" ? "Re-scan" : "Start"}
            </Button>
          )}
          {status === "running" && (
            <Button size="sm" variant="outline" disabled={busy !== null} onClick={() => onControl(fmt, "pause")} className="gap-1">
              <Pause className="h-3.5 w-3.5" aria-hidden /> Pause
            </Button>
          )}
          {status === "paused" && (
            <Button size="sm" variant="outline" disabled={busy !== null} onClick={() => onControl(fmt, "resume")} className="gap-1">
              <Play className="h-3.5 w-3.5" aria-hidden /> Resume
            </Button>
          )}
          {active && (
            <Button size="sm" variant="outline" disabled={busy !== null} onClick={() => onControl(fmt, "cancel")} className="gap-1">
              <StopCircle className="h-3.5 w-3.5" aria-hidden /> Cancel
            </Button>
          )}
        </div>
      )}
    </div>
  );
}

function ImportList({ workspaceId, statusFilter, empty }: { workspaceId: string; statusFilter: string; empty: string }) {
  const [rows, setRows] = useState<CricsheetImportRow[] | null>(null);
  useEffect(() => {
    let live = true;
    void api.cricsheetImports(workspaceId, statusFilter).then((r) => { if (live) setRows(r); }).catch(() => setRows([]));
    return () => { live = false; };
  }, [workspaceId, statusFilter]);

  if (rows === null) return <p className="text-xs text-muted-foreground">Loading…</p>;
  if (rows.length === 0) return <EmptyState title="Nothing here" description={empty} />;
  return (
    <div className="overflow-x-auto rounded-[var(--radius-app)] border border-border">
      <table className="w-full text-xs">
        <thead className="bg-muted text-left text-muted-foreground">
          <tr><th className="px-2 py-1.5">Match (Cricsheet id)</th><th className="px-2 py-1.5">Format</th>
            <th className="px-2 py-1.5">Detail</th><th className="px-2 py-1.5">When</th></tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.source_ref} className="border-t border-border align-top">
              <td className="px-2 py-1.5 font-medium">{r.source_ref}</td>
              <td className="px-2 py-1.5">{r.format ? FORMAT_LABEL[r.format] ?? r.format : "—"}</td>
              <td className="px-2 py-1.5 text-muted-foreground">{r.detail ?? "—"}</td>
              <td className="px-2 py-1.5 text-muted-foreground">{new Date(r.updated_at).toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function IdentityReviews({ workspaceId }: { workspaceId: string }) {
  const [rows, setRows] = useState<IdentityReviewRow[] | null>(null);
  useEffect(() => {
    let live = true;
    void api.cricsheetIdentityReviews(workspaceId).then((r) => { if (live) setRows(r); }).catch(() => setRows([]));
    return () => { live = false; };
  }, [workspaceId]);

  if (rows === null) return <p className="text-xs text-muted-foreground">Loading…</p>;
  if (rows.length === 0) return <EmptyState title="No identities to resolve" description="No ambiguous same-name imports are waiting." />;
  return (
    <div className="flex flex-col gap-2">
      <p className="text-[11px] text-muted-foreground">
        Players imported under a shared name with no registry id. They were kept separate (never
        auto-merged); resolve each in People → identity management.
      </p>
      {rows.map((r) => (
        <div key={r.id} className="flex flex-wrap items-center gap-2 rounded-[var(--radius-app)] border border-border p-2 text-xs">
          <Badge variant="warning">{r.confidence ?? "review"}</Badge>
          <span className="text-muted-foreground">{r.evidence ?? "possible duplicate"}</span>
          <span className="ml-auto font-mono text-[11px] text-muted-foreground">
            {r.person_a_id.slice(0, 8)}… ↔ {r.person_b_id.slice(0, 8)}…
          </span>
        </div>
      ))}
    </div>
  );
}

function SourceInfo() {
  return (
    <Card><CardContent className="flex flex-col gap-2">
      <h3 className="text-sm font-semibold">Source information</h3>
      <p className="text-xs text-muted-foreground">
        The importer fetches only the agreed allow-list. Completeness needs agreement across at least two
        sources; benchmarks are consulted by people, never scraped. Each imported file's checksum and URL
        are recorded for provenance.
      </p>
      <div className="overflow-hidden rounded-[var(--radius-app)] border border-border">
        <table className="w-full text-xs">
          <thead className="bg-muted text-left text-muted-foreground">
            <tr><th className="px-2 py-1.5">Source</th><th className="px-2 py-1.5">Host</th>
              <th className="px-2 py-1.5">Role</th><th className="px-2 py-1.5">Used for</th></tr>
          </thead>
          <tbody>
            {ALLOWED_SOURCES.map((s) => (
              <tr key={s.name} className="border-t border-border">
                <td className="px-2 py-1.5 font-medium">{s.name}</td>
                <td className="px-2 py-1.5 text-muted-foreground">{s.host}</td>
                <td className="px-2 py-1.5">
                  <Badge variant={s.role === "fetched" ? "success" : "muted"}>{s.role}</Badge>
                </td>
                <td className="px-2 py-1.5 text-muted-foreground">{s.use}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </CardContent></Card>
  );
}
