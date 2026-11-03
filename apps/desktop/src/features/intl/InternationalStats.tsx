/**
 * International statistics — per-format (Test / ODI / T20I) leaderboards.
 *
 * International cricket is reported by format, so this screen never pools formats: you pick a format and
 * a discipline and see that format's leaderboard, straight from the approved-scorecard ledger via the
 * /intl-stats API (which reuses the statistics engine). Every honesty flag the engine carries is shown:
 * a runs/wickets total that includes innings with unknown components is marked as a known minimum (≥),
 * and a strike-rate/economy computed over only part of a career is flagged. Until matches are imported
 * and approved the ledger is empty, so a leaderboard is genuinely empty — never a fabricated ranking.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { BarChart3 } from "lucide-react";
import { AppShell } from "../../components/layout/AppShell";
import { EmptyState } from "../../components/states/States";
import { api, ApiError, type IntlFormat, type IntlLeaderRow, type Person } from "../../lib/api";
import { useWorkspace } from "../../lib/workspace-context";

const FORMATS: { key: IntlFormat; label: string }[] = [
  { key: "test", label: "Test" },
  { key: "odi", label: "ODI" },
  { key: "t20i", label: "T20I" },
];
const DISCIPLINES = [
  { key: "batting", label: "Batting" },
  { key: "bowling", label: "Bowling" },
  { key: "fielding", label: "Fielding" },
];

interface Col {
  key: string;
  label: string;
  /** render the cell, given the row; may apply honesty flags */
  cell: (r: IntlLeaderRow) => string;
  align?: "left" | "right";
}

const num = (v: unknown): string => (v == null ? "—" : String(v));
/** A count that may include innings with unknown components reads as a known minimum (≥). */
const minCount = (v: unknown, known_minimum: unknown): string =>
  v == null ? "—" : `${known_minimum ? "≥" : ""}${v}`;
/** A rate computed over only part of a career is flagged with an asterisk. */
const rate = (v: unknown, incomplete: unknown): string =>
  v == null ? "—" : `${v}${incomplete ? "*" : ""}`;

const COLUMNS: Record<string, Col[]> = {
  batting: [
    { key: "matches", label: "M", cell: (r) => num(r.matches), align: "right" },
    { key: "innings", label: "Inns", cell: (r) => num(r.innings), align: "right" },
    { key: "runs", label: "Runs", cell: (r) => minCount(r.runs, r.runs_known_minimum), align: "right" },
    { key: "highest_score", label: "HS", cell: (r) => num(r.highest_score), align: "right" },
    { key: "average", label: "Avg", cell: (r) => num(r.average), align: "right" },
    { key: "strike_rate", label: "SR", cell: (r) => rate(r.strike_rate, r.balls_incomplete), align: "right" },
    { key: "hundreds", label: "100s", cell: (r) => num(r.hundreds), align: "right" },
    { key: "fifties", label: "50s", cell: (r) => num(r.fifties), align: "right" },
    { key: "ducks", label: "0s", cell: (r) => num(r.ducks), align: "right" },
  ],
  bowling: [
    { key: "matches", label: "M", cell: (r) => num(r.matches), align: "right" },
    { key: "overs", label: "Overs", cell: (r) => num(r.overs), align: "right" },
    { key: "runs", label: "Runs", cell: (r) => num(r.runs), align: "right" },
    { key: "wickets", label: "Wkts", cell: (r) => minCount(r.wickets, r.wickets_known_minimum), align: "right" },
    { key: "average", label: "Avg", cell: (r) => num(r.average), align: "right" },
    { key: "economy", label: "Econ", cell: (r) => rate(r.economy, r.economy_incomplete), align: "right" },
    { key: "five_wkt_innings", label: "5wi", cell: (r) => num(r.five_wkt_innings), align: "right" },
    { key: "best_match_wickets", label: "Best (match wkts)", cell: (r) => num(r.best_match_wickets), align: "right" },
  ],
  fielding: [
    { key: "matches", label: "M", cell: (r) => num(r.matches), align: "right" },
    { key: "catches", label: "Catches", cell: (r) => num(r.catches), align: "right" },
    { key: "stumpings", label: "Stumpings", cell: (r) => num(r.stumpings), align: "right" },
    { key: "run_out_involvements", label: "Run-outs", cell: (r) => num(r.run_out_involvements), align: "right" },
    { key: "keeper_dismissals", label: "WK dismissals", cell: (r) => num(r.keeper_dismissals), align: "right" },
  ],
};

export function InternationalStats() {
  const { current } = useWorkspace();
  const workspaceId = current?.id ?? null;

  const [fmt, setFmt] = useState<IntlFormat>("test");
  const [discipline, setDiscipline] = useState("batting");
  const [rows, setRows] = useState<IntlLeaderRow[] | null>(null);
  const [names, setNames] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  // People are resolved once (subject_id -> display name); a leaderboard only lists ids.
  useEffect(() => {
    if (!workspaceId) return;
    let live = true;
    void (async () => {
      try {
        const people: Person[] = await api.listPeople(workspaceId);
        if (live) setNames(Object.fromEntries(people.map((p) => [p.id, p.display_name])));
      } catch {
        /* names are a convenience; the table still renders with ids */
      }
    })();
    return () => { live = false; };
  }, [workspaceId]);

  const load = useCallback(async () => {
    if (!workspaceId) return;
    setRows(null);
    setError(null);
    try {
      setRows(await api.intlLeaders(workspaceId, fmt, discipline, { limit: 100 }));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load the leaderboard.");
    }
  }, [workspaceId, fmt, discipline]);

  useEffect(() => { void load(); }, [load]);

  const cols = COLUMNS[discipline] ?? COLUMNS.batting;
  const anyFlag = useMemo(
    () => (rows ?? []).some((r) => r.runs_known_minimum || r.balls_incomplete || r.wickets_known_minimum || r.economy_incomplete),
    [rows],
  );

  if (!current) {
    return (
      <AppShell title="International Statistics" subtitle="Per-format Test / ODI / T20I leaderboards">
        <EmptyState title="No workspace selected" description="Choose a workspace to continue." />
      </AppShell>
    );
  }

  return (
    <AppShell title="International Statistics" subtitle="Per-format Test / ODI / T20I leaderboards">
      <div className="mx-auto flex max-w-5xl flex-col gap-4">
        <div className="flex items-center gap-2">
          <BarChart3 className="h-5 w-5 text-brand" aria-hidden />
          <h3 className="text-sm font-semibold">Leaderboards</h3>
        </div>

        {/* Format tabs */}
        <div className="flex flex-wrap gap-1" role="tablist" aria-label="Format">
          {FORMATS.map((f) => (
            <button key={f.key} type="button" role="tab" aria-selected={fmt === f.key}
              onClick={() => setFmt(f.key)}
              className={`rounded-[var(--radius-app)] px-3 py-1.5 text-sm font-medium ${
                fmt === f.key ? "bg-brand text-white" : "border border-border text-muted-foreground hover:border-brand hover:text-brand"
              }`}>
              {f.label}
            </button>
          ))}
        </div>

        {/* Discipline tabs */}
        <div className="flex flex-wrap gap-1" role="tablist" aria-label="Discipline">
          {DISCIPLINES.map((d) => (
            <button key={d.key} type="button" role="tab" aria-selected={discipline === d.key}
              onClick={() => setDiscipline(d.key)}
              className={`rounded-full px-3 py-1 text-xs font-medium ${
                discipline === d.key ? "bg-muted text-foreground" : "text-muted-foreground hover:text-foreground"
              }`}>
              {d.label}
            </button>
          ))}
        </div>

        {error && <p className="rounded-[var(--radius-app)] border border-danger/40 bg-danger/10 p-2 text-xs text-danger">{error}</p>}

        {rows === null ? (
          <p className="text-xs text-muted-foreground">Loading…</p>
        ) : rows.length === 0 ? (
          <EmptyState
            title="No statistics yet"
            description="No approved international scorecards for this format yet. Leaderboards appear here once matches are imported and approved — no figures are shown until then."
          />
        ) : (
          <div className="overflow-x-auto rounded-[var(--radius-app)] border border-border">
            <table className="w-full text-sm">
              <thead className="bg-muted text-left text-xs text-muted-foreground">
                <tr>
                  <th className="px-2 py-1.5">#</th>
                  <th className="px-2 py-1.5">Player</th>
                  {cols.map((c) => (
                    <th key={c.key} className={`px-2 py-1.5 ${c.align === "right" ? "text-right" : ""}`}>{c.label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={String(r.subject_id) + i} className="border-t border-border">
                    <td className="px-2 py-1.5 text-muted-foreground">{i + 1}</td>
                    <td className="px-2 py-1.5 font-medium">
                      {names[String(r.subject_id)] ?? `${String(r.subject_id).slice(0, 8)}…`}
                      {r.qualified === false && <span className="ml-1 text-[11px] text-muted-foreground">(unqualified)</span>}
                    </td>
                    {cols.map((c) => (
                      <td key={c.key} className={`px-2 py-1.5 ${c.align === "right" ? "text-right tabular-nums" : ""}`}>{c.cell(r)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {anyFlag && (
          <p className="text-[11px] text-muted-foreground">
            ≥ a total that includes innings with unknown components (a known minimum, never guessed). ·
            * a rate (strike rate / economy) computed over only the part of the career with recorded
            balls/overs.
          </p>
        )}
      </div>
    </AppShell>
  );
}
