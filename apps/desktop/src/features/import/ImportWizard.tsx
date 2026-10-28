/**
 * CricketStatz Import Wizard (Phase 6, Stage 8). A professional, step-by-step interface over the
 * existing import engine — it does NOT reimplement any import logic. Steps: choose source & file →
 * analyse (counts + selectable matches) → preview (nothing persists) → import selected → results.
 *
 * The genuine export file is parsed locally (read-only, never modified); only the selected slice is
 * sent to the backend. Preview and import both go through POST /imports/cricketstatz, which runs the
 * proven people + structural + scorecard pipeline server-side under workspace isolation and the
 * import.manage permission. Imports are idempotent (re-import creates no duplicates), unresolved
 * dismissal codes and source provenance are preserved, and imported matches open in the Scorecard.
 */

import { AlertTriangle, CheckCircle2, DatabaseBackup, FileJson, Loader2, Upload } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AppShell } from "../../components/layout/AppShell";
import { ErrorState } from "../../components/states/States";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import { Input } from "../../components/ui/input";
import { Select } from "../../components/ui/select";
import { api, ApiError, type Competition, type CricketStatzImportResult, type ImportBatch } from "../../lib/api";
import { NoWorkspace, useManage } from "../manage/_shared";
import { UniversalImport } from "./UniversalImport";

// loose shapes — the CricketStatz export is parsed as-is (the backend owns validation)
interface CsFile { [k: string]: unknown[] | null | undefined }
type Row = Record<string, number | string | null | undefined>;
type Wrap = { MatchID: number; cricket_Innings?: Array<Record<string, unknown>> };

function count(file: CsFile, key: string): number {
  const v = file[key];
  return Array.isArray(v) ? v.length : 0;
}

function nestedCount(file: CsFile, key: string, inner: string): number {
  const v = file[key];
  if (!Array.isArray(v)) return 0;
  let n = 0;
  for (const w of v as Wrap[]) for (const i of w.cricket_Innings ?? []) n += ((i[inner] as unknown[]) ?? []).length;
  return n;
}

/** Build the sliced payload (structural + scorecards + referenced people) for the selected matches —
 *  only the records those matches need, mirroring the controlled-import scoping. Exported for tests. */
export function buildSlice(file: CsFile, ids: Set<number>) {
  const matches = ((file.matches as Row[]) ?? []).filter((m) => ids.has(m.MatchID as number));
  const keep = new Set(matches.map((m) => m.MatchID as number));
  const pick = (k: string) => ((file[k] as Wrap[]) ?? []).filter((w) => keep.has(w.MatchID));
  const innings = pick("innings"), batting = pick("batting"), bowling = pick("bowling");

  const teamIds = new Set<number>();
  for (const m of matches) { for (const k of ["HomeTeam", "AwayTeam"]) { const v = m[k] as number; if (v) teamIds.add(v); } }
  for (const w of innings) for (const i of w.cricket_Innings ?? []) for (const k of ["battingteam", "bowlingteam"]) { const v = i[k] as number; if (v) teamIds.add(v); }
  const gradeIds = new Set(matches.map((m) => m.Grade as number).filter(Boolean));
  const groundIds = new Set(matches.map((m) => m.Ground as number).filter(Boolean));
  const teams = ((file.teams as Row[]) ?? []).filter((t) => teamIds.has(t.TeamID as number));
  const clubIds = new Set(teams.map((t) => t.ClubID as number).filter(Boolean));

  const pids = new Set<number>();
  const addP = (v: unknown) => { if (typeof v === "number" && v) pids.add(v); };
  for (const m of matches) for (const k of ["homecaptain1", "homekeeper1", "homekeeper2", "awaycaptain1",
    "awaykeeper1", "awaykeeper2", "tosswonby", "official1", "official2", "official3", "scorer1", "scorer2", "scorer3"]) addP(m[k]);
  for (const w of batting) for (const i of w.cricket_Innings ?? []) for (const b of (i.cricket_batting as Row[]) ?? [])
    if (b) for (const k of ["BatsmanID", "Bowler", "Fielder", "FOWBatID"]) addP(b[k]);
  for (const w of bowling) for (const i of w.cricket_Innings ?? []) for (const bw of (i.cricket_bowling as Row[]) ?? [])
    if (bw) addP(bw.bowlerID);

  return {
    data: {
      clubs: ((file.clubs as Row[]) ?? []).filter((c) => clubIds.has(c.ClubID as number)),
      teams,
      venues: ((file.venues as Row[]) ?? []).filter((v) => groundIds.has(v.GroundID as number)),
      divisions: ((file.divisions as Row[]) ?? []).filter((d) => gradeIds.has(d.GradeID as number)),
      matches, innings, batting, bowling,
    },
    people: {
      players: ((file.players as Row[]) ?? []).filter((p) => pids.has(p.PlayerID as number)),
      officials: ((file.officials as Row[]) ?? []).filter((o) => pids.has(o.PlayerID as number)),
    },
  };
}

type Step = "select" | "analyse" | "preview" | "importing" | "results";

export function ImportWizard() {
  const { workspaceId } = useManage();
  const navigate = useNavigate();
  const [mode, setMode] = useState<"cricketstatz" | "universal">("cricketstatz");
  const [step, setStep] = useState<Step>("select");
  const [file, setFile] = useState<CsFile | null>(null);
  const [fileName, setFileName] = useState("");
  const [fileSize, setFileSize] = useState(0);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [preview, setPreview] = useState<CricketStatzImportResult | null>(null);
  const [result, setResult] = useState<CricketStatzImportResult | null>(null);
  const [history, setHistory] = useState<ImportBatch[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Competition to import into. CricketStatz exports carry no competition, so the user chooses:
  // "" = default import container, a competition id = import into it, "__new__" = create by name.
  const [comps, setComps] = useState<Competition[]>([]);
  const [compChoice, setCompChoice] = useState<string>("");
  const [newCompName, setNewCompName] = useState("");
  const [assignBySeason, setAssignBySeason] = useState(false);
  const [suggestClass, setSuggestClass] = useState(false);

  const loadHistory = useCallback(async () => {
    if (!workspaceId) return;
    try { setHistory(await api.listImports(workspaceId)); } catch { /* history is best-effort */ }
    try { setComps(await api.listCompetitions(workspaceId)); } catch { /* best-effort */ }
  }, [workspaceId]);
  useEffect(() => { void loadHistory(); }, [loadHistory]);

  // name maps for the match table (resolved from the file's own lists)
  const names = useMemo(() => {
    const team = new Map<number, string>(), venue = new Map<number, string>(), grade = new Map<number, string>();
    for (const t of (file?.teams as Row[]) ?? []) team.set(t.TeamID as number, String(t.Name ?? t.TeamID));
    for (const v of (file?.venues as Row[]) ?? []) venue.set(v.GroundID as number, String(v.Name ?? ""));
    for (const g of (file?.divisions as Row[]) ?? []) grade.set(g.GradeID as number, String(g.Name ?? ""));
    return { team, venue, grade };
  }, [file]);

  const matches = (file?.matches as Row[]) ?? [];

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    setError(null); setBusy(true);
    try {
      const text = await f.text();
      const parsed = JSON.parse(text) as CsFile;
      if (!Array.isArray(parsed.matches)) throw new Error("This file has no 'matches' — is it a CricketStatz JSON export?");
      setFile(parsed); setFileName(f.name); setFileSize(f.size);
      setSelected(new Set()); setPreview(null); setResult(null);
      setStep("analyse");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not read the file as JSON.");
    } finally { setBusy(false); }
  }

  const toggle = (id: number) => setSelected((s) => {
    const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n;
  });
  const selectFirst = (k: number) => setSelected(new Set(matches.slice(0, k).map((m) => m.MatchID as number)));
  const selectAll = () => setSelected(new Set(matches.map((m) => m.MatchID as number)));

  async function runPreview() {
    if (!workspaceId || !file) return;
    setBusy(true); setError(null);
    try {
      const { data, people } = buildSlice(file, selected);
      setPreview(await api.cricketStatzImport(workspaceId, { data, people, commit: false, filename: fileName }));
      setStep("preview");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Preview failed.");
    } finally { setBusy(false); }
  }

  async function runImport() {
    if (!workspaceId || !file) return;
    setStep("importing"); setBusy(true); setError(null);
    try {
      const { data, people } = buildSlice(file, selected);
      const competition_id = compChoice && compChoice !== "__new__" ? compChoice : null;
      const competition_name = compChoice === "__new__" ? newCompName.trim() || null : null;
      setResult(await api.cricketStatzImport(workspaceId, { data, people, commit: true, filename: fileName, competition_id, competition_name, assign_by_season_date: assignBySeason, suggest_classifications: suggestClass }));
      await loadHistory();
      setStep("results");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Import failed.");
      setStep("preview");
    } finally { setBusy(false); }
  }

  function reset() {
    setStep("select"); setFile(null); setFileName(""); setSelected(new Set());
    setPreview(null); setResult(null); setError(null);
  }

  if (!workspaceId) return <AppShell title="Import Data"><NoWorkspace /></AppShell>;

  return (
    <AppShell title="Import Data" subtitle="Bring matches and scorecards in from CricketStatz and other formats">
      <div className="mx-auto flex max-w-4xl flex-col gap-4">
        <div className="flex gap-1 rounded-[var(--radius-app)] border border-border p-1 text-sm w-fit">
          {([["cricketstatz", "CricketStatz"], ["universal", "Other formats (CSV, Excel, JSON, XML)"]] as const).map(([m, label]) => (
            <button key={m} onClick={() => setMode(m)}
              className={`rounded-[var(--radius-app)] px-3 py-1 ${mode === m ? "bg-brand text-brand-foreground" : "hover:bg-muted"}`}>
              {label}
            </button>
          ))}
        </div>

        {mode === "universal" && <UniversalImport />}

        {mode === "cricketstatz" && <Stepper step={step} />}
        {error && <ErrorState message={error} />}

        {mode === "cricketstatz" && step === "select" && (
          <SelectStep busy={busy} onFile={onFile} history={history} />
        )}

        {step === "analyse" && file && (
          <Card><CardContent className="flex flex-col gap-4">
            <div className="flex items-center gap-2 text-sm">
              <FileJson className="h-4 w-4 text-brand" aria-hidden />
              <span className="font-medium">{fileName}</span>
              <span className="text-muted-foreground">({(fileSize / 1_048_576).toFixed(1)} MB)</span>
            </div>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
              <Stat label="Matches" n={count(file, "matches")} />
              <Stat label="Innings" n={nestedCountInnings(file)} />
              <Stat label="Batting" n={nestedCount(file, "batting", "cricket_batting")} />
              <Stat label="Bowling" n={nestedCount(file, "bowling", "cricket_bowling")} />
              <Stat label="Players" n={count(file, "players")} />
              <Stat label="Teams" n={count(file, "teams")} />
              <Stat label="Clubs" n={count(file, "clubs")} />
              <Stat label="Venues" n={count(file, "venues")} />
              <Stat label="Grades" n={count(file, "divisions")} />
              <Stat label="Officials" n={count(file, "officials")} />
            </div>

            <div className="flex flex-wrap items-center gap-2 border-t border-border pt-3 text-sm">
              <span className="text-muted-foreground">Select matches to import:</span>
              <Button variant="outline" size="sm" onClick={() => selectFirst(2)}>First 2</Button>
              <Button variant="outline" size="sm" onClick={() => selectFirst(10)}>First 10</Button>
              <Button variant="outline" size="sm" onClick={selectAll}>Select all ({matches.length})</Button>
              <Button variant="outline" size="sm" onClick={() => setSelected(new Set())}>Clear</Button>
              <span className="ml-auto font-medium">{selected.size} selected</span>
            </div>

            <div className="max-h-96 overflow-auto rounded-[var(--radius-app)] border border-border">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-muted text-left text-xs text-muted-foreground">
                  <tr><th className="w-8 px-2 py-1.5" /><th className="px-2 py-1.5">Date</th>
                    <th className="px-2 py-1.5">Home</th><th className="px-2 py-1.5">Away</th>
                    <th className="px-2 py-1.5">Grade</th><th className="px-2 py-1.5">Venue</th></tr>
                </thead>
                <tbody>
                  {matches.slice(0, 500).map((m) => {
                    const id = m.MatchID as number;
                    return (
                      <tr key={id} className="border-t border-border hover:bg-muted/40">
                        <td className="px-2 py-1"><input type="checkbox" checked={selected.has(id)} onChange={() => toggle(id)} aria-label={`Select match ${id}`} /></td>
                        <td className="px-2 py-1 tabular-nums">{String(m.DatePlayed ?? "").slice(0, 10) || "—"}</td>
                        <td className="px-2 py-1">{names.team.get(m.HomeTeam as number) ?? "—"}</td>
                        <td className="px-2 py-1">{names.team.get(m.AwayTeam as number) ?? "—"}</td>
                        <td className="px-2 py-1">{names.grade.get(m.Grade as number) ?? "—"}</td>
                        <td className="px-2 py-1">{names.venue.get(m.Ground as number) ?? "—"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {matches.length > 500 && <p className="p-2 text-xs text-muted-foreground">Showing the first 500 of {matches.length}. Use the quick-select buttons for larger slices.</p>}
            </div>

            <div className="flex justify-between">
              <Button variant="ghost" size="sm" onClick={reset}>Back</Button>
              <Button size="sm" disabled={selected.size === 0 || busy} onClick={() => void runPreview()}>
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null} Preview {selected.size} match{selected.size === 1 ? "" : "es"}
              </Button>
            </div>
          </CardContent></Card>
        )}

        {step === "preview" && preview && (
          <PreviewStep preview={preview} selected={selected.size} busy={busy}
            onBack={() => setStep("analyse")} onImport={() => void runImport()}
            comps={comps} compChoice={compChoice} setCompChoice={setCompChoice}
            newCompName={newCompName} setNewCompName={setNewCompName}
            assignBySeason={assignBySeason} setAssignBySeason={setAssignBySeason}
            suggestClass={suggestClass} setSuggestClass={setSuggestClass} />
        )}

        {step === "importing" && (
          <Card><CardContent className="flex flex-col items-center gap-3 py-10">
            <Loader2 className="h-8 w-8 animate-spin text-brand" aria-hidden />
            <p className="text-sm text-muted-foreground">Importing {selected.size} match(es) and their scorecards…</p>
          </CardContent></Card>
        )}

        {step === "results" && result && (
          <ResultsStep result={result} onDone={reset} onOpenMatches={() => navigate("/matches")} />
        )}

        {step === "select" && history.length > 0 && <HistoryPanel history={history} />}
      </div>
    </AppShell>
  );
}

function nestedCountInnings(file: CsFile): number {
  const v = file.innings;
  if (!Array.isArray(v)) return 0;
  let n = 0;
  for (const w of v as Wrap[]) n += (w.cricket_Innings ?? []).length;
  return n;
}

const STEPS: { key: Step; label: string }[] = [
  { key: "select", label: "Source" }, { key: "analyse", label: "Analyse" },
  { key: "preview", label: "Preview" }, { key: "results", label: "Results" },
];
function Stepper({ step }: { step: Step }) {
  const order = ["select", "analyse", "preview", "importing", "results"];
  const cur = order.indexOf(step);
  return (
    <div className="flex items-center gap-2 text-xs">
      {STEPS.map((s, i) => {
        const idx = order.indexOf(s.key);
        const active = idx === cur || (s.key === "preview" && step === "importing");
        const done = idx < cur && !(s.key === "preview" && step === "importing");
        return (
          <div key={s.key} className="flex items-center gap-2">
            <span className={`flex h-6 min-w-6 items-center justify-center rounded-full px-2 font-medium ${active ? "bg-brand text-white" : done ? "bg-brand/15 text-brand" : "bg-muted text-muted-foreground"}`}>{i + 1}</span>
            <span className={active ? "font-medium" : "text-muted-foreground"}>{s.label}</span>
            {i < STEPS.length - 1 && <span className="mx-1 text-muted-foreground">›</span>}
          </div>
        );
      })}
    </div>
  );
}

function SelectStep({ busy, onFile, history }: { busy: boolean; onFile: (e: React.ChangeEvent<HTMLInputElement>) => void; history: ImportBatch[] }) {
  return (
    <Card><CardContent className="flex flex-col gap-4">
      <div className="flex items-start gap-3 rounded-[var(--radius-app)] border border-brand/30 bg-brand/5 p-3">
        <DatabaseBackup className="mt-0.5 h-5 w-5 shrink-0 text-brand" aria-hidden />
        <div className="text-sm">
          <p className="font-medium">CricketStatz (JSON export)</p>
          <p className="text-muted-foreground">Select a CricketStatz <code>.json</code> export. It is read locally and never modified; you choose which matches to import, and nothing is written until you approve the preview.</p>
        </div>
      </div>
      <label className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-[var(--radius-app)] border-2 border-dashed border-border py-10 text-sm hover:bg-muted/40">
        {busy ? <Loader2 className="h-6 w-6 animate-spin text-brand" /> : <Upload className="h-6 w-6 text-muted-foreground" aria-hidden />}
        <span className="font-medium">{busy ? "Reading file…" : "Choose a CricketStatz JSON file"}</span>
        <input type="file" accept=".json,application/json" className="hidden" onChange={onFile} disabled={busy} />
      </label>
      {history.length === 0 && <p className="text-xs text-muted-foreground">No previous imports in this workspace yet.</p>}
    </CardContent></Card>
  );
}

function PreviewStep({ preview, selected, busy, onBack, onImport, comps, compChoice, setCompChoice, newCompName, setNewCompName, assignBySeason, setAssignBySeason, suggestClass, setSuggestClass }: {
  preview: CricketStatzImportResult; selected: number; busy: boolean; onBack: () => void; onImport: () => void;
  comps: Competition[]; compChoice: string; setCompChoice: (v: string) => void;
  newCompName: string; setNewCompName: (v: string) => void;
  assignBySeason: boolean; setAssignBySeason: (v: boolean) => void;
  suggestClass: boolean; setSuggestClass: (v: boolean) => void;
}) {
  const p = preview.preview;
  const ppl = preview.people.detected;
  const unresolved = preview.howout_unresolved ?? [];
  const needsName = compChoice === "__new__" && !newCompName.trim();
  return (
    <Card><CardContent className="flex flex-col gap-4">
      <p className="text-sm">Preview of <strong>{selected}</strong> selected match(es). <span className="text-muted-foreground">Nothing has been written yet.</span></p>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {Object.entries(preview.staged).filter(([, n]) => n > 0).map(([k, n]) => <Stat key={k} label={k.replace(/_/g, " ")} n={n} />)}
      </div>
      <div className="grid gap-2 sm:grid-cols-3">
        <InfoRow label="Promotable now" value={p.promotable_now} />
        <InfoRow label="Matches" value={p.matches_promotable} />
        <InfoRow label="Ambiguous grades (flagged)" value={p.unresolved} warn={p.unresolved > 0} />
      </div>
      {ppl && (
        <div className="rounded-[var(--radius-app)] border border-border p-3 text-sm">
          <p className="mb-1 font-medium">People matching</p>
          <div className="flex flex-wrap gap-3 text-xs">
            <span>Matched existing: <strong>{ppl.matched}</strong></span>
            <span>New: <strong>{ppl.new}</strong></span>
            <span className={ppl.possible_existing > 0 ? "text-warning" : ""}>Needs review: <strong>{ppl.possible_existing}</strong></span>
          </div>
          {ppl.possible_existing > 0 && <p className="mt-1 text-xs text-muted-foreground">Possible duplicate identities are never auto-merged — review them in People after import.</p>}
        </div>
      )}
      {unresolved.length > 0 && (
        <div className="rounded-[var(--radius-app)] border border-warning/40 bg-warning/5 p-3 text-sm">
          <p className="mb-1 flex items-center gap-1 font-medium text-warning"><AlertTriangle className="h-4 w-4" aria-hidden /> Unresolved dismissal codes (preserved for review)</p>
          <div className="flex flex-wrap gap-2 text-xs">
            {unresolved.map((u) => <Badge key={u.code} variant="warning">code {u.code}: {u.count}</Badge>)}
          </div>
        </div>
      )}
      <div className="rounded-[var(--radius-app)] border border-border p-3 text-sm">
        <p className="mb-1 font-medium">Competition</p>
        <p className="mb-2 text-xs text-muted-foreground">CricketStatz files don&apos;t record the competition, so choose where these grades and matches go.</p>
        <label className="mb-2 flex items-start gap-2">
          <input type="checkbox" checked={assignBySeason} onChange={(e) => setAssignBySeason(e.target.checked)} className="mt-0.5 h-4 w-4" />
          <span>
            <span className="font-medium">Assign competition &amp; season by match date</span>
            <span className="block text-xs text-muted-foreground">Files each match under the competition whose season date range covers its date. Set the seasons&apos; start/finish dates on your competitions first; matches with no covering season fall to the choice below.</span>
          </span>
        </label>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-muted-foreground">{assignBySeason ? "Fallback:" : ""}</span>
          <Select value={compChoice} onChange={(e) => setCompChoice(e.target.value)} className="max-w-xs">
            <option value="">Default — Cricket Statz Import container</option>
            {comps.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            <option value="__new__">➕ New competition…</option>
          </Select>
          {compChoice === "__new__" && (
            <Input value={newCompName} onChange={(e) => setNewCompName(e.target.value)}
              placeholder="e.g. Grampians Cricket Association" className="max-w-xs" />
          )}
        </div>
      </div>
      <div className="rounded-[var(--radius-app)] border border-border p-3 text-sm">
        <label className="flex items-start gap-2">
          <input type="checkbox" checked={suggestClass} onChange={(e) => setSuggestClass(e.target.checked)} className="mt-0.5 h-4 w-4" />
          <span>
            <span className="font-medium">Suggest match types from the round</span>
            <span className="block text-xs text-muted-foreground">Proposes Home &amp; Away, Final or Grand Final from each match&apos;s round label (GF, SF, round number…). Written as unverified suggestions — confirm them in bulk on the Matches list; nothing is trusted on a guess.</span>
          </span>
        </label>
      </div>
      <div className="flex justify-between border-t border-border pt-3">
        <Button variant="ghost" size="sm" onClick={onBack}>Back</Button>
        <Button size="sm" disabled={busy || needsName} onClick={onImport}>Import {selected} match(es)</Button>
      </div>
    </CardContent></Card>
  );
}

function ResultsStep({ result, onDone, onOpenMatches }: { result: CricketStatzImportResult; onDone: () => void; onOpenMatches: () => void }) {
  const created = result.promoted?.created ?? {};
  const matched = result.promoted?.matched ?? {};
  const ppl = result.people.promoted;
  const createdEntries = Object.entries(created).filter(([, n]) => n > 0);
  const matchedEntries = Object.entries(matched).filter(([, n]) => n > 0);
  return (
    <Card><CardContent className="flex flex-col gap-4">
      <div className="flex items-center gap-2 text-sm font-medium text-success"><CheckCircle2 className="h-5 w-5" aria-hidden /> Import complete</div>
      <div>
        <p className="mb-1 text-xs font-medium text-muted-foreground">Created</p>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {createdEntries.length ? createdEntries.map(([k, n]) => <Stat key={k} label={k.replace(/_/g, " ")} n={n} />) : <span className="text-sm text-muted-foreground">Nothing new.</span>}
          {ppl && (ppl.created.player ?? 0) > 0 && <Stat label="people" n={ppl.created.player ?? 0} />}
        </div>
      </div>
      {matchedEntries.length > 0 && (
        <div>
          <p className="mb-1 text-xs font-medium text-muted-foreground">Matched existing (no duplicates)</p>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {matchedEntries.map(([k, n]) => <Stat key={k} label={k.replace(/_/g, " ")} n={n} />)}
          </div>
        </div>
      )}
      {(result.howout_unresolved?.length ?? 0) > 0 && (
        <p className="text-xs text-muted-foreground">Unresolved dismissal codes were preserved on each record for later mapping.</p>
      )}
      <div className="flex justify-between border-t border-border pt-3">
        <Button variant="ghost" size="sm" onClick={onDone}>Import another</Button>
        <Button size="sm" onClick={onOpenMatches}>Open in Matches</Button>
      </div>
    </CardContent></Card>
  );
}

function HistoryPanel({ history }: { history: ImportBatch[] }) {
  return (
    <Card><CardContent className="flex flex-col gap-2">
      <p className="text-sm font-medium">Import history</p>
      <div className="overflow-auto rounded-[var(--radius-app)] border border-border">
        <table className="w-full text-sm">
          <thead className="bg-muted text-left text-xs text-muted-foreground">
            <tr><th className="px-2 py-1.5">File</th><th className="px-2 py-1.5">Status</th><th className="px-2 py-1.5">Records</th><th className="px-2 py-1.5">When</th></tr>
          </thead>
          <tbody>
            {history.slice(0, 20).map((b) => (
              <tr key={b.id} className="border-t border-border">
                <td className="px-2 py-1">{b.source_filename ?? b.source_system}</td>
                <td className="px-2 py-1"><Badge variant={b.status === "promoted" ? "success" : "muted"}>{b.status}</Badge></td>
                <td className="px-2 py-1 tabular-nums">{b.counts ? Object.values(b.counts).reduce((a, n) => a + n, 0) : "—"}</td>
                <td className="px-2 py-1 text-muted-foreground">{b.created_at ? new Date(b.created_at).toLocaleString() : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </CardContent></Card>
  );
}

function Stat({ label, n }: { label: string; n: number }) {
  return (
    <div className="rounded-[var(--radius-app)] border border-border bg-card px-3 py-2">
      <div className="text-lg font-semibold tabular-nums">{n.toLocaleString()}</div>
      <div className="text-xs capitalize text-muted-foreground">{label}</div>
    </div>
  );
}
function InfoRow({ label, value, warn }: { label: string; value: number; warn?: boolean }) {
  return (
    <div className={`rounded-[var(--radius-app)] border px-3 py-2 text-sm ${warn ? "border-warning/40 bg-warning/5" : "border-border"}`}>
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="font-semibold tabular-nums">{value}</div>
    </div>
  );
}
