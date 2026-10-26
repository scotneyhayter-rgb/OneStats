/**
 * Statistics (Phase 12) — professional on-screen reports from the one deterministic engine, with
 * consistent filters and one-click PDF export (the PDF carries the same figures). Right-aligned
 * numeric columns, fixed decimals, sticky header, client-side sorting, qualification-aware.
 */
import { Download, RefreshCw, Save, Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AppShell } from "../../components/layout/AppShell";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import { Select } from "../../components/ui/select";
import { api, ApiError, type Competition, type StatColumn, type StatReport } from "../../lib/api";
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
  const [split, setSplit] = useState("");
  const [venue, setVenue] = useState("");
  const [format, setFormat] = useState("");
  const [formats, setFormats] = useState<string[]>([]);
  const [minThreshold, setMinThreshold] = useState("");
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
    loadSaved();
  }, [current, loadSaved]);

  const applySaved = (id: string) => {
    setSelectedSaved(id);
    const s = saved.find((x) => x.id === id);
    if (!s) return;
    const cfg = (s.config ?? {}) as Record<string, string | number>;
    setReport(s.report);
    setCompetitionId(String(cfg.competition_id ?? ""));
    setSplit(String(cfg.split ?? ""));
    setVenue(String(cfg.venue ?? ""));
    setFormat(String(cfg.format ?? ""));
    setMinThreshold(String(cfg.min_runs ?? cfg.min_wickets ?? cfg.min_eligible ?? ""));
  };

  const saveCurrent = async () => {
    if (!current) return;
    const name = window.prompt("Save this report as:");
    if (!name) return;
    const config: Record<string, unknown> = { competition_id: competitionId || undefined,
      split: split || undefined, venue: venue || undefined, format: format || undefined };
    if (minThreshold) {
      if (report === "batting") config.min_runs = Number(minThreshold);
      else if (report === "bowling") config.min_wickets = Number(minThreshold);
      else if (report === "captaincy") config.min_eligible = Number(minThreshold);
    }
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
      competition_id: competitionId || undefined, split: split || undefined, venue: venue || undefined,
      format: format || undefined,
    };
    if (minThreshold) {
      if (report === "batting") q.min_runs = Number(minThreshold);
      else if (report === "bowling") q.min_wickets = Number(minThreshold);
      else if (report === "captaincy") q.min_eligible = Number(minThreshold);
    }
    return q;
  }, [competitionId, split, venue, format, minThreshold, report]);

  const load = useCallback(async () => {
    if (!current) return;
    setBusy(true);
    setError(null);
    try {
      setData(await api.statsReport(current.id, report, query));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load the report.");
    } finally {
      setBusy(false);
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
    if (!sortKey) return data.rows;
    const r = [...data.rows];
    r.sort((a, b) => {
      const av = a[sortKey] as number | string | null;
      const bv = b[sortKey] as number | string | null;
      if (av === null || av === undefined) return 1;
      if (bv === null || bv === undefined) return -1;
      if (typeof av === "number" && typeof bv === "number") return (av - bv) * sortDir;
      return String(av).localeCompare(String(bv)) * sortDir;
    });
    return r;
  }, [data, sortKey, sortDir]);

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

  return (
    <AppShell title="Statistics" subtitle={current.name}>
      <div className="mx-auto flex max-w-5xl flex-col gap-4">
        {error && <p className="rounded-[var(--radius-app)] border border-danger/40 bg-danger/5 px-3 py-2 text-sm text-danger">{error}</p>}

        <div className="flex items-center justify-between gap-2">
          <p className="text-xs text-muted-foreground">Core leaderboards with full filters. For the complete library of reports, open the catalogue.</p>
          <a href="#/statistics/catalogue"
            className="whitespace-nowrap rounded-[var(--radius-app)] border border-brand bg-brand/10 px-3 py-1.5 text-sm font-medium text-brand">
            Report Catalogue →
          </a>
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
          <div className="flex flex-wrap items-end gap-2 text-xs">
            <label className="flex flex-col gap-1">
              <span className="text-muted-foreground">Competition</span>
              <Select value={competitionId} onChange={(e) => setCompetitionId(e.target.value)} className="w-44">
                <option value="">All competitions</option>
                {competitions.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </Select>
            </label>
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
            {formats.length > 0 && (
              <label className="flex flex-col gap-1">
                <span className="text-muted-foreground">Format</span>
                <Select value={format} onChange={(e) => setFormat(e.target.value)} className="w-44">
                  <option value="">All formats</option>
                  {formats.map((fmt) => <option key={fmt} value={fmt}>{fmt}</option>)}
                </Select>
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
