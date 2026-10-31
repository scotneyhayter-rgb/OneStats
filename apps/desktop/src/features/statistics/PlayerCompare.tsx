/**
 * Player Compare — two or more players side by side on batting, bowling, fielding and captaincy, under the
 * same filters, from the one engine (figures match the individual reports). A capability neither CricketStatz
 * nor the old OneStats had (audit Deliverable F). Best value per row is highlighted; unknown stays "—".
 */
import { Download, Plus, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AppShell } from "../../components/layout/AppShell";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import { Input } from "../../components/ui/input";
import { Select } from "../../components/ui/select";
import { api, ApiError, type ComparePlayer, type Competition, type Grade, type Organisation, type Person, type Season } from "../../lib/api";
import { useWorkspace } from "../../lib/workspace-context";

type Dir = "hi" | "lo" | "none";
type Row = { label: string; group: "batting" | "bowling" | "fielding" | "captaincy"; key: string; dir: Dir; dec?: number };
const ROWS: Row[] = [
  { label: "Matches", group: "batting", key: "matches", dir: "none" },
  { label: "Innings", group: "batting", key: "innings", dir: "none" },
  { label: "Runs", group: "batting", key: "runs", dir: "hi" },
  { label: "Average", group: "batting", key: "average", dir: "hi", dec: 2 },
  { label: "High score", group: "batting", key: "highest_score", dir: "hi" },
  { label: "50s", group: "batting", key: "fifties", dir: "hi" },
  { label: "100s", group: "batting", key: "hundreds", dir: "hi" },
  { label: "Strike rate", group: "batting", key: "strike_rate", dir: "hi", dec: 2 },
  { label: "Wickets", group: "bowling", key: "wickets", dir: "hi" },
  { label: "Average", group: "bowling", key: "average", dir: "lo", dec: 2 },
  { label: "Economy", group: "bowling", key: "economy", dir: "lo", dec: 2 },
  { label: "5 wkt inns", group: "bowling", key: "five_wkt_innings", dir: "hi" },
  { label: "Catches", group: "fielding", key: "catches", dir: "hi" },
  { label: "Stumpings", group: "fielding", key: "stumpings", dir: "hi" },
  { label: "Run outs", group: "fielding", key: "run_outs", dir: "hi" },
  { label: "Captained", group: "captaincy", key: "captained", dir: "hi" },
  { label: "Wins", group: "captaincy", key: "wins", dir: "hi" },
  { label: "Win %", group: "captaincy", key: "win_pct", dir: "hi", dec: 1 },
];
const GROUPS: { key: Row["group"]; label: string }[] = [
  { key: "batting", label: "Batting" }, { key: "bowling", label: "Bowling" },
  { key: "fielding", label: "Fielding" }, { key: "captaincy", label: "Captaincy" },
];

export function PlayerCompare() {
  const { current } = useWorkspace();
  const workspaceId = current?.id;
  const [sel, setSel] = useState<{ id: string; name: string }[]>([]);
  const [term, setTerm] = useState("");
  const [results, setResults] = useState<Person[]>([]);
  const [orgs, setOrgs] = useState<Organisation[]>([]);
  const [comps, setComps] = useState<Competition[]>([]);
  const [grades, setGrades] = useState<Grade[]>([]);
  const [seasons, setSeasons] = useState<Season[]>([]);
  const [competitionId, setCompetitionId] = useState("");
  const [gradeId, setGradeId] = useState("");
  const [seasonId, setSeasonId] = useState("");
  const [oppositionOrgId, setOppositionOrgId] = useState("");
  const [data, setData] = useState<ComparePlayer[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!workspaceId) return;
    api.listOrganisations(workspaceId).then(setOrgs).catch(() => setOrgs([]));
    api.listCompetitions(workspaceId).then(setComps).catch(() => setComps([]));
  }, [workspaceId]);

  useEffect(() => {
    if (workspaceId && competitionId) {
      api.getCompetition(workspaceId, competitionId)
        .then((c) => { setGrades(c.grades ?? []); setSeasons(c.seasons ?? []); })
        .catch(() => { setGrades([]); setSeasons([]); });
    } else { setGrades([]); setSeasons([]); }
    setGradeId(""); setSeasonId("");
  }, [workspaceId, competitionId]);

  useEffect(() => {
    const q = term.trim();
    if (!workspaceId || q.length < 2) { setResults([]); return; }
    let live = true;
    api.listPeople(workspaceId, { search: q })
      .then((p) => { if (live) setResults(p.filter((x) => !x.merged_into_id && !sel.some((s) => s.id === x.id)).slice(0, 8)); })
      .catch(() => { if (live) setResults([]); });
    return () => { live = false; };
  }, [term, workspaceId, sel]);

  const filters = useMemo(() => ({
    competition_id: competitionId || undefined, grade_id: gradeId || undefined, season_id: seasonId || undefined,
    opposition_organisation_id: oppositionOrgId || undefined,
  }), [competitionId, gradeId, seasonId, oppositionOrgId]);

  const run = useCallback(() => {
    if (!workspaceId || sel.length < 2) { setData(null); return; }
    api.statsCompare(workspaceId, sel.map((s) => s.id), filters)
      .then((d) => setData(d.players))
      .catch((e) => setError(e instanceof ApiError ? e.message : "Compare failed."));
  }, [workspaceId, sel, filters]);
  useEffect(() => { run(); }, [run]);

  const add = (p: Person) => { if (sel.length < 6) setSel((s) => [...s, { id: p.id, name: p.display_name }]); setTerm(""); setResults([]); };
  const remove = (id: string) => setSel((s) => s.filter((x) => x.id !== id));

  const fmt = (v: number | null | undefined, dec?: number) =>
    v === null || v === undefined ? "—" : typeof v === "number" && dec !== undefined ? v.toFixed(dec) : String(v);
  const bestIdx = (row: Row): number | null => {
    if (row.dir === "none" || !data) return null;
    let bi: number | null = null, bv: number | null = null;
    data.forEach((p, i) => {
      const v = (p[row.group] as Record<string, number | null>)[row.key];
      if (v === null || v === undefined) return;
      if (bv === null || (row.dir === "hi" ? v > bv : v < bv)) { bv = v; bi = i; }
    });
    return bi;
  };

  const exportCsv = () => {
    if (!data) return;
    const lines = [["Metric", ...data.map((p) => p.name)].join(",")];
    for (const r of ROWS) lines.push([`${r.group}:${r.label}`,
      ...data.map((p) => fmt((p[r.group] as Record<string, number | null>)[r.key], r.dec))].join(","));
    const url = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" }));
    const a = document.createElement("a"); a.href = url; a.download = "player-compare.csv"; a.click(); URL.revokeObjectURL(url);
  };

  if (!current) return <AppShell title="Compare players"><Card><CardContent><p className="text-sm text-muted-foreground">No workspace selected.</p></CardContent></Card></AppShell>;

  return (
    <AppShell title="Compare players" subtitle={current.name}>
      <div className="mx-auto flex max-w-5xl flex-col gap-4">
        <Card><CardContent className="flex flex-col gap-3">
          <p className="text-xs text-muted-foreground">Pick two or more players (up to 6) to compare side by side, under the same filters.</p>
          <div className="flex flex-wrap items-center gap-1.5">
            {sel.map((s) => (
              <span key={s.id} className="inline-flex items-center gap-1 rounded-full border border-brand bg-brand/10 px-2 py-0.5 text-xs text-brand">
                {s.name}
                <button type="button" aria-label={`Remove ${s.name}`} onClick={() => remove(s.id)}><X className="h-3 w-3" aria-hidden /></button>
              </span>
            ))}
            {sel.length < 6 && (
              <div className="relative">
                <Input value={term} onChange={(e) => setTerm(e.target.value)} placeholder="Add a player…" className="h-8 w-44 text-sm" />
                {results.length > 0 && (
                  <div className="absolute z-10 mt-1 w-56 rounded-[var(--radius-app)] border border-border bg-card shadow">
                    {results.map((p) => (
                      <button key={p.id} type="button" onClick={() => add(p)} className="flex w-full items-center gap-1 px-2 py-1 text-left text-sm hover:bg-muted">
                        <Plus className="h-3 w-3" aria-hidden /> {p.display_name}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
          <div className="flex flex-wrap items-end gap-2 text-sm">
            {comps.length > 0 && (
              <label className="flex flex-col gap-1"><span className="text-xs text-muted-foreground">Competition</span>
                <Select value={competitionId} onChange={(e) => setCompetitionId(e.target.value)} className="w-44"><option value="">All</option>
                  {comps.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select></label>
            )}
            {grades.length > 0 && (
              <label className="flex flex-col gap-1"><span className="text-xs text-muted-foreground">Grade</span>
                <Select value={gradeId} onChange={(e) => setGradeId(e.target.value)} className="w-32"><option value="">All</option>
                  {grades.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}</Select></label>
            )}
            {seasons.length > 0 && (
              <label className="flex flex-col gap-1"><span className="text-xs text-muted-foreground">Season</span>
                <Select value={seasonId} onChange={(e) => setSeasonId(e.target.value)} className="w-28"><option value="">All</option>
                  {seasons.map((se) => <option key={se.id} value={se.id}>{se.label}</option>)}</Select></label>
            )}
            {orgs.length > 1 && (
              <label className="flex flex-col gap-1"><span className="text-xs text-muted-foreground">Opposition</span>
                <Select value={oppositionOrgId} onChange={(e) => setOppositionOrgId(e.target.value)} className="w-44"><option value="">Any</option>
                  {orgs.map((o) => <option key={o.id} value={o.id}>vs {o.name}</option>)}</Select></label>
            )}
            {data && data.length > 0 && <Button size="sm" variant="outline" className="ml-auto" onClick={exportCsv}><Download className="h-4 w-4" aria-hidden /> CSV</Button>}
          </div>
          {error && <p className="text-sm text-danger">{error}</p>}
        </CardContent></Card>

        {sel.length < 2 && <p className="text-sm text-muted-foreground">Add at least two players to compare.</p>}

        {data && data.length >= 2 && (
          <Card><CardContent className="overflow-auto p-0">
            <table className="w-full border-collapse text-sm">
              <thead className="sticky top-0 bg-brand text-white">
                <tr><th className="px-3 py-2 text-left">Metric</th>
                  {data.map((p) => <th key={p.person_id} className="px-3 py-2 text-right">{p.name}</th>)}</tr>
              </thead>
              <tbody>
                {GROUPS.map((g) => (
                  <>
                    <tr key={g.key} className="bg-muted/50"><td className="px-3 py-1 text-xs font-semibold uppercase text-muted-foreground" colSpan={data.length + 1}>{g.label}</td></tr>
                    {ROWS.filter((r) => r.group === g.key).map((r) => {
                      const bi = bestIdx(r);
                      return (
                        <tr key={`${g.key}-${r.key}`} className="border-t border-border">
                          <td className="px-3 py-1.5">{r.label}</td>
                          {data.map((p, i) => (
                            <td key={p.person_id} className={`px-3 py-1.5 text-right tabular-nums ${bi === i ? "font-semibold text-brand" : ""}`}>
                              {fmt((p[r.group] as Record<string, number | null>)[r.key], r.dec)}
                            </td>
                          ))}
                        </tr>
                      );
                    })}
                  </>
                ))}
              </tbody>
            </table>
          </CardContent></Card>
        )}
      </div>
    </AppShell>
  );
}
