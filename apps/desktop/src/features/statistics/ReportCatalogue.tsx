/**
 * Report Catalogue (Phase 12 expansion) — a professional, searchable, categorised library of every
 * ready-made report. Each entry opens a working report from the one deterministic engine, with split
 * filtering and PDF / CSV export. Favourites and recently-used persist per viewer (localStorage).
 */
import { Download, FileText, Search, Star, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AppShell } from "../../components/layout/AppShell";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import { Input } from "../../components/ui/input";
import { Select } from "../../components/ui/select";
import { api, ApiError, type CatalogueReport, type ReportCatalogue as Catalogue, type StatColumn, type StatReport } from "../../lib/api";
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
  const [data, setData] = useState<StatReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!current) return;
    api.statsCatalogue(current.id).then(setCat).catch((e) =>
      setError(e instanceof ApiError ? e.message : "Could not load the report catalogue."));
  }, [current]);

  const allReports = useMemo(() => (cat?.categories ?? []).flatMap((c) => c.reports), [cat]);
  const byId = useMemo(() => new Map(allReports.map((r) => [r.id, r])), [allReports]);

  const toggleFav = useCallback((id: string) => {
    setFavs((prev) => {
      const next = prev.includes(id) ? prev.filter((x) => x !== id) : [id, ...prev];
      saveIds(FAV_KEY, next);
      return next;
    });
  }, []);

  const loadReport = useCallback(async (r: CatalogueReport, sp: string) => {
    if (!current) return;
    setError(null);
    try {
      const d = await api.statsReport(current.id, r.id, { split: sp || undefined });
      setData(d);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not open the report.");
      setData(null);
    }
  }, [current]);

  const openReport = useCallback((r: CatalogueReport) => {
    if (r.id === "capt_compare") { window.location.hash = "#/statistics/captaincy-compare"; return; }
    setOpen(r);
    setSplit("");
    setData(null);
    void loadReport(r, "");
    setRecent((prev) => {
      const next = [r.id, ...prev.filter((x) => x !== r.id)];
      saveIds(RECENT_KEY, next);
      return next;
    });
  }, [loadReport]);

  const exportUrl = useCallback(async (kind: "pdf" | "csv") => {
    if (!current || !open) return;
    try {
      const q = { split: split || undefined };
      const url = kind === "pdf"
        ? await api.statsReportPdfUrl(current.id, open.id, q)
        : await api.statsReportCsvUrl(current.id, open.id, q);
      window.open(url, "_blank");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Export failed.");
    }
  }, [current, open, split]);

  const printIndex = useCallback(async () => {
    if (!current) return;
    try {
      window.open(await api.statsCatalogueIndexUrl(current.id), "_blank");
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

        {open && (
          <Card><CardContent className="flex flex-col gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-sm font-semibold">{open.name}</h3>
              <Badge variant="muted">{open.category}</Badge>
              <div className="ml-auto flex items-center gap-2">
                <Select value={split} onChange={(e) => { setSplit(e.target.value); void loadReport(open, e.target.value); }}>
                  {SPLITS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
                </Select>
                {open.pdf && <Button size="sm" variant="outline" onClick={() => void exportUrl("pdf")}><Download className="h-4 w-4" aria-hidden /> PDF</Button>}
                {open.csv && <Button size="sm" variant="outline" onClick={() => void exportUrl("csv")}><Download className="h-4 w-4" aria-hidden /> CSV</Button>}
                <Button size="sm" variant="ghost" onClick={() => { setOpen(null); setData(null); }} aria-label="Close"><X className="h-4 w-4" aria-hidden /></Button>
              </div>
            </div>
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
          </CardContent></Card>
        )}
      </div>
    </AppShell>
  );
}
