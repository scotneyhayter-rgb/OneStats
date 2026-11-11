/**
 * Report Catalogue (Phase 12 expansion) — a professional, searchable, categorised library of every
 * ready-made report. Each entry opens a working report from the one deterministic engine, with split
 * filtering and PDF / CSV export. Favourites and recently-used persist per viewer (localStorage).
 */
import { Download, FileText, Search, Star, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AppShell } from "../../components/layout/AppShell";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import { Input } from "../../components/ui/input";
import { Select } from "../../components/ui/select";
import { api, ApiError, type CatalogueReport, type Competition, type Grade, type Organisation, type ReportCatalogue as Catalogue, type StatColumn, type StatReport, type Team, type Venue } from "../../lib/api";
import { openBlobUrl } from "../../lib/utils";
import { useWorkspace } from "../../lib/workspace-context";

const FAV_KEY = "onestats.reportFavourites";
const RECENT_KEY = "onestats.reportRecent";

const SPLITS = [
  { value: "", label: "All matches" },
  { value: "home_away", label: "Home & Away" },
  { value: "finals", label: "Finals (excl. GF)" },
  { value: "grand_final", label: "Grand Finals" },
];

function loadIds(key: string): string[] {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as string[]) : [];
  } catch {
    return [];
  }
}
function saveIds(key: string, ids: string[]): void {
  try {
    localStorage.setItem(key, JSON.stringify(ids.slice(0, 40)));
  } catch {
    /* storage unavailable — favourites/recent are a convenience only */
  }
}

function fmt(value: unknown, col: StatColumn): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (col.decimals != null && typeof value === "number") return value.toFixed(col.decimals);
  return String(value);
}

export function ReportCatalogue() {
  const { current } = useWorkspace();
  const [cat, setCat] = useState<Catalogue | null>(null);
  const [query, setQuery] = useState("");
  const [activeCat, setActiveCat] = useState<string | null>(null);
  const [favs, setFavs] = useState<string[]>(() => loadIds(FAV_KEY));
  const [recent, setRecent] = useState<string[]>(() => loadIds(RECENT_KEY));
  const [open, setOpen] = useState<CatalogueReport | null>(null);
  const [split, setSplit] = useState("");
  const [format, setFormat] = useState("");
  const [formats, setFormats] = useState<string[]>([]);
  const [data, setData] = useState<StatReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Scope filters an opened report honours (the engine applies them identically to the Statistics screen).
  const [competitions, setCompetitions] = useState<Competition[]>([]);
  const [organisations, setOrganisations] = useState<Organisation[]>([]);
  const [teams, setTeams] = useState<Team[]>([]);
  const [venues, setVenues] = useState<Venue[]>([]);
  const [grades, setGrades] = useState<Grade[]>([]);
  const [seasonLabels, setSeasonLabels] = useState<string[]>([]);
  const [primaryClub, setPrimaryClub] = useState<{ organisation_id?: string; name?: string }>({});
  const [competitionId, setCompetitionId] = useState("");
  const [organisationId, setOrganisationId] = useState("");
  const [teamId, setTeamId] = useState("");
  const [venueId, setVenueId] = useState("");
  const [gradeId, setGradeId] = useState("");
  const [seasonLabel, setSeasonLabel] = useState("");

  useEffect(() => {
    if (!current) return;
    api.statsCatalogue(current.id).then(setCat).catch((e) =>
      setError(e instanceof ApiError ? e.message : "Could not load the report catalogue."));
    api.statsUsedFormats(current.id).then(setFormats).catch(() => setFormats([]));
    api.statsUsedSeasons(current.id).then(setSeasonLabels).catch(() => setSeasonLabels([]));
    api.listCompetitions(current.id).then(setCompetitions).catch(() => setCompetitions([]));
    api.listOrganisations(current.id).then(setOrganisations).catch(() => setOrganisations([]));
    api.listTeams(current.id).then(setTeams).catch(() => setTeams([]));
    api.listVenues(current.id).then(setVenues).catch(() => setVenues([]));
    api.statsPrimaryClub(current.id).then(setPrimaryClub).catch(() => setPrimaryClub({}));
    // Depend on the workspace id (a stable string), not the `current` object whose identity changes each render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current?.id]);

  // Grades belong to a competition — load them when one is picked, and clear the pick. (Season is a
  // workspace-wide year filter, not competition-dependent.)
  useEffect(() => {
    if (current && competitionId) {
      api.getCompetition(current.id, competitionId)
        .then((c) => setGrades(c.grades ?? []))
        .catch(() => setGrades([]));
    } else {
      setGrades([]);
    }
    setGradeId("");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current?.id, competitionId]);

  const allReports = useMemo(() => (cat?.categories ?? []).flatMap((c) => c.reports), [cat]);
  const byId = useMemo(() => new Map(allReports.map((r) => [r.id, r])), [allReports]);

  const toggleFav = useCallback((id: string) => {
    setFavs((prev) => {
      const next = prev.includes(id) ? prev.filter((x) => x !== id) : [id, ...prev];
      saveIds(FAV_KEY, next);
      return next;
    });
  }, []);

  // Which scope filters this report honours (declared by the catalogue; the engine applies them).
  const buildQuery = useCallback((r: CatalogueReport): Record<string, string | undefined> => {
    const s = (t: string) => r.filters.includes(t);
    return {
      organisation_id: s("organisation") && organisationId ? organisationId : undefined,
      team_id: s("team") && teamId ? teamId : undefined,
      competition_id: s("competition") && competitionId ? competitionId : undefined,
      grade_id: s("grade") && gradeId ? gradeId : undefined,
      season_label: s("season") && seasonLabel ? seasonLabel : undefined,
      venue_id: s("venue") && venueId ? venueId : undefined,
      split: s("split") && split ? split : undefined,
      format: s("format") && format ? format : undefined,
    };
  }, [organisationId, teamId, competitionId, gradeId, seasonLabel, venueId, split, format]);

  const loadReport = useCallback(async (r: CatalogueReport) => {
    if (!current) return;
    setError(null);
    try {
      setData(await api.statsReport(current.id, r.id, buildQuery(r)));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not open the report.");
      setData(null);
    }
  }, [current, buildQuery]);

  const openReport = useCallback((r: CatalogueReport) => {
    if (r.id === "capt_compare") { window.location.hash = "#/statistics/captaincy-compare"; return; }
    // Reset scope, defaulting the club to the workspace's primary club where the report supports it.
    setSplit(""); setFormat(""); setCompetitionId(""); setTeamId(""); setVenueId(""); setGradeId(""); setSeasonLabel("");
    setOrganisationId(r.filters.includes("organisation") ? (primaryClub.organisation_id ?? "") : "");
    setData(null);
    setOpen(r);
    setRecent((prev) => {
      const next = [r.id, ...prev.filter((x) => x !== r.id)];
      saveIds(RECENT_KEY, next);
      return next;
    });
  }, [primaryClub]);

  const closeReport = useCallback(() => { setOpen(null); setData(null); }, []);

  // Reload whenever the opened report or any of its scope filters change.
  const reportRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (open) void loadReport(open);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open?.id, organisationId, teamId, competitionId, gradeId, seasonLabel, venueId, split, format]);
  useEffect(() => {
    if (open) reportRef.current?.scrollIntoView?.({ behavior: "smooth", block: "start" });
  }, [open?.id]);

  const exportUrl = useCallback(async (kind: "pdf" | "csv") => {
    if (!current || !open) return;
    try {
      const q = buildQuery(open);
      const url = kind === "pdf"
        ? await api.statsReportPdfUrl(current.id, open.id, q)
        : await api.statsReportCsvUrl(current.id, open.id, q);
      openBlobUrl(url, `${open.name}.${kind}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Export failed.");
    }
  }, [current, open, buildQuery]);

  const printIndex = useCallback(async () => {
    if (!current) return;
    try {
      openBlobUrl(await api.statsCatalogueIndexUrl(current.id), "Report Catalogue.pdf");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not open the catalogue index.");
    }
  }, [current]);

  if (!current) return <AppShell title="Report Catalogue" subtitle="Select a workspace"><div /></AppShell>;

  const q = query.trim().toLowerCase();
  const matches = (r: CatalogueReport) =>
    !q || r.name.toLowerCase().includes(q) || r.description.toLowerCase().includes(q) || r.category.toLowerCase().includes(q);

  const visibleCategories = (cat?.categories ?? [])
    .filter((c) => !activeCat || c.category === activeCat)
    .map((c) => ({ ...c, reports: c.reports.filter(matches) }))
    .filter((c) => c.reports.length > 0);

  const reportCard = (r: CatalogueReport) => (
    <div key={r.id} className="flex flex-col gap-1 rounded-[var(--radius-app)] border border-border p-3">
      <div className="flex items-start gap-2">
        <button type="button" onClick={() => toggleFav(r.id)} aria-label="Favourite"
          className={favs.includes(r.id) ? "text-brand" : "text-muted-foreground"}>
          <Star className="h-4 w-4" fill={favs.includes(r.id) ? "currentColor" : "none"} aria-hidden />
        </button>
        <div className="flex-1">
          <div className="text-sm font-medium">{r.name}</div>
          <div className="text-xs text-muted-foreground">{r.description}</div>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-1">
        {r.filters.slice(0, 6).map((fl) => <Badge key={fl} variant="muted">{fl.replace(/_/g, " ")}</Badge>)}
        {r.qualification && <Badge variant="warning">qualified</Badge>}
      </div>
      <div className="mt-1 flex gap-2">
        <Button size="sm" onClick={() => openReport(r)}>View report</Button>
      </div>
    </div>
  );

  return (
    <AppShell title="Report Catalogue" subtitle={`${cat?.count ?? ""} reports · ${current.name}`}>
      <div className="flex flex-col gap-4">
        {error && <p className="rounded-[var(--radius-app)] border border-danger/40 bg-danger/5 px-3 py-2 text-sm text-danger">{error}</p>}

        {!open && (<>
        <Card><CardContent className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative flex-1 min-w-[12rem]">
              <Search className="pointer-events-none absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
              <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search reports…" className="pl-8" />
            </div>
            <Button size="sm" variant="outline" onClick={() => void printIndex()}>
              <FileText className="h-4 w-4" aria-hidden /> Printable index
            </Button>
          </div>
          <div className="flex flex-wrap gap-1">
            <button type="button" onClick={() => setActiveCat(null)}
              className={`rounded-[var(--radius-app)] border px-2 py-1 text-xs ${!activeCat ? "border-brand bg-brand/10 text-brand" : "border-border text-muted-foreground"}`}>All</button>
            {(cat?.categories ?? []).map((c) => (
              <button key={c.category} type="button" onClick={() => setActiveCat(c.category)}
                className={`rounded-[var(--radius-app)] border px-2 py-1 text-xs ${activeCat === c.category ? "border-brand bg-brand/10 text-brand" : "border-border text-muted-foreground"}`}>
                {c.category} ({c.reports.length})
              </button>
            ))}
          </div>
        </CardContent></Card>

        {(favs.length > 0 || recent.length > 0) && !q && !activeCat && (
          <div className="grid gap-4 sm:grid-cols-2">
            {favs.length > 0 && (
              <Card><CardContent className="flex flex-col gap-2">
                <h3 className="text-sm font-semibold">★ Favourites</h3>
                {favs.map((id) => byId.get(id)).filter(Boolean).slice(0, 8).map((r) => (
                  <button key={r!.id} type="button" onClick={() => openReport(r!)}
                    className="text-left text-sm text-brand hover:underline">{r!.name}</button>
                ))}
              </CardContent></Card>
            )}
            {recent.length > 0 && (
              <Card><CardContent className="flex flex-col gap-2">
                <h3 className="text-sm font-semibold">Recently used</h3>
                {recent.map((id) => byId.get(id)).filter(Boolean).slice(0, 8).map((r) => (
                  <button key={r!.id} type="button" onClick={() => openReport(r!)}
                    className="text-left text-sm text-brand hover:underline">{r!.name}</button>
                ))}
              </CardContent></Card>
            )}
          </div>
        )}

        {visibleCategories.map((c) => (
          <Card key={c.category}><CardContent className="flex flex-col gap-2">
            <h3 className="text-sm font-semibold">{c.category}</h3>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">{c.reports.map(reportCard)}</div>
          </CardContent></Card>
        ))}
        {visibleCategories.length === 0 && cat && <p className="text-sm text-muted-foreground">No reports match “{query}”.</p>}
        </>)}

        {open && (
          <div ref={reportRef}><Card><CardContent className="flex flex-col gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <Button size="sm" variant="outline" onClick={closeReport}>← All reports</Button>
              <h3 className="text-sm font-semibold">{open.name}</h3>
              <Badge variant="muted">{open.category}</Badge>
              <div className="ml-auto flex items-center gap-2">
                {open.pdf && <Button size="sm" variant="outline" onClick={() => void exportUrl("pdf")}><Download className="h-4 w-4" aria-hidden /> PDF</Button>}
                {open.csv && <Button size="sm" variant="outline" onClick={() => void exportUrl("csv")}><Download className="h-4 w-4" aria-hidden /> CSV</Button>}
                <Button size="sm" variant="ghost" onClick={closeReport} aria-label="Close"><X className="h-4 w-4" aria-hidden /></Button>
              </div>
            </div>

            {/* Scope filters this report supports — the engine applies them to the figures and the PDF/CSV. */}
            <div className="flex flex-wrap items-end gap-2 text-xs">
              {open.filters.includes("organisation") && organisations.length > 0 && (
                <label className="flex flex-col gap-1">
                  <span className="text-muted-foreground">Club</span>
                  <Select value={organisationId} onChange={(e) => setOrganisationId(e.target.value)} className="w-44">
                    <option value="">All clubs</option>
                    {organisations.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
                  </Select>
                </label>
              )}
              {open.filters.includes("team") && teams.length > 0 && (
                <label className="flex flex-col gap-1">
                  <span className="text-muted-foreground">Team</span>
                  <Select value={teamId} onChange={(e) => setTeamId(e.target.value)} className="w-44">
                    <option value="">All teams</option>
                    {teams.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                  </Select>
                </label>
              )}
              {open.filters.includes("competition") && competitions.length > 0 && (
                <label className="flex flex-col gap-1">
                  <span className="text-muted-foreground">Competition</span>
                  <Select value={competitionId} onChange={(e) => setCompetitionId(e.target.value)} className="w-44">
                    <option value="">All competitions</option>
                    {competitions.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                  </Select>
                </label>
              )}
              {open.filters.includes("grade") && grades.length > 0 && (
                <label className="flex flex-col gap-1">
                  <span className="text-muted-foreground">Grade</span>
                  <Select value={gradeId} onChange={(e) => setGradeId(e.target.value)} className="w-36">
                    <option value="">All grades</option>
                    {grades.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
                  </Select>
                </label>
              )}
              {open.filters.includes("season") && seasonLabels.length > 0 && (
                <label className="flex flex-col gap-1">
                  <span className="text-muted-foreground">Season (year)</span>
                  <Select value={seasonLabel} onChange={(e) => setSeasonLabel(e.target.value)} className="w-32">
                    <option value="">All years</option>
                    {seasonLabels.map((s) => <option key={s} value={s}>{s}</option>)}
                  </Select>
                </label>
              )}
              {open.filters.includes("venue") && venues.length > 0 && (
                <label className="flex flex-col gap-1">
                  <span className="text-muted-foreground">Ground</span>
                  <Select value={venueId} onChange={(e) => setVenueId(e.target.value)} className="w-44">
                    <option value="">All grounds</option>
                    {venues.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
                  </Select>
                </label>
              )}
              {open.filters.includes("split") && (
                <label className="flex flex-col gap-1">
                  <span className="text-muted-foreground">Matches</span>
                  <Select value={split} onChange={(e) => setSplit(e.target.value)} className="w-40">
                    {SPLITS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
                  </Select>
                </label>
              )}
              {open.filters.includes("format") && formats.length > 0 && (
                <label className="flex flex-col gap-1">
                  <span className="text-muted-foreground">Format</span>
                  <Select value={format} onChange={(e) => setFormat(e.target.value)} className="w-40">
                    <option value="">All formats</option>
                    {formats.map((fmt) => <option key={fmt} value={fmt}>{fmt}</option>)}
                  </Select>
                </label>
              )}
            </div>
            {(() => {
              const chips = [
                organisationId && open.filters.includes("organisation") && { label: `Club: ${organisations.find((o) => o.id === organisationId)?.name ?? "—"}`, clear: () => setOrganisationId("") },
                teamId && open.filters.includes("team") && { label: `Team: ${teams.find((t) => t.id === teamId)?.name ?? "—"}`, clear: () => setTeamId("") },
                competitionId && open.filters.includes("competition") && { label: `Comp: ${competitions.find((c) => c.id === competitionId)?.name ?? "—"}`, clear: () => setCompetitionId("") },
                gradeId && open.filters.includes("grade") && { label: `Grade: ${grades.find((g) => g.id === gradeId)?.name ?? "—"}`, clear: () => setGradeId("") },
                seasonLabel && open.filters.includes("season") && { label: `Season: ${seasonLabel}`, clear: () => setSeasonLabel("") },
                venueId && open.filters.includes("venue") && { label: `Ground: ${venues.find((v) => v.id === venueId)?.name ?? "—"}`, clear: () => setVenueId("") },
                split && open.filters.includes("split") && { label: SPLITS.find((s) => s.value === split)?.label ?? split, clear: () => setSplit("") },
                format && open.filters.includes("format") && { label: `Format: ${format}`, clear: () => setFormat("") },
              ].filter(Boolean) as { label: string; clear: () => void }[];
              return chips.length > 0 ? (
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-xs text-muted-foreground">Scope:</span>
                  {chips.map((c, i) => (
                    <span key={i} className="inline-flex items-center gap-1 rounded-full border border-brand bg-brand/10 px-2 py-0.5 text-xs text-brand">
                      {c.label}
                      <button type="button" aria-label={`Clear ${c.label}`} className="hover:text-danger" onClick={c.clear}>×</button>
                    </span>
                  ))}
                </div>
              ) : <p className="text-xs text-muted-foreground">Showing all matches. Use the filters above to scope this report to a club, team or season.</p>;
            })()}
            <p className="text-xs text-muted-foreground">{open.description}</p>
            {(open.qualification || open.limitations) && (
              <p className="text-xs text-muted-foreground">
                {open.qualification && <span className="block">Qualification: {open.qualification}</span>}
                {open.limitations && <span className="block">Note: {open.limitations}</span>}
              </p>
            )}
            {!data ? <p className="text-xs text-muted-foreground">Loading…</p> :
              data.rows.length === 0 ? <p className="text-xs text-muted-foreground">No data for this report yet.</p> :
              <div className="max-h-[32rem] overflow-auto rounded-[var(--radius-app)] border border-border">
                <table className="w-full border-collapse text-sm">
                  <thead className="sticky top-0 bg-brand text-white">
                    <tr>{data.columns.map((col) => (
                      <th key={col.key} className={`whitespace-nowrap px-2 py-1.5 font-semibold ${col.align === "right" ? "text-right" : "text-left"}`}>{col.label}</th>
                    ))}</tr>
                  </thead>
                  <tbody>
                    {data.rows.map((r, i) => (
                      <tr key={i} className={i % 2 ? "bg-muted/30" : ""}>
                        {data.columns.map((col) => (
                          <td key={col.key} className={`whitespace-nowrap px-2 py-1 tabular-nums ${col.align === "right" ? "text-right" : "text-left"}`}>
                            {fmt(r[col.key], col)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>}
          </CardContent></Card></div>
        )}
      </div>
    </AppShell>
  );
}
