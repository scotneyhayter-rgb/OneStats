/**
 * Records & Achievements (Phase 13) — all-time record holders (prominent No.1 + expanded ranking),
 * seasonal leaders, upcoming milestones and Life Members, plus one-click Club Record Book PDF. Reads
 * from the Records Engine (approved data only); ties and known-minimum flags are shown, nothing invented.
 */
import { Award, BookOpen, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { AppShell } from "../../components/layout/AppShell";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import { api, ApiError, type RecordCategory } from "../../lib/api";
import { useWorkspace } from "../../lib/workspace-context";

type Seasonal = Awaited<ReturnType<typeof api.recordsSeasonal>>;
type Upcoming = Awaited<ReturnType<typeof api.recordsUpcoming>>;

export function Records() {
  const { current } = useWorkspace();
  const [all, setAll] = useState<Record<string, RecordCategory> | null>(null);
  const [seasonal, setSeasonal] = useState<Seasonal>([]);
  const [upcoming, setUpcoming] = useState<Upcoming>([]);
  const [honours, setHonours] = useState<Record<string, unknown>[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!current) return;
    setBusy(true);
    setError(null);
    try {
      const [a, s, u, h] = await Promise.all([
        api.recordsAllTime(current.id), api.recordsSeasonal(current.id),
        api.recordsUpcoming(current.id, 10), api.recordsHonours(current.id),
      ]);
      setAll(a);
      setSeasonal(s);
      setUpcoming(u);
      setHonours(h);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load records.");
    } finally {
      setBusy(false);
    }
  }, [current]);
  useEffect(() => {
    void load();
  }, [load]);

  if (!current) {
    return (
      <AppShell title="Records & Achievements" subtitle="Select or create a workspace">
        <Card><CardContent><p className="text-sm text-muted-foreground">No workspace selected.</p></CardContent></Card>
      </AppShell>
    );
  }

  const exportBook = async () => {
    try {
      window.open(await api.recordBookPdfUrl(current.id), "_blank");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Record book export failed.");
    }
  };

  const categories = all ? Object.entries(all).filter(([, c]) => c.holder) : [];

  return (
    <AppShell title="Records & Achievements" subtitle={current.name}>
      <div className="mx-auto flex max-w-5xl flex-col gap-4">
        {error && <p className="rounded-[var(--radius-app)] border border-danger/40 bg-danger/5 px-3 py-2 text-sm text-danger">{error}</p>}

        <div className="flex items-center gap-2">
          <Button size="sm" variant="outline" disabled={busy} onClick={() => void load()}>
            <RefreshCw className="h-4 w-4" aria-hidden /> Refresh
          </Button>
          <Button size="sm" className="ml-auto" onClick={() => void exportBook()}>
            <BookOpen className="h-4 w-4" aria-hidden /> Club Record Book (PDF)
          </Button>
        </div>

        <Card><CardContent className="flex flex-col gap-3">
          <h3 className="text-sm font-semibold">All-time record holders</h3>
          {categories.length === 0 && <p className="text-xs text-muted-foreground">No approved records yet.</p>}
          <div className="grid gap-2 sm:grid-cols-2">
            {categories.map(([key, c]) => (
              <button key={key} type="button" onClick={() => setExpanded(expanded === key ? null : key)}
                className="flex flex-col gap-1 rounded-[var(--radius-app)] border border-border p-3 text-left hover:border-brand">
                <div className="flex items-center gap-2">
                  <Award className="h-4 w-4 text-brand" aria-hidden />
                  <span className="text-xs text-muted-foreground">{c.title}</span>
                </div>
                <div className="flex items-baseline gap-2">
                  <span className="text-lg font-semibold">{c.holder?.player}</span>
                  <span className="text-xl font-bold tabular-nums text-brand">{c.value}</span>
                  {c.holder?.tied && <Badge variant="muted">tied</Badge>}
                  {c.holder?.known_minimum && <Badge variant="warning">known min.</Badge>}
                </div>
                {expanded === key && (
                  <div className="mt-1 flex flex-col gap-0.5 border-t border-border pt-1 text-xs">
                    {c.ranking.map((r) => (
                      <div key={r.rank} className="flex justify-between">
                        <span>{r.rank}. {r.player}</span><span className="tabular-nums">{r.value}</span>
                      </div>
                    ))}
                  </div>
                )}
              </button>
            ))}
          </div>
        </CardContent></Card>

        <div className="grid gap-4 md:grid-cols-2">
          <Card><CardContent className="flex flex-col gap-2">
            <h3 className="text-sm font-semibold">Seasonal leaders</h3>
            {seasonal.length === 0 && <p className="text-xs text-muted-foreground">No seasons with approved data.</p>}
            {seasonal.map((s) => (
              <div key={s.season_id} className="flex flex-col gap-0.5 border-t border-border pt-1 text-sm first:border-0">
                <span className="font-medium">{s.label}</span>
                <span className="text-xs text-muted-foreground">
                  Runs: {s.leading_run_scorer ? `${s.leading_run_scorer.player} (${s.leading_run_scorer.value})` : "—"}
                  {" · "}Wkts: {s.leading_wicket_taker ? `${s.leading_wicket_taker.player} (${s.leading_wicket_taker.value})` : "—"}
                </span>
              </div>
            ))}
          </CardContent></Card>

          <Card><CardContent className="flex flex-col gap-2">
            <h3 className="text-sm font-semibold">Upcoming milestones</h3>
            {upcoming.length === 0 && <p className="text-xs text-muted-foreground">None approaching (from confirmed totals).</p>}
            {upcoming.slice(0, 12).map((u, i) => (
              <div key={i} className="flex items-center gap-2 text-sm">
                <Badge variant="brand">{u.to_go}</Badge>
                <span className="text-muted-foreground">from {u.threshold} {u.metric} (on {u.current})</span>
              </div>
            ))}
          </CardContent></Card>
        </div>

        <Card><CardContent className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold">Life Members & honorary recognition</h3>
          {honours.length === 0 && <p className="text-xs text-muted-foreground">None recorded.</p>}
          {honours.map((h, i) => (
            <div key={i} className="flex flex-wrap items-center gap-2 text-sm">
              <Badge variant="muted">{String(h.honour_type).replace(/_/g, " ")}</Badge>
              <span className="font-medium">{String(h.title)}</span>
              {h.awarded_season ? <span className="text-xs text-muted-foreground">{String(h.awarded_season)}</span> : null}
            </div>
          ))}
          <p className="text-xs text-muted-foreground">
            Honours are explicitly recorded and authorised — never inferred from statistics.
          </p>
        </CardContent></Card>
      </div>
    </AppShell>
  );
}
