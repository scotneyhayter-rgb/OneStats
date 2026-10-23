/**
 * Integrated scorecard editor (Stage 7, §3): one screen with clearly-organised sections for match
 * details, innings, batting, bowling, extras, fall of wickets, partnerships, and result/notes —
 * moving between them never loses work (each section commits to the Phase 6 API). Non-blocking
 * advisory warnings are shown per innings; genuine integrity/permission errors are surfaced from
 * the backend. A visual legend distinguishes recorded / calculated / unknown / conflicting /
 * verified information.
 */

import { ChevronLeft, Info, Save } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import { Input, Textarea } from "../../components/ui/input";
import { Select } from "../../components/ui/select";
import { ErrorState, LoadingState } from "../../components/states/States";
import {
  api, ApiError, type Competition, type InningsTotals, type Innings, type MatchDetail,
  type Person, type Team, type Venue, type Grade, type Season, type CompetitionDetail,
} from "../../lib/api";
import { useWorkspace } from "../../lib/workspace-context";
import { Field } from "../manage/_shared";
import { BattingGrid, BowlingGrid, FowGrid, PartnershipsGrid } from "./grids";
import {
  deserializeDraft, draftKey, inningsAdvisories, INNINGS_STATUSES, serializeDraft, showNum,
} from "./scorecard-logic";

const CLASSIFICATIONS = ["unclassified", "home_away", "final", "grand_final", "other"];
const FINALS_STAGES = ["qualifying_final", "elimination_final", "semi_final", "preliminary_final", "grand_final", "custom"];
const RESULT_TYPES = ["home_win", "away_win", "tie", "draw", "no_result", "abandoned", "washout", "forfeit", "unknown"];
const MATCH_STATUSES = ["draft", "final", "abandoned"];

export function ScorecardEditor({
  workspaceId, matchId, canManage, onBack, onSaved,
}: {
  workspaceId: string;
  matchId: string;
  canManage: boolean;
  onBack: () => void;
  onSaved: () => void;
}) {
  const [match, setMatch] = useState<MatchDetail | null>(null);
  const [innings, setInnings] = useState<Innings[]>([]);
  const [teams, setTeams] = useState<Team[]>([]);
  const [venues, setVenues] = useState<Venue[]>([]);
  const [comps, setComps] = useState<Competition[]>([]);
  const [compDetail, setCompDetail] = useState<CompetitionDetail | null>(null);
  const [names, setNames] = useState<Map<string, string>>(new Map());
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [activeInnings, setActiveInnings] = useState<string | null>(null);

  const nameOf = useCallback((id: string | null) => (id ? names.get(id) ?? null : null), [names]);
  const teamName = useCallback((id: string | null) => (id ? teams.find((t) => t.id === id)?.name ?? null : null), [teams]);
  const addName = useCallback((p: Person) => setNames((m) => new Map(m).set(p.id, p.display_name)), []);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const [m, inn, t, v, c, people] = await Promise.all([
        api.getMatch(workspaceId, matchId),
        api.listInnings(workspaceId, matchId),
        api.listTeams(workspaceId),
        api.listVenues(workspaceId),
        api.listCompetitions(workspaceId),
        api.listPeople(workspaceId),
      ]);
      setMatch(m);
      setInnings(inn);
      setTeams(t);
      setVenues(v);
      setComps(c);
      setNames(new Map(people.map((p) => [p.id, p.display_name])));
      if (!activeInnings && inn.length) setActiveInnings(inn[0].id);
      if (m.competition_id) setCompDetail(await api.getCompetition(workspaceId, m.competition_id));
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Failed to load match");
    } finally {
      setLoading(false);
    }
  }, [workspaceId, matchId, activeInnings]);

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId, matchId]);

  const flash = (m: string) => {
    setMsg(m);
    setTimeout(() => setMsg(null), 2500);
  };

  const patchMatch = async (body: Record<string, unknown>) => {
    try {
      await api.updateMatch(workspaceId, matchId, body);
      await load();
      onSaved();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Save failed");
    }
  };

  if (loading) return <LoadingState label="Loading scorecard…" />;
  if (err && !match) return <ErrorState message={err} onRetry={() => void load()} />;
  if (!match) return null;

  const home = match.teams.find((t) => t.is_home);
  const away = match.teams.find((t) => !t.is_home);
  const title = `${teamName(home?.team_id ?? null) ?? "Home"} v ${teamName(away?.team_id ?? null) ?? "Away"}`;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="ghost" size="sm" onClick={onBack}>
          <ChevronLeft className="h-4 w-4" aria-hidden /> Matches
        </Button>
        <h2 className="text-lg font-semibold">{title}</h2>
        <Badge variant={match.status === "final" ? "success" : match.status === "abandoned" ? "warning" : "muted"}>
          {match.status}
        </Badge>
        {match.classification !== "unclassified" && <Badge variant="brand">{match.classification.replace(/_/g, " ")}</Badge>}
        <div className="flex-1" />
        {msg && <span className="text-sm text-success">{msg}</span>}
        {err && <span className="text-sm text-danger">{err}</span>}
      </div>

      <Legend />

      <MatchDetailsSection
        match={match} teams={teams} venues={venues} comps={comps} compDetail={compDetail}
        canManage={canManage} teamName={teamName}
        onComp={async (cid) => { await patchMatch({ competition_id: cid || null }); }}
        onPatch={patchMatch}
        onSetTeam={async (team_id, is_home) => {
          try { await api.setMatchTeam(workspaceId, matchId, { team_id, is_home }); await load(); }
          catch (e) { setErr(e instanceof ApiError ? e.message : "Could not set team"); }
        }}
      />

      <InningsSection
        workspaceId={workspaceId} matchId={matchId} match={match} innings={innings}
        canManage={canManage} activeInnings={activeInnings} setActiveInnings={setActiveInnings}
        nameOf={nameOf} teamName={teamName} addName={addName}
        reloadInnings={async () => setInnings(await api.listInnings(workspaceId, matchId))}
        onDirty={(m) => m && setErr(m)} flash={flash}
      />

      <ResultNotesSection match={match} teamName={teamName} canManage={canManage} onPatch={patchMatch}
        onResult={async (body) => {
          try { await api.setMatchResult(workspaceId, matchId, body); await load(); flash("Result saved."); }
          catch (e) { setErr(e instanceof ApiError ? e.message : "Could not save result"); }
        }} />
    </div>
  );
}

function Legend() {
  const items: { label: string; cls: string }[] = [
    { label: "Recorded", cls: "text-foreground" },
    { label: "Calculated", cls: "text-brand" },
    { label: "Unknown", cls: "italic text-muted-foreground" },
    { label: "Conflicting", cls: "text-danger" },
    { label: "Verified", cls: "text-success" },
  ];
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-[var(--radius-app)] border border-border bg-muted/40 px-3 py-2 text-xs">
      <span className="flex items-center gap-1 font-medium text-muted-foreground"><Info className="h-3.5 w-3.5" aria-hidden /> Legend</span>
      {items.map((i) => <span key={i.label} className={i.cls}>{i.label === "Unknown" ? "—" : "●"} {i.label}</span>)}
    </div>
  );
}

function MatchDetailsSection({
  match, teams, venues, comps, compDetail, canManage, teamName, onComp, onPatch, onSetTeam,
}: {
  match: MatchDetail; teams: Team[]; venues: Venue[]; comps: Competition[]; compDetail: CompetitionDetail | null;
  canManage: boolean; teamName: (id: string | null) => string | null;
  onComp: (cid: string) => void; onPatch: (b: Record<string, unknown>) => void;
  onSetTeam: (teamId: string, isHome: boolean) => void;
}) {
  const home = match.teams.find((t) => t.is_home)?.team_id ?? "";
  const away = match.teams.find((t) => !t.is_home)?.team_id ?? "";
  const grades: Grade[] = compDetail?.grades ?? [];
  const seasons: Season[] = compDetail?.seasons ?? [];
  return (
    <Section title="Match details">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <Field label="Competition">
          <Select value={match.competition_id ?? ""} disabled={!canManage} onChange={(e) => onComp(e.target.value)}>
            <option value="">— none —</option>
            {comps.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </Select>
        </Field>
        <Field label="Grade">
          <Select value={match.grade_id ?? ""} disabled={!canManage || !grades.length} onChange={(e) => onPatch({ grade_id: e.target.value || null })}>
            <option value="">— none —</option>
            {grades.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
          </Select>
        </Field>
        <Field label="Season">
          <Select value={match.season_id ?? ""} disabled={!canManage || !seasons.length} onChange={(e) => onPatch({ season_id: e.target.value || null })}>
            <option value="">— none —</option>
            {seasons.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
          </Select>
        </Field>
        <Field label="Venue">
          <Select value={match.venue_id ?? ""} disabled={!canManage} onChange={(e) => onPatch({ venue_id: e.target.value || null })}>
            <option value="">— unknown —</option>
            {venues.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
          </Select>
        </Field>
        <Field label="Date" hint="Leave blank if unknown — never guessed.">
          <Input type="date" value={match.match_date ?? ""} disabled={!canManage} onChange={(e) => onPatch({ match_date: e.target.value || null })} />
        </Field>
        <Field label="Format">
          <Input value={match.format ?? ""} placeholder="e.g. two-day, limited overs" disabled={!canManage}
            onBlur={(e) => { if ((e.target.value || null) !== match.format) onPatch({ format: e.target.value || null }); }}
            onChange={() => { /* committed on blur */ }} defaultValue={match.format ?? ""} />
        </Field>
        <Field label="Round" hint="A label only — never used to classify the match.">
          <Input defaultValue={match.round ?? ""} placeholder="e.g. Round 5, GF" disabled={!canManage}
            onBlur={(e) => { if ((e.target.value || null) !== match.round) onPatch({ round: e.target.value || null }); }} />
        </Field>
      </div>

      <ClassificationControl match={match} canManage={canManage} />

      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <Field label="Home team">
          <Select value={home} disabled={!canManage} onChange={(e) => e.target.value && onSetTeam(e.target.value, true)}>
            <option value="">— select —</option>
            {teams.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </Select>
        </Field>
        <Field label="Away team">
          <Select value={away} disabled={!canManage} onChange={(e) => e.target.value && onSetTeam(e.target.value, false)}>
            <option value="">— select —</option>
            {teams.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </Select>
        </Field>
      </div>
      <p className="mt-1 text-xs text-muted-foreground">Home: {teamName(home || null) ?? "—"} · Away: {teamName(away || null) ?? "—"}</p>
    </Section>
  );
}

function ClassificationControl({ match, canManage }: { match: MatchDetail; canManage: boolean }) {
  // Classification is set through its own endpoint (independent of round), so give it a clear control.
  const [cls, setCls] = useState(match.classification);
  const [stage, setStage] = useState(match.finals_stage ?? "");
  const [verified, setVerified] = useState(match.classification_verified);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const w = useWorkspaceId();
  const save = async () => {
    if (!w) return;
    setBusy(true);
    try {
      await api.setMatchClassification(w, match.id, {
        classification: cls, finals_stage: stage || null, verified,
      });
      setDone(true);
      setTimeout(() => setDone(false), 2000);
    } finally {
      setBusy(false);
    }
  };
  const isFinal = cls === "final" || cls === "grand_final" || cls === "other";
  return (
    <div className="mt-3 flex flex-wrap items-end gap-2 rounded-[var(--radius-app)] border border-border bg-background px-3 py-2">
      <Field label="Classification">
        <Select value={cls} disabled={!canManage} onChange={(e) => setCls(e.target.value)} className="w-40">
          {CLASSIFICATIONS.map((c) => <option key={c} value={c}>{c.replace(/_/g, " ")}</option>)}
        </Select>
      </Field>
      {isFinal && (
        <Field label="Finals stage">
          <Select value={stage} disabled={!canManage} onChange={(e) => setStage(e.target.value)} className="w-44">
            <option value="">— unspecified —</option>
            {FINALS_STAGES.map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
          </Select>
        </Field>
      )}
      <label className="flex items-center gap-1 text-sm">
        <input type="checkbox" checked={verified} disabled={!canManage} onChange={(e) => setVerified(e.target.checked)} />
        Verified
      </label>
      {canManage && (
        <Button size="sm" variant="outline" onClick={() => void save()} disabled={busy}>
          {done ? "Saved" : busy ? "Saving…" : "Set classification"}
        </Button>
      )}
    </div>
  );
}

// tiny workspace-id accessor without threading props everywhere (reads the same context the app uses)
function useWorkspaceId(): string | null {
  const { current } = useWorkspace();
  return current?.id ?? null;
}

function InningsSection({
  workspaceId, matchId, match, innings, canManage, activeInnings, setActiveInnings,
  nameOf, teamName, addName, reloadInnings, onDirty, flash,
}: {
  workspaceId: string; matchId: string; match: MatchDetail; innings: Innings[];
  canManage: boolean; activeInnings: string | null; setActiveInnings: (id: string) => void;
  nameOf: (id: string | null) => string | null; teamName: (id: string | null) => string | null;
  addName: (p: Person) => void; reloadInnings: () => Promise<void>; onDirty: (m: string | null) => void; flash: (m: string) => void;
}) {
  const addInnings = async () => {
    const n = innings.length + 1;
    const bat = match.teams.find((t) => t.is_home)?.team_id;
    const bowl = match.teams.find((t) => !t.is_home)?.team_id;
    // alternate batting side by innings number where both sides are known
    const batting = n % 2 === 1 ? bat : bowl;
    const bowling = n % 2 === 1 ? bowl : bat;
    try {
      const created = await api.createInnings(workspaceId, matchId, {
        inns_number: n, batting_team_id: batting ?? null, bowling_team_id: bowling ?? null,
      });
      await reloadInnings();
      setActiveInnings(created.id);
    } catch (e) {
      onDirty(e instanceof ApiError ? e.message : "Could not add innings");
    }
  };

  const active = innings.find((i) => i.id === activeInnings) ?? null;
  return (
    <Section title="Innings">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        {innings.map((i) => (
          <button key={i.id} onClick={() => setActiveInnings(i.id)}
            className={`rounded-[var(--radius-app)] border px-3 py-1 text-sm ${i.id === activeInnings ? "border-brand bg-brand/10 text-brand" : "border-border hover:bg-muted"}`}>
            Innings {i.inns_number}
            <span className="ml-1 text-xs text-muted-foreground">{teamName(i.batting_team_id) ?? "—"}</span>
          </button>
        ))}
        {canManage && (
          <Button size="sm" variant="outline" onClick={() => void addInnings()}>Add innings</Button>
        )}
      </div>
      {!active && <p className="text-sm text-muted-foreground">No innings yet. Add the first innings to begin entry.</p>}
      {active && (
        <InningsEditor key={active.id} workspaceId={workspaceId} matchId={matchId} innings={active}
          canManage={canManage} nameOf={nameOf} teamName={teamName} addName={addName}
          reloadInnings={reloadInnings} onDirty={onDirty} flash={flash} />
      )}
    </Section>
  );
}

function InningsEditor({
  workspaceId, matchId, innings, canManage, nameOf, teamName, addName, reloadInnings, onDirty, flash,
}: {
  workspaceId: string; matchId: string; innings: Innings; canManage: boolean;
  nameOf: (id: string | null) => string | null; teamName: (id: string | null) => string | null;
  addName: (p: Person) => void; reloadInnings: () => Promise<void>; onDirty: (m: string | null) => void; flash: (m: string) => void;
}) {
  const [totals, setTotals] = useState<InningsTotals | null>(null);
  const [backendWarnings, setBackendWarnings] = useState<string[]>([]);
  const [clientWarnings, setClientWarnings] = useState<{ code: string; message: string }[]>([]);
  const w = workspaceId;

  const recompute = useCallback(async () => {
    try {
      const [t, batting, bowling] = await Promise.all([
        api.getInningsTotals(w, matchId, innings.id),
        api.listBatting(w, innings.id),
        api.listBowling(w, innings.id),
      ]);
      setTotals(t);
      setClientWarnings(inningsAdvisories({
        batting: batting.map((b) => ({ person_id: b.person_id, batting_position: b.batting_position, runs: b.runs, dismissal_type: b.dismissal_type, bowler_person_id: b.bowler_person_id })),
        bowling: bowling.map((b) => ({ person_id: b.person_id, wickets: b.wickets, runs_conceded: b.runs_conceded })),
        extras: { byes: innings.byes, legbyes: innings.legbyes, wides: innings.wides, noballs: innings.noballs, penalty: innings.penalty },
        officialTotal: innings.official_total, officialWickets: innings.official_wickets,
      }));
    } catch {
      /* totals are advisory; ignore transient errors */
    }
  }, [w, matchId, innings]);

  useEffect(() => { void recompute(); }, [recompute]);

  const runBackendValidation = async () => {
    try {
      const [i, b, bo, p] = await Promise.all([
        api.validateInnings(w, matchId, innings.id),
        api.validateBatting(w, innings.id),
        api.validateBowling(w, innings.id),
        api.validatePartnerships(w, innings.id),
      ]);
      setBackendWarnings([...i.warnings, ...b.warnings, ...bo.warnings, ...p.warnings]);
      flash("Validation refreshed.");
    } catch (e) {
      onDirty(e instanceof ApiError ? e.message : "Validation failed");
    }
  };

  const patchInnings = async (body: Record<string, unknown>) => {
    try {
      await api.updateInnings(w, matchId, innings.id, body);
      await reloadInnings();
      await recompute();
    } catch (e) {
      onDirty(e instanceof ApiError ? e.message : "Save failed");
    }
  };

  const ctx = { workspaceId: w, inningsId: innings.id, canManage, nameOf, onPersonLoaded: addName,
    onDirty, onChanged: () => void recompute() };

  return (
    <div className="flex flex-col gap-4 rounded-[var(--radius-app)] border border-border p-3">
      <div className="flex flex-wrap items-center gap-3">
        <Field label="Status">
          <Select value={innings.status} disabled={!canManage} onChange={(e) => void patchInnings({ status: e.target.value })} className="w-40">
            {INNINGS_STATUSES.map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
          </Select>
        </Field>
        <div className="text-sm text-muted-foreground">
          Batting: <span className="text-foreground">{teamName(innings.batting_team_id) ?? "—"}</span>
        </div>
      </div>

      <ExtrasRow innings={innings} canManage={canManage} onCommit={patchInnings} />

      <TotalsBar totals={totals} innings={innings} canManage={canManage}
        onOfficial={async (total, wickets, reason) => {
          try { await api.setInningsOfficialTotal(w, matchId, innings.id, { total, wickets, reason }); await reloadInnings(); await recompute(); flash("Official total recorded."); }
          catch (e) { onDirty(e instanceof ApiError ? e.message : "Could not save official total"); }
        }} />

      <SubSection title="Batting"><BattingGrid {...ctx} /></SubSection>
      <SubSection title="Bowling"><BowlingGrid {...ctx} /></SubSection>
      <SubSection title="Fall of wickets"><FowGrid {...ctx} /></SubSection>
      <SubSection title="Partnerships"><PartnershipsGrid {...ctx} /></SubSection>

      <ValidationPanel client={clientWarnings} backend={backendWarnings} onRun={() => void runBackendValidation()} />
    </div>
  );
}

function ExtrasRow({ innings, canManage, onCommit }: { innings: Innings; canManage: boolean; onCommit: (b: Record<string, unknown>) => void }) {
  const fields: { key: keyof Innings; label: string }[] = [
    { key: "byes", label: "Byes" }, { key: "legbyes", label: "Leg byes" }, { key: "wides", label: "Wides" },
    { key: "noballs", label: "No-balls" }, { key: "penalty", label: "Penalty" },
  ];
  return (
    <div>
      <h4 className="mb-1 text-xs font-semibold uppercase text-muted-foreground">Extras</h4>
      <div className="flex flex-wrap gap-3">
        {fields.map((f) => (
          <label key={f.key} className="flex flex-col gap-1 text-xs">
            <span>{f.label}</span>
            <input aria-label={f.label} inputMode="numeric" placeholder="—" disabled={!canManage}
              defaultValue={innings[f.key] === null || innings[f.key] === undefined ? "" : String(innings[f.key])}
              onBlur={(e) => {
                const s = e.target.value.trim();
                const v = s === "" ? null : /^\d+$/.test(s) ? Number.parseInt(s, 10) : null;
                if (v !== innings[f.key]) onCommit({ [f.key]: v });
              }}
              className="w-16 h-8 rounded-[var(--radius-app)] border border-border bg-card px-2 text-sm tabular-nums placeholder:italic placeholder:text-muted-foreground focus-visible:outline-2 focus-visible:outline-[var(--ring)] disabled:opacity-50" />
          </label>
        ))}
      </div>
    </div>
  );
}

function TotalsBar({ totals, innings, canManage, onOfficial }: {
  totals: InningsTotals | null; innings: Innings; canManage: boolean;
  onOfficial: (total: number | null, wickets: number | null, reason: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [total, setTotal] = useState("");
  const [wkts, setWkts] = useState("");
  const [reason, setReason] = useState("");
  return (
    <div className="rounded-[var(--radius-app)] bg-muted/40 px-3 py-2 text-sm">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-1">
        <span className="text-muted-foreground">Extras: <span className="text-foreground tabular-nums">{showNum(totals?.extras_total ?? null)}</span></span>
        <span className="text-muted-foreground">Batting runs: <span className="text-foreground tabular-nums">{showNum(totals?.batting_runs ?? null)}</span></span>
        <span className="text-muted-foreground">Calculated total: <span className="text-brand tabular-nums">{showNum(totals?.derived_total ?? null)}</span></span>
        <span className="text-muted-foreground">Calculated wkts: <span className="text-brand tabular-nums">{showNum(totals?.derived_wickets ?? null)}</span></span>
        <span className="text-muted-foreground">Official: <span className={`tabular-nums ${innings.official_total !== null ? "text-success" : "italic text-muted-foreground"}`}>
          {innings.official_total !== null ? `${innings.official_total}/${showNum(innings.official_wickets)}` : "—"}</span></span>
        {canManage && <button className="ml-auto text-xs text-brand hover:underline" onClick={() => setOpen((v) => !v)}>{open ? "Cancel" : "Record official total"}</button>}
      </div>
      {open && canManage && (
        <div className="mt-2 flex flex-wrap items-end gap-2">
          <label className="flex flex-col gap-1 text-xs">Total<input value={total} onChange={(e) => setTotal(e.target.value)} className="w-20 h-8 rounded-[var(--radius-app)] border border-border bg-card px-2 text-sm" /></label>
          <label className="flex flex-col gap-1 text-xs">Wickets<input value={wkts} onChange={(e) => setWkts(e.target.value)} className="w-20 h-8 rounded-[var(--radius-app)] border border-border bg-card px-2 text-sm" /></label>
          <label className="flex flex-col gap-1 text-xs">Reason / evidence<input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. RMCC scorebook p.4" className="w-56 h-8 rounded-[var(--radius-app)] border border-border bg-card px-2 text-sm" /></label>
          <Button size="sm" onClick={() => { const t = /^\d+$/.test(total.trim()) ? Number(total) : null; const wv = /^\d+$/.test(wkts.trim()) ? Number(wkts) : null; onOfficial(t, wv, reason); setOpen(false); }}>
            <Save className="h-4 w-4" aria-hidden /> Save official
          </Button>
        </div>
      )}
    </div>
  );
}

function ValidationPanel({ client, backend, onRun }: {
  client: { code: string; message: string }[]; backend: string[]; onRun: () => void;
}) {
  return (
    <div className="rounded-[var(--radius-app)] border border-warning/40 bg-warning/5 px-3 py-2">
      <div className="mb-1 flex items-center gap-2">
        <h4 className="text-xs font-semibold uppercase text-warning">Advisory warnings</h4>
        <Button size="sm" variant="outline" onClick={onRun}>Re-check (server)</Button>
      </div>
      {client.length === 0 && backend.length === 0 ? (
        <p className="text-xs text-muted-foreground">No issues detected. Warnings never block saving — incomplete historical cards are allowed.</p>
      ) : (
        <ul className="space-y-1 text-xs">
          {client.map((w) => <li key={`c-${w.code}`} className="text-foreground">• {w.message}</li>)}
          {backend.map((code) => <li key={`b-${code}`} className="text-muted-foreground">• {code.replace(/_/g, " ")} <span className="opacity-60">(server)</span></li>)}
        </ul>
      )}
    </div>
  );
}

function ResultNotesSection({ match, teamName, canManage, onPatch, onResult }: {
  match: MatchDetail; teamName: (id: string | null) => string | null; canManage: boolean;
  onPatch: (b: Record<string, unknown>) => void; onResult: (b: Record<string, unknown>) => void;
}) {
  const [resultType, setResultType] = useState(match.result_type ?? "unknown");
  const [winner, setWinner] = useState(match.won_by_team_id ?? "");
  const [runs, setRuns] = useState(match.margin_runs === null ? "" : String(match.margin_runs));
  const [wkts, setWkts] = useState(match.margin_wickets === null ? "" : String(match.margin_wickets));
  const sides = match.teams.map((t) => t.team_id);
  const workspaceId = useWorkspaceId() ?? "";
  return (
    <Section title="Match result & notes">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Field label="Result">
          <Select value={resultType} disabled={!canManage} onChange={(e) => setResultType(e.target.value)}>
            {RESULT_TYPES.map((r) => <option key={r} value={r}>{r.replace(/_/g, " ")}</option>)}
          </Select>
        </Field>
        <Field label="Won by (team)">
          <Select value={winner} disabled={!canManage} onChange={(e) => setWinner(e.target.value)}>
            <option value="">— n/a —</option>
            {sides.map((id) => <option key={id} value={id}>{teamName(id) ?? "—"}</option>)}
          </Select>
        </Field>
        <Field label="Margin (runs)"><Input value={runs} inputMode="numeric" disabled={!canManage} onChange={(e) => setRuns(e.target.value)} placeholder="—" /></Field>
        <Field label="Margin (wickets)"><Input value={wkts} inputMode="numeric" disabled={!canManage} onChange={(e) => setWkts(e.target.value)} placeholder="—" /></Field>
      </div>
      {canManage && (
        <Button size="sm" className="mt-2" onClick={() => onResult({
          result_type: resultType, won_by_team_id: winner || null,
          margin_runs: /^\d+$/.test(runs.trim()) ? Number(runs) : null,
          margin_wickets: /^\d+$/.test(wkts.trim()) ? Number(wkts) : null,
        })}>Save result</Button>
      )}
      <div className="mt-4">
        <Field label="Notes" hint="Autosaved locally as you type; committed to the record on blur.">
          <Textarea defaultValue={match.notes ?? ""} disabled={!canManage}
            onChange={(e) => persistDraftNote(workspaceId, match.id, { notes: e.target.value })}
            onBlur={(e) => { if ((e.target.value || null) !== match.notes) onPatch({ notes: e.target.value || null }); }} />
        </Field>
      </div>
      <div className="mt-3 flex items-center gap-2">
        <span className="text-xs text-muted-foreground">Match status:</span>
        {MATCH_STATUSES.map((s) => (
          <button key={s} disabled={!canManage} onClick={() => onPatch({ status: s })}
            className={`rounded-[var(--radius-app)] border px-2 py-1 text-xs ${match.status === s ? "border-brand bg-brand/10 text-brand" : "border-border hover:bg-muted"}`}>
            {s}
          </button>
        ))}
        <span className="ml-2 text-xs text-muted-foreground">Draft keeps it editable and out of statistics until finalised.</span>
      </div>
      <DraftNote matchId={match.id} />
    </Section>
  );
}

/** Shows when a local draft of unsaved notes exists for this match (per-viewer convenience). */
function DraftNote({ matchId }: { matchId: string }) {
  const w = useWorkspaceId();
  const [savedAt, setSavedAt] = useState<string | null>(null);
  useEffect(() => {
    if (!w) return;
    try {
      const d = deserializeDraft(localStorage.getItem(draftKey(w, matchId)));
      setSavedAt(d?.savedAt ?? null);
    } catch { /* storage unavailable */ }
  }, [w, matchId]);
  if (!savedAt) return null;
  return <p className="mt-2 text-xs text-muted-foreground">Local draft notes restored (saved {new Date(savedAt).toLocaleString()}).</p>;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card>
      <CardContent className="py-4">
        <h3 className="mb-3 text-sm font-semibold">{title}</h3>
        {children}
      </CardContent>
    </Card>
  );
}

function SubSection({ title, children }: { title: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(true);
  return (
    <div className="rounded-[var(--radius-app)] border border-border">
      <button className="flex w-full items-center justify-between px-3 py-2 text-sm font-medium" onClick={() => setOpen((v) => !v)}>
        {title}<span className="text-xs text-muted-foreground">{open ? "Hide" : "Show"}</span>
      </button>
      {open && <div className="border-t border-border p-3">{children}</div>}
    </div>
  );
}

// expose draft serializer usage so the helper is referenced (notes autosave hook point)
export function persistDraftNote(workspaceId: string, matchId: string, state: Record<string, unknown>) {
  try {
    localStorage.setItem(draftKey(workspaceId, matchId), serializeDraft(state));
  } catch {
    /* storage unavailable — editing still works against the backend */
  }
}
