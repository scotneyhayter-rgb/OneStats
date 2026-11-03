/**
 * International Men's Cricket — Update Management + match-index dashboard.
 *
 * Two honest panels for the International workspace:
 *  1. Automatic updates — the recurring daily 04:00 Australia/Melbourne update task: its real next-run
 *     and last-run, Update Now / Pause / Disable controls, and a GENUINE run history. The history keeps
 *     the scheduled instant (scheduled_for) separate from when a run actually happened (ran_at) and
 *     flags catch-ups, so a run that fired late after the PC was off is never shown as on-time. A
 *     "no pipeline" run is shown truthfully as "fired, nothing to import yet" — not as a success.
 *  2. Match index — per-format coverage (Test / ODI / T20I). Counts are the real row counts; an unknown
 *     expected total is shown as "unknown", never as zero. The index starts empty and NO completeness
 *     is claimed until coverage is actually reconciled from multiple sources.
 *
 * All figures come straight from the backend; nothing here fabricates a run, a count or a result.
 */
import { useCallback, useEffect, useState } from "react";
import { CalendarClock, Loader2, Pause, Play, Power, RefreshCw } from "lucide-react";
import { AppShell } from "../../components/layout/AppShell";
import { EmptyState } from "../../components/states/States";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import {
  api,
  ApiError,
  type IntlFormat,
  type MatchIndexSummary,
  type SchedulerTask,
  type SchedulerTaskRun,
} from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { canManage } from "../../lib/permissions";
import { useWorkspace } from "../../lib/workspace-context";

const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const FORMAT_LABELS: Record<IntlFormat, string> = { test: "Test", odi: "ODI", t20i: "T20I" };
const STATE_ORDER = ["expected", "indexed", "imported", "complete", "verified"] as const;

const RUN_STATUS: Record<SchedulerTaskRun["status"], { label: string; variant: "success" | "danger" | "muted" | "warning" }> = {
  succeeded: { label: "succeeded", variant: "success" },
  failed: { label: "failed", variant: "danger" },
  skipped: { label: "skipped", variant: "muted" },
  no_pipeline: { label: "no import pipeline yet", variant: "warning" },
};

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

/** The task's recurrence as a plain-English sentence, honest about cadence and timezone. */
function scheduleText(t: SchedulerTask): string {
  const at = `${pad(t.hour)}:${pad(t.minute)}`;
  const when =
    t.schedule_kind === "daily"
      ? `every day at ${at}`
      : `every ${t.day_of_week == null ? "week" : DAYS[t.day_of_week]} at ${at}`;
  return `${when} (${t.timezone})`;
}

/** Render a UTC instant in the task's own timezone, e.g. "Tue 4 Nov 2026, 04:00 AEDT". */
function inZone(iso: string | null, tz: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  try {
    return new Intl.DateTimeFormat(undefined, {
      timeZone: tz,
      weekday: "short",
      day: "numeric",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      timeZoneName: "short",
    }).format(d);
  } catch {
    return d.toISOString();
  }
}

/** A short, local date-time for run history rows. */
function localDateTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  return new Intl.DateTimeFormat(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(d);
}

export function InternationalUpdates() {
  const { current } = useWorkspace();
  const { user } = useAuth();
  const admin = canManage(user, current);
  const workspaceId = current?.id ?? null;

  const [tasks, setTasks] = useState<SchedulerTask[] | null>(null);
  const [index, setIndex] = useState<MatchIndexSummary | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!workspaceId) return;
    setError(null);
    try {
      const [t, i] = await Promise.all([
        api.schedulerTasks(workspaceId),
        api.matchIndexSummary(workspaceId),
      ]);
      setTasks(t);
      setIndex(i);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load the update information.");
    }
  }, [workspaceId]);

  useEffect(() => {
    void load();
  }, [load]);

  const act = async (key: string, fn: () => Promise<unknown>, done?: string) => {
    setBusy(key);
    setError(null);
    setNotice(null);
    try {
      await fn();
      if (done) setNotice(done);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The action could not be completed.");
    } finally {
      setBusy(null);
    }
  };

  if (!current) {
    return (
      <AppShell title="International Updates" subtitle="Scheduled updates and match-index coverage">
        <EmptyState title="No workspace selected" description="Choose a workspace to continue." />
      </AppShell>
    );
  }

  return (
    <AppShell title="International Updates" subtitle="Scheduled updates and match-index coverage">
      <div className="mx-auto flex max-w-5xl flex-col gap-4">
        {error && <p className="rounded-[var(--radius-app)] border border-danger/40 bg-danger/10 p-2 text-xs text-danger">{error}</p>}
        {notice && <p className="rounded-[var(--radius-app)] border border-success/40 bg-success/10 p-2 text-xs text-success">{notice}</p>}

        {/* --- Automatic updates (Update Management) --- */}
        <Card>
          <CardContent className="flex flex-col gap-3">
            <div className="flex items-center gap-2">
              <CalendarClock className="h-5 w-5 text-brand" aria-hidden />
              <h3 className="text-sm font-semibold">Automatic updates</h3>
              <Button size="sm" variant="outline" className="ml-auto gap-1" disabled={busy !== null} onClick={() => void load()}>
                <RefreshCw className="h-3.5 w-3.5" aria-hidden /> Refresh
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              OneStats checks for newly completed and recently corrected international matches on a
              schedule. A run is recorded only when it actually happens — if the computer was off at the
              scheduled time, the next run is shown as a late catch-up, never as if it had run on time.
            </p>

            {tasks === null && <p className="text-xs text-muted-foreground">Loading…</p>}
            {tasks !== null && tasks.length === 0 && (
              <p className="text-xs text-muted-foreground">
                No scheduled update is registered for this workspace.
              </p>
            )}
            {tasks?.map((t) => (
              <TaskPanel
                key={t.id}
                task={t}
                admin={admin}
                busy={busy}
                onRunNow={() =>
                  void act(`run-${t.id}`, () => api.schedulerRunNow(current.id, t.id), "Update started — see the run history below.")
                }
                onPause={() =>
                  void act(`pause-${t.id}`, () => api.schedulerPause(current.id, t.id, !t.paused))
                }
                onEnable={() =>
                  void act(`enable-${t.id}`, () => api.schedulerEnable(current.id, t.id, !t.enabled))
                }
                workspaceId={current.id}
              />
            ))}
          </CardContent>
        </Card>

        {/* --- Match index coverage (dashboard) --- */}
        <Card>
          <CardContent className="flex flex-col gap-3">
            <h3 className="text-sm font-semibold">Match index</h3>
            <p className="text-xs text-muted-foreground">
              What is known to exist, and how far it has been imported and verified, per format. Counts
              are real row counts. An expected total is shown only once it has been reconciled from more
              than one source; until then it reads <b>unknown</b> — which is different from zero. The
              index starts empty and no completeness is claimed.
            </p>
            {index === null ? (
              <p className="text-xs text-muted-foreground">Loading…</p>
            ) : (
              <div className="grid gap-3 sm:grid-cols-3">
                {(Object.keys(FORMAT_LABELS) as IntlFormat[]).map((fmt) => (
                  <FormatCoverage key={fmt} fmt={fmt} summary={index[fmt]} />
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </AppShell>
  );
}

function TaskPanel({
  task,
  admin,
  busy,
  onRunNow,
  onPause,
  onEnable,
  workspaceId,
}: {
  task: SchedulerTask;
  admin: boolean;
  busy: string | null;
  onRunNow: () => void;
  onPause: () => void;
  onEnable: () => void;
  workspaceId: string;
}) {
  const [showRuns, setShowRuns] = useState(true);
  const running = busy === `run-${task.id}`;

  return (
    <div className="flex flex-col gap-2 rounded-[var(--radius-app)] border border-border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">{task.name}</span>
        <Badge variant={task.enabled ? "success" : "muted"}>{task.enabled ? "enabled" : "disabled"}</Badge>
        {task.paused && <Badge variant="warning">paused</Badge>}
        {task.catch_up && <Badge variant="muted">catch-up on</Badge>}
      </div>
      <p className="text-xs text-muted-foreground">Runs {scheduleText(task)}.</p>

      <dl className="grid grid-cols-1 gap-x-6 gap-y-1 text-xs sm:grid-cols-2">
        <div className="flex justify-between gap-2 sm:block">
          <dt className="text-muted-foreground">Next run</dt>
          <dd className="font-medium">
            {task.enabled && !task.paused ? inZone(task.next_run_at, task.timezone) : "— (not scheduled while disabled/paused)"}
          </dd>
        </div>
        <div className="flex justify-between gap-2 sm:block">
          <dt className="text-muted-foreground">Last run</dt>
          <dd className="font-medium">
            {task.last_run_at ? `${inZone(task.last_run_at, task.timezone)}${task.last_status ? ` · ${task.last_status}` : ""}` : "never"}
          </dd>
        </div>
      </dl>
      {task.last_error && <p className="text-xs text-danger">Last error: {task.last_error}</p>}

      {admin && (
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" disabled={busy !== null || !task.enabled || task.paused} onClick={onRunNow} className="gap-1.5">
            {running ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : <Play className="h-4 w-4" aria-hidden />}
            Update now
          </Button>
          <Button size="sm" variant="outline" disabled={busy !== null || !task.enabled} onClick={onPause} className="gap-1.5">
            {task.paused ? <Play className="h-3.5 w-3.5" aria-hidden /> : <Pause className="h-3.5 w-3.5" aria-hidden />}
            {task.paused ? "Resume" : "Pause"}
          </Button>
          <Button size="sm" variant="outline" disabled={busy !== null} onClick={onEnable} className="gap-1.5">
            <Power className="h-3.5 w-3.5" aria-hidden />
            {task.enabled ? "Disable" : "Enable"}
          </Button>
          <Button size="sm" variant="outline" className="ml-auto" onClick={() => setShowRuns((v) => !v)}>
            {showRuns ? "Hide history" : "Show history"}
          </Button>
        </div>
      )}

      {showRuns && <RunHistory workspaceId={workspaceId} taskId={task.id} reloadKey={task.last_run_at} />}
    </div>
  );
}

function RunHistory({ workspaceId, taskId, reloadKey }: { workspaceId: string; taskId: string; reloadKey: string | null }) {
  const [runs, setRuns] = useState<SchedulerTaskRun[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setRuns(await api.schedulerRuns(workspaceId, taskId));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load the run history.");
    }
  }, [workspaceId, taskId]);

  useEffect(() => {
    void load();
  }, [load, reloadKey]);

  if (error) return <p className="text-xs text-danger">{error}</p>;
  if (runs === null) return <p className="text-xs text-muted-foreground">Loading history…</p>;
  if (runs.length === 0) {
    return (
      <p className="rounded-[var(--radius-app)] border border-border bg-muted/20 p-2 text-xs text-muted-foreground">
        No runs yet. When the update runs — on schedule or via “Update now” — each run is recorded here.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto rounded-[var(--radius-app)] border border-border">
      <table className="w-full text-xs">
        <thead className="bg-muted text-left text-muted-foreground">
          <tr>
            <th className="px-2 py-1.5">Scheduled for</th>
            <th className="px-2 py-1.5">Ran at</th>
            <th className="px-2 py-1.5">Result</th>
            <th className="px-2 py-1.5">Detail</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => {
            const s = RUN_STATUS[r.status] ?? { label: r.status, variant: "muted" as const };
            return (
              <tr key={r.id} className="border-t border-border align-top">
                <td className="px-2 py-1.5">{r.scheduled_for ? localDateTime(r.scheduled_for) : "—"}</td>
                <td className="px-2 py-1.5">
                  {localDateTime(r.ran_at)}
                  {r.was_catch_up && <Badge variant="warning" className="ml-1">late catch-up</Badge>}
                </td>
                <td className="px-2 py-1.5"><Badge variant={s.variant}>{s.label}</Badge></td>
                <td className="px-2 py-1.5 text-muted-foreground">{r.error ?? r.detail ?? "—"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function FormatCoverage({ fmt, summary }: { fmt: IntlFormat; summary: MatchIndexSummary[IntlFormat] }) {
  const total = STATE_ORDER.reduce((n, s) => n + (summary.states[s] ?? 0), 0);
  return (
    <div className="flex flex-col gap-2 rounded-[var(--radius-app)] border border-border p-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold">{FORMAT_LABELS[fmt]}</span>
        <Badge variant={summary.coverage_state === "reconciled" ? "success" : "muted"}>{summary.coverage_state}</Badge>
      </div>
      <div className="text-xs text-muted-foreground">
        Expected: <span className="font-medium text-foreground">{summary.expected == null ? "unknown" : summary.expected}</span>
        {" · "}in index: <span className="font-medium text-foreground">{total}</span>
      </div>
      <dl className="flex flex-col gap-0.5 text-xs">
        {STATE_ORDER.map((s) => (
          <div key={s} className="flex justify-between">
            <dt className="capitalize text-muted-foreground">{s}</dt>
            <dd className="font-medium">{summary.states[s] ?? 0}</dd>
          </div>
        ))}
      </dl>
      {(summary.candidates > 0 || summary.disputed > 0) && (
        <div className="flex flex-wrap gap-1 border-t border-border pt-1 text-[11px]">
          {summary.candidates > 0 && <Badge variant="muted">{summary.candidates} candidate</Badge>}
          {summary.disputed > 0 && <Badge variant="warning">{summary.disputed} disputed</Badge>}
        </div>
      )}
    </div>
  );
}
