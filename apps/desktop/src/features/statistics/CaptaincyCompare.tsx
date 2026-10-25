/**
 * Captaincy Comparison (Phase 12) — select two or more captains and compare their captaincy record
 * side by side (matches, W/L/D/T/NR, win %, consecutive wins, finals, grand finals). One engine; the
 * same figures as the captaincy reports. Captains are drawn from the "Most Matches Captained" report.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { AppShell } from "../../components/layout/AppShell";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import { api, ApiError, type CaptaincyCompareRow } from "../../lib/api";
import { useWorkspace } from "../../lib/workspace-context";

const METRICS: { key: keyof CaptaincyCompareRow; label: string; dp?: number }[] = [
  { key: "captained", label: "Matches captained" },
  { key: "wins", label: "Wins" },
  { key: "losses", label: "Losses" },
  { key: "draws", label: "Draws" },
  { key: "ties", label: "Ties" },
  { key: "no_results", label: "No results" },
  { key: "win_pct", label: "Win %", dp: 1 },
  { key: "consecutive_wins", label: "Consecutive wins" },
  { key: "gf_captained", label: "Grand finals captained" },
  { key: "gf_wins", label: "Grand finals won" },
];

export function CaptaincyCompare() {
  const { current } = useWorkspace();
  const [captains, setCaptains] = useState<{ subject_id: string; player: string }[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [rows, setRows] = useState<CaptaincyCompareRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!current) return;
    api.statsReport(current.id, "capt_most_matches").then((d) => {
      setCaptains(d.rows.map((r) => ({ subject_id: String(r.subject_id ?? ""), player: String(r.player ?? "Unknown") }))
        .filter((c) => c.subject_id));
    }).catch((e) => setError(e instanceof ApiError ? e.message : "Could not load captains."));
  }, [current]);

  const toggle = useCallback((id: string) => {
    setSelected((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]);
  }, []);

  const compare = useCallback(async () => {
    if (!current || selected.length < 2) return;
    setError(null);
    try {
      const res = await api.statsCaptaincyCompare(current.id, selected);
      setRows(res.captains);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Comparison failed.");
    }
  }, [current, selected]);

  const best = useMemo(() => {
    const m: Partial<Record<string, number>> = {};
    if (!rows) return m;
    for (const met of METRICS) {
      const vals = rows.map((r) => Number(r[met.key] ?? -Infinity));
      m[met.key] = Math.max(...vals);
    }
    return m;
  }, [rows]);

  if (!current) return <AppShell title="Captaincy Comparison" subtitle="Select a workspace"><div /></AppShell>;

  return (
    <AppShell title="Captaincy Comparison" subtitle={current.name}>
      <div className="mx-auto flex max-w-4xl flex-col gap-4">
        {error && <p className="rounded-[var(--radius-app)] border border-danger/40 bg-danger/5 px-3 py-2 text-sm text-danger">{error}</p>}
        <Card><CardContent className="flex flex-col gap-3">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold">Select captains to compare</h3>
            <a href="#/statistics/catalogue" className="ml-auto text-xs text-brand hover:underline">← Report Catalogue</a>
          </div>
          <div className="grid max-h-56 grid-cols-2 gap-1 overflow-auto sm:grid-cols-3">
            {captains.map((c) => (
              <label key={c.subject_id} className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={selected.includes(c.subject_id)} onChange={() => toggle(c.subject_id)} />
                {c.player}
              </label>
            ))}
            {captains.length === 0 && <p className="text-xs text-muted-foreground">No captains recorded yet.</p>}
          </div>
          <Button size="sm" disabled={selected.length < 2} onClick={() => void compare()}>
            Compare {selected.length > 0 ? `(${selected.length})` : ""}
          </Button>
          {selected.length === 1 && <p className="text-xs text-muted-foreground">Select at least two captains.</p>}
        </CardContent></Card>

        {rows && rows.length > 0 && (
          <Card><CardContent>
            <div className="overflow-auto rounded-[var(--radius-app)] border border-border">
              <table className="w-full border-collapse text-sm">
                <thead className="sticky top-0 bg-brand text-white">
                  <tr>
                    <th className="px-2 py-1.5 text-left font-semibold">Metric</th>
                    {rows.map((r) => <th key={r.subject_id} className="px-2 py-1.5 text-right font-semibold">{r.player}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {METRICS.map((met) => (
                    <tr key={met.key} className="odd:bg-muted/30">
                      <td className="px-2 py-1 text-left">{met.label}</td>
                      {rows.map((r) => {
                        const v = r[met.key] as number | null;
                        const isBest = v !== null && rows.length > 1 && Number(v) === best[met.key] && Number(v) > 0;
                        return (
                          <td key={r.subject_id} className={`px-2 py-1 text-right tabular-nums ${isBest ? "font-semibold text-brand" : ""}`}>
                            {v === null || v === undefined ? "—" : met.dp != null ? Number(v).toFixed(met.dp) : String(v)}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-2 text-xs text-muted-foreground">Figures share the same scope for every captain; the leading value in each row is highlighted.</p>
          </CardContent></Card>
        )}
      </div>
    </AppShell>
  );
}
