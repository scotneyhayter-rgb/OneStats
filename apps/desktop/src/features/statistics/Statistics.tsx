/**
 * Statistics (Phase 12) — professional on-screen reports from the one deterministic engine, with
 * consistent filters and one-click PDF export (the PDF carries the same figures). Right-aligned
 * numeric columns, fixed decimals, sticky header, client-side sorting, qualification-aware.
 */
import { Download, RefreshCw, Save, Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AppShell } from "../../components/layout/AppShell";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import { Select } from "../../components/ui/select";
import { api, ApiError, type Competition, type Grade, type Organisation, type Season, type StatColumn, type StatReport, type Team, type Venue } from "../../lib/api";
import { openBlobUrl } from "../../lib/utils";
import { useWorkspace } from "../../lib/workspace-context";

const REPORTS = [
  { key: "batting", label: "Batting" },
  { key: "bowling", label: "Bowling" },
  { key: "fielding", label: "Fielding & WK" },
  { key: "captaincy", label: "Captaincy" },
  { key: "participation", label: "Appearances" },
  { key: "teams", label: "Teams" },
];

const SPLITS = [
  { value: "", label: "All matches" },
  { value: "home_away", label: "Home & Away" },
  { value: "finals", label: "Finals (excl. GF)" },
  { value: "grand_final", label: "Grand Finals" },
];

function fmt(value: unknown, col: StatColumn): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (col.decimals != null && typeof value === "number") return value.toFixed(col.decimals);
  return String(value);
}

export function Statistics() {
  const { current } = useWorkspace();
  const [report, setReport] = useState("batting");
  const [data, setData] = useState<StatReport | null>(null);
  const [competitions, setCompetitions] = useState<Competition[]>([]);
  const [competitionId, setCompetitionId] = useState("");
  const [organisations, setOrganisations] = useState<Organisation[]>([]);
  const [teams, setTeams] = useState<Team[]>([]);
  const [venues, setVenues] = useState<Venue[]>([]);
  const [venueId, setVenueId] = useState("");   // a specific ground (distinct from the home/away split)
  const [grades, setGrades] = useState<Grade[]>([]);
  const [seasons, setSeasons] = useState<Season[]>([]);
  const [organisationId, setOrganisationId] = useState("");
  // Master club scope: the workspace's primary club (auto-detected) and whether the default has been applied.
  const [primaryClub, setPrimaryClub] = useState<{ organisation_id?: string; name?: string }>({});
  const scopeApplied = useRef(false);
  const reqSeq = useRef(0);   // monotonic request id; only the latest report response may render
  const [gradeId, setGradeId] = useState("");
  const [teamId, setTeamId] = useState("");
  const [oppositionOrgId, setOppositionOrgId] = useState("");   // stats against a chosen opposition club
  const [seasonId, setSeasonId] = useState("");
  const [split, setSplit] = useState("");
  const [venue, setVenue] = useState("");
  const [format, setFormat] = useState("");
  const [formats, setFormats] = useState<string[]>([]);
  const [minThreshold, setMinThreshold] = useState("");
  const [minInnings, setMinInnings] = useState("");   // user-adjustable qualification (batting/bowling)
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<1 | -1>(-1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<Awaited<ReturnType<typeof api.statsSavedList>>>([]);
  const [selectedSaved, setSelectedSaved] = useState("");

  const loadSaved = useCallback(() => {
    if (current) api.statsSavedList(current.id).then(setSaved).catch(() => {});
  }, [current]);
  useEffect(() => {
    if (current) api.listCompetitions(current.id).then(setCompetitions).catch(() => {});
    if (current) api.statsUsedFormats(current.id).then(setFormats).catch(() => setFormats([]));
    if (current) api.listOrganisations(current.id).then(setOrganisations).catch(() => setOrganisations([]));
    if (current) api.listTeams(current.id).then(setTeams).catch(() => setTeams([]));
    if (current) api.listVenues(current.id).then(setVenues).catch(() => setVenues([]));
    if (current) api.statsPrimaryClub(current.id).then(setPrimaryClub).catch(() => setPrimaryClub({}));
    loadSaved();
  }, [current, loadSaved]);

  // Master filter default: on entering a workspace, scope the stats to the user's last choice, or — first
  // time — to the primary club ("show my club"). The user can switch to All clubs or any specific club.
  useEffect(() => { scopeApplied.current = false; }, [current]);
  useEffect(() => {
    if (!current || scopeApplied.current) return;
    let saved: string | null = null;
    try { saved = localStorage.getItem(`stats-club-${current.id}`); } catch { /* storage unavailable */ }
    if (saved !== null) { setOrganisationId(saved); scopeApplied.current = true; }
    else if (primaryClub.organisation_id) { setOrganisationId(primaryClub.organisation_id); scopeApplied.current = true; }
  }, [current, primaryClub]);

  // Change the club scope and remember it per workspace, so the master filter sticks across visits.
  const setClub = useCallback((orgId: string) => {
    setOrganisationId(orgId);
    try { if (current) localStorage.setItem(`stats-club-${current.id}`, orgId); } catch { /* storage unavailable */ }
  }, [current]);

  // Grades and seasons belong to a competition — load them when one is chosen, and clear the picks.
  useEffect(() => {
    if (current && competitionId) {
      api.getCompetition(current.id, competitionId)
        .then((c) => { setGrades(c.grades ?? []); setSeasons(c.seasons ?? []); })
        .catch(() => { setGrades([]); setSeasons([]); });
    } else {
      setGrades([]); setSeasons([]);
    }
    setGradeId(""); setSeasonId("");
  }, [current, competitionId]);

  const applySaved = (id: string) => {
    setSelectedSaved(id);
    const s = saved.find((x) => x.id === id);
    if (!s) return;
    const cfg = (s.config ?? {}) as Record<string, string | number>;
    setReport(s.report);
    setCompetitionId(String(cfg.competition_id ?? ""));
    setOrganisationId(String(cfg.organisation_id ?? ""));
    setTeamId(String(cfg.team_id ?? ""));
    setOppositionOrgId(String(cfg.opposition_organisation_id ?? ""));
    setVenueId(String(cfg.venue_id ?? ""));
    // grade/season depend on the competition's loaded lists; reselect them after choosing a competition
    setSplit(String(cfg.split ?? ""));
    setVenue(String(cfg.venue ?? ""));
    setFormat(String(cfg.format ?? ""));
    setMinThreshold(String(cfg.min_runs ?? cfg.min_wickets ?? cfg.min_eligible ?? ""));
    setMinInnings(String(cfg.min_innings ?? ""));
  };

  const saveCurrent = async () => {
    if (!current) return;
    const name = window.prompt("Save this report as:");
    if (!name) return;
    const config: Record<string, unknown> = { competition_id: competitionId || undefined,
      organisation_id: organisationId || undefined, grade_id: gradeId || undefined,
      team_id: teamId || undefined, season_id: seasonId || undefined,
      opposition_organisation_id: oppositionOrgId || undefined, venue_id: venueId || undefined,
      split: split || undefined, venue: venue || undefined, format: format || undefined };
    if (minThreshold) {
      if (report === "batting") config.min_runs = Number(minThreshold);
      else if (report === "bowling") config.min_wickets = Number(minThreshold);
      else if (report === "captaincy") config.min_eligible = Number(minThreshold);
    }
    if (minInnings && (report === "batting" || report === "bowling")) config.min_innings = Number(minInnings);
    try {
      await api.statsSaveReport(current.id, { name, report, config });
      loadSaved();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not save the report.");
    }
  };

  const deleteSaved = async () => {
    if (!current || !selectedSaved) return;
    try {
      await api.statsDeleteSaved(current.id, selectedSaved);
      setSelectedSaved("");
      loadSaved();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not delete (only the owner may).");
    }
  };

  const query = useMemo(() => {
    const q: Record<string, string | number | undefined> = {
      competition_id: competitionId || undefined, organisation_id: organisationId || undefined,
      grade_id: gradeId || undefined, team_id: teamId || undefined, season_id: seasonId || undefined,
      opposition_organisation_id: oppositionOrgId || undefined, venue_id: venueId || undefined,
      split: split || undefined, venue: venue || undefined, format: format || undefined,
    };
    if (minThreshold) {
      if (report === "batting") q.min_runs = Number(minThreshold);
      else if (report === "bowling") q.min_wickets = Number(minThreshold);
      else if (report === "captaincy") q.min_eligible = Number(minThreshold);
    }
    if (minInnings && (report === "batting" || report === "bowling")) q.min_innings = Number(minInnings);
    return q;
  }, [competitionId, organisationId, gradeId, teamId, oppositionOrgId, venueId, seasonId, split, venue, format, minThreshold, minInnings, report]);

  const load = useCallback(async () => {
    if (!current) return;
    // Guard against out-of-order responses: the report fires once on the default (unscoped) query and
    // again once the club scope is applied. Only the latest request's result may win, so a stale unscoped
    // response can never overwrite the scoped figures.
    const seq = ++reqSeq.current;
    setBusy(true);
    setError(null);
    try {
      const d = await api.statsReport(current.id, report, query);
      if (seq === reqSeq.current) setData(d);
    } catch (e) {
      if (seq === reqSeq.current) setError(e instanceof ApiError ? e.message : "Could not load the report.");
    } finally {
      if (seq === reqSeq.current) setBusy(false);
    }
  }, [current, report, query]);
  useEffect(() => {
    void load();
  }, [load]);

  const exportPdf = async () => {
    if (!current) return;
    try {
      openBlobUrl(await api.statsReportPdfUrl(current.id, report, query), `${report}.pdf`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "PDF export failed.");
    }
  };

  const rows = useMemo(() => {
    if (!data) return [];
    // When a qualification threshold is set, drop players the engine flagged unqualified, so a rate
    // ranking (average/strike rate) is never topped by a tiny-sample player.
    const hasThreshold = Boolean(minThreshold || minInnings);
    const base = hasThreshold ? data.rows.filter((r) => r["qualified"] !== false) : data.rows;
    if (!sortKey) return base;
    const r = [...base];
    r.sort((a, b) => {
      const av = a[sortKey] as number | string | null;
      const bv = b[sortKey] as number | string | null;
      if (av === null || av === undefined) return 1;
      if (bv === null || bv === undefined) return -1;
      if (typeof av === "number" && typeof bv === "number") return (av - bv) * sortDir;
      return String(av).localeCompare(String(bv)) * sortDir;
    });
    return r;
  }, [data, sortKey, sortDir, minThreshold, minInnings]);

  if (!current) {
    return (
      <AppShell title="Statistics" subtitle="Select or create a workspace">
        <Card><CardContent><p className="text-sm text-muted-foreground">No workspace selected.</p></CardContent></Card>
      </AppShell>
    );
  }

  const toggleSort = (key: string) => {
    if (sortKey === key) setSortDir((d) => (d === 1 ? -1 : 1));
    else { setSortKey(key); setSortDir(-1); }
  };

  const clearAll = () => {
    setCompetitionId(""); setGradeId(""); setSeasonId(""); setTeamId("");
    setOppositionOrgId(""); setVenueId(""); setSplit(""); setVenue(""); setFormat("");
    setMinInnings(""); setMinThreshold("");   // club scope is the master default, left intact
  };
  // Active filters, shown as removable chips so a filtered report is never mistaken for all-time.
  const activeChips = [
    competitionId && { label: `Comp: ${competitions.find((c) => c.id === competitionId)?.name ?? "—"}`, clear: () => setCompetitionId("") },
    gradeId && { label: `Grade: ${grades.find((g) => g.id === gradeId)?.name ?? "—"}`, clear: () => setGradeId("") },
    seasonId && { label: `Season: ${seasons.find((s) => s.id === seasonId)?.label ?? "—"}`, clear: () => setSeasonId("") },
    organisationId && { label: `Club: ${organisations.find((o) => o.id === organisationId)?.name ?? "—"}`, clear: () => setClub("") },
    teamId && { label: `Team: ${teams.find((t) => t.id === teamId)?.name ?? "—"}`, clear: () => setTeamId("") },
    oppositionOrgId && { label: `vs ${organisations.find((o) => o.id === oppositionOrgId)?.name ?? "—"}`, clear: () => setOppositionOrgId("") },
    venueId && { label: `Ground: ${venues.find((v) => v.id === venueId)?.name ?? "—"}`, clear: () => setVenueId("") },
    split && { label: SPLITS.find((s) => s.value === split)?.label ?? split, clear: () => setSplit("") },
    venue && { label: venue === "home" ? "Home only" : "Away only", clear: () => setVenue("") },
    format && { label: `Format: ${format}`, clear: () => setFormat("") },
    minInnings && (report === "batting" || report === "bowling") && { label: `Min innings: ${minInnings}`, clear: () => setMinInnings("") },
    minThreshold && { label: `${report === "batting" ? "Min runs" : report === "bowling" ? "Min wickets" : "Min eligible"}: ${minThreshold}`, clear: () => setMinThreshold("") },
  ].filter(Boolean) as { label: string; clear: () => void }[];

  return (
    <AppShell title="Statistics" subtitle={current.name}>
      <div className="mx-auto flex max-w-5xl flex-col gap-4">
        {error && <p className="rounded-[var(--radius-app)] border border-danger/40 bg-danger/5 px-3 py-2 text-sm text-danger">{error}</p>}

        <div className="flex items-center justify-between gap-2">
          <p className="text-xs text-muted-foreground">Core leaderboards with full filters. For the complete library of reports, open the catalogue.</p>
          <div className="flex items-center gap-2">
            <a href="#/statistics/compare"
              className="whitespace-nowrap rounded-[var(--radius-app)] border border-border px-3 py-1.5 text-sm font-medium hover:border-brand">
              Compare players →
            </a>
            <a href="#/statistics/catalogue"
              className="whitespace-nowrap rounded-[var(--radius-app)] border border-brand bg-brand/10 px-3 py-1.5 text-sm font-medium text-brand">
              Report Catalogue →
            </a>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {REPORTS.map((r) => (
            <button key={r.key} type="button" onClick={() => { setReport(r.key); setSortKey(null); }}
              className={`rounded-[var(--radius-app)] border px-3 py-1.5 text-sm ${
                report === r.key ? "border-brand bg-brand/10 font-medium text-brand" : "border-border text-muted-foreground"}`}>
              {r.label}
            </button>
          ))}
        </div>

        <Card><CardContent className="flex flex-col gap-3">
          <div className="flex flex-wrap items-end gap-2 text-xs">
            <label className="flex flex-col gap-1">
              <span className="text-muted-foreground">Saved report</span>
              <Select value={selectedSaved} onChange={(e) => applySaved(e.target.value)} className="w-48">
                <option value="">— open a saved report —</option>
                {saved.map((s) => <option key={s.id} value={s.id}>{s.name}{s.shared ? " (shared)" : ""}</option>)}
              </Select>
            </label>
            <Button size="sm" variant="outline" onClick={() => void saveCurrent()}>
              <Save className="h-4 w-4" aria-hidden /> Save
            </Button>
            {selectedSaved && (
              <Button size="sm" variant="outline" onClick={() => void deleteSaved()}>
                <Trash2 className="h-4 w-4" aria-hidden /> Delete
              </Button>
            )}
          </div>
          {primaryClub.organisation_id && (
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="text-muted-foreground">Show</span>
              <Button size="sm" variant={organisationId === primaryClub.organisation_id ? "primary" : "outline"}
                onClick={() => setClub(primaryClub.organisation_id!)}>
                {primaryClub.name ?? "My club"}
              </Button>
              <Button size="sm" variant={organisationId === "" ? "primary" : "outline"} onClick={() => setClub("")}>
                All clubs
              </Button>
              {organisationId && organisationId !== primaryClub.organisation_id && (
                <span className="text-xs text-muted-foreground">· filtered to a specific club below</span>
              )}
            </div>
          )}
          <div className="flex flex-wrap items-end gap-2 text-xs">
            <label className="flex flex-col gap-1">
              <span className="text-muted-foreground">Competition</span>
              <Select value={competitionId} onChange={(e) => setCompetitionId(e.target.value)} className="w-44">
                <option value="">All competitions</option>
                {competitions.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </Select>
            </label>
            {grades.length > 0 && (
              <label className="flex flex-col gap-1">
                <span className="text-muted-foreground">Grade</span>
                <Select value={gradeId} onChange={(e) => setGradeId(e.target.value)} className="w-36">
                  <option value="">All grades</option>
                  {grades.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
                </Select>
              </label>
            )}
            {seasons.length > 0 && (
              <label className="flex flex-col gap-1">
                <span className="text-muted-foreground">Season</span>
                <Select value={seasonId} onChange={(e) => setSeasonId(e.target.value)} className="w-32">
                  <option value="">All seasons</option>
                  {seasons.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
                </Select>
              </label>
            )}
            {organisations.length > 0 && (
              <label className="flex flex-col gap-1">
                <span className="text-muted-foreground">Club</span>
                <Select value={organisationId} onChange={(e) => setClub(e.target.value)} className="w-44">
                  <option value="">All clubs</option>
                  {organisations.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
                </Select>
              </label>
            )}
            {teams.length > 0 && (
              <label className="flex flex-col gap-1">
                <span className="text-muted-foreground">Team</span>
                <Select value={teamId} onChange={(e) => setTeamId(e.target.value)} className="w-44">
                  <option value="">All teams</option>
                  {teams.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                </Select>
              </label>
            )}
            {organisations.length > 1 && (
              <label className="flex flex-col gap-1">
                <span className="text-muted-foreground">Opposition</span>
                <Select value={oppositionOrgId} onChange={(e) => setOppositionOrgId(e.target.value)} className="w-44">
                  <option value="">Any opposition</option>
                  {organisations.filter((o) => o.id !== organisationId).map((o) => <option key={o.id} value={o.id}>vs {o.name}</option>)}
                </Select>
              </label>
            )}
            <label className="flex flex-col gap-1">
              <span className="text-muted-foreground">Matches</span>
              <Select value={split} onChange={(e) => setSplit(e.target.value)} className="w-40">
                {SPLITS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
              </Select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-muted-foreground">Venue</span>
              <Select value={venue} onChange={(e) => setVenue(e.target.value)} className="w-28">
                <option value="">All</option>
                <option value="home">Home</option>
                <option value="away">Away</option>
              </Select>
            </label>
            {venues.length > 0 && (
              <label className="flex flex-col gap-1">
                <span className="text-muted-foreground">Ground</span>
                <Select value={venueId} onChange={(e) => setVenueId(e.target.value)} className="w-44">
                  <option value="">All grounds</option>
                  {venues.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
                </Select>
              </label>
            )}
            {formats.length > 0 && (
              <label className="flex flex-col gap-1">
                <span className="text-muted-foreground">Format</span>
                <Select value={format} onChange={(e) => setFormat(e.target.value)} className="w-44">
                  <option value="">All formats</option>
                  {formats.map((fmt) => <option key={fmt} value={fmt}>{fmt}</option>)}
                </Select>
              </label>
            )}
            {(report === "batting" || report === "bowling") && (
              <label className="flex flex-col gap-1">
                <span className="text-muted-foreground">Min innings</span>
                <input value={minInnings} onChange={(e) => setMinInnings(e.target.value)} type="number"
                  placeholder="e.g. 10"
                  className="w-24 rounded-[var(--radius-app)] border border-border bg-background px-2 py-1" />
              </label>
            )}
            {(report === "batting" || report === "bowling" || report === "captaincy") && (
              <label className="flex flex-col gap-1">
                <span className="text-muted-foreground">
                  {report === "batting" ? "Min runs" : report === "bowling" ? "Min wickets" : "Min eligible"}
                </span>
                <input value={minThreshold} onChange={(e) => setMinThreshold(e.target.value)} type="number"
                  className="w-24 rounded-[var(--radius-app)] border border-border bg-background px-2 py-1" />
              </label>
            )}
            <Button size="sm" variant="outline" disabled={busy} onClick={() => void load()}>
              <RefreshCw className="h-4 w-4" aria-hidden /> Refresh
            </Button>
            <Button size="sm" className="ml-auto" disabled={busy || !data?.rows.length} onClick={() => void exportPdf()}>
              <Download className="h-4 w-4" aria-hidden /> Export PDF
            </Button>
          </div>

          {activeChips.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-xs text-muted-foreground">Filters:</span>
              {activeChips.map((c, i) => (
                <span key={i} className="inline-flex items-center gap-1 rounded-full border border-brand bg-brand/10 px-2 py-0.5 text-xs text-brand">
                  {c.label}
                  <button type="button" aria-label={`Clear ${c.label}`} className="hover:text-danger" onClick={c.clear}>×</button>
                </span>
              ))}
              <button type="button" className="text-xs text-muted-foreground underline hover:text-foreground" onClick={clearAll}>Clear all</button>
            </div>
          )}

          <h3 className="text-sm font-semibold">{data?.title ?? "Report"}</h3>
          {data && data.rows.length === 0 && (
            <p className="text-xs text-muted-foreground">No approved data for these filters yet.</p>
          )}
          {data && data.rows.length > 0 && (
            <div className="max-h-[32rem] overflow-auto rounded-[var(--radius-app)] border border-border">
              <table className="w-full border-collapse text-sm">
                <thead className="sticky top-0 bg-brand text-white">
                  <tr>
                    {data.columns.map((c) => (
                      <th key={c.key} onClick={() => toggleSort(c.key)}
                        className={`cursor-pointer whitespace-nowrap px-2 py-1.5 font-semibold ${c.align === "right" ? "text-right" : "text-left"}`}>
                        {c.label}{sortKey === c.key ? (sortDir === 1 ? " ▲" : " ▼") : ""}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => (
                    <tr key={i} className={i % 2 ? "bg-muted/30" : ""}>
                      {data.columns.map((c) => (
                        <td key={c.key} className={`whitespace-nowrap px-2 py-1 tabular-nums ${c.align === "right" ? "text-right" : "text-left"}`}>
                          {fmt(r[c.key], c)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="text-xs text-muted-foreground">
            Official statistics from approved scorecards only. Unknown values are never treated as zero; strike/economy
            rates use recorded balls only. Averages are runs ÷ dismissals.
          </p>
        </CardContent></Card>
      </div>
    </AppShell>
  );
}
