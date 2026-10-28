/**
 * Integrated scorecard editor (Stage 7, §3): one screen with clearly-organised sections for match
 * details, innings, batting, bowling, extras, fall of wickets, partnerships, and result/notes —
 * moving between them never loses work (each section commits to the Phase 6 API). Non-blocking
 * advisory warnings are shown per innings; genuine integrity/permission errors are surfaced from
 * the backend. A visual legend distinguishes recorded / calculated / unknown / conflicting /
 * verified information.
 */

import {
  AlertTriangle, Check, ChevronLeft, ClipboardCheck, ClipboardList, Coins, Info, Layers, ListOrdered,
  Maximize2, Minimize2, Save, Target, TrendingDown, Trophy, Users,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { ConfirmDialog } from "../../components/ui/dialog";
import { Input, Textarea } from "../../components/ui/input";
import { Select } from "../../components/ui/select";
import { ErrorState, LoadingState } from "../../components/states/States";
import {
  api, ApiError, type Competition, type InningsTotals, type Innings, type MatchDetail, type MatchTeam,
  type Person, type Team, type Venue, type Grade, type Season, type CompetitionDetail, type MatchFormat,
} from "../../lib/api";
import { useLayout } from "../../lib/layout";
import { useWorkspace } from "../../lib/workspace-context";
import { Field } from "../manage/_shared";
import { BattingGrid, BowlingGrid, FowGrid, PartnershipsGrid } from "./grids";
import { PlayerSelect } from "./PlayerSelect";
import { SectionCard, SubPanel, SubtleBar, TeamPanel } from "./ui";
import {
  battingOrderIssues, deserializeDraft, draftKey, formatScore, fowIssues, inningsAdvisories,
  INNINGS_STATUSES, scoreStatusLabel, serializeDraft, showNum,
} from "./scorecard-logic";
import { useScoreFormat } from "../../lib/score-format";

/** "no_toss" -> "No Toss", "in_progress" -> "In Progress" — consistent, readable option labels. */
const titleCase = (s: string) => s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
// Sentence case (first letter only) — natural for result labels like "No result", "Home win".
const sentenceCase = (s: string) => (s.length ? s.charAt(0).toUpperCase() + s.slice(1) : s);

/** Human-readable match result, e.g. "Rhymney/Moyston won by 42 runs" (Phase 7.3). Display only. */
function formatResult(m: MatchDetail, teamName: (id: string | null) => string | null): string {
  const t = m.result_type;
  if (!t || t === "unknown") return "Result not yet determined";
  const labels: Record<string, string> = {
    tie: "Match tied", draw: "Match drawn", no_result: "No result",
    abandoned: "Match abandoned", washout: "Washed out", forfeit: "Match forfeited",
  };
  if (labels[t]) return labels[t];
  const w = teamName(m.won_by_team_id) ?? "Winner";
  if (m.margin_runs != null) return `${w} won by ${m.margin_runs} run${m.margin_runs === 1 ? "" : "s"}`;
  if (m.margin_wickets != null) return `${w} won by ${m.margin_wickets} wicket${m.margin_wickets === 1 ? "" : "s"}`;
  return `${w} won`;
}

/** Prominent innings score header (Phase 7.7): TEAM, big score (AU/EN), status, and breakdown.
 *  Display only — official is shown where set (distinct from calculated); unknowns stay "—". */
function InningsScoreHeader({ teamName, innings, totals, format }: {
  teamName: (id: string | null) => string | null; innings: Innings;
  totals: InningsTotals | null; format: "au" | "en";
}) {
  const isOfficial = totals?.official_total != null;
  const runs = totals ? (totals.official_total ?? totals.derived_total) : null;
  const wkts = totals ? (isOfficial ? totals.official_wickets : totals.derived_wickets) : null;
  const status = scoreStatusLabel(wkts, innings.status);
  return (
    <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 rounded-[var(--radius-app)] border border-border bg-muted/30 p-3">
      <span className="text-sm font-semibold uppercase tracking-wide">{teamName(innings.batting_team_id) ?? "Batting team"}</span>
      <span className="text-3xl font-bold tabular-nums text-brand">{formatScore(runs, wkts, { format, declared: innings.status === "declared" })}</span>
      {status && <span className="text-sm text-muted-foreground">{status}</span>}
      <span className="ml-auto text-xs text-muted-foreground">
        Batting {showNum(totals?.batting_runs ?? null)} · Extras {showNum(totals?.extras_total ?? null)} · Total {showNum(runs)} {isOfficial ? "(official)" : runs != null ? "(calculated)" : ""}
      </span>
    </div>
  );
}

/** Scorecard approval workflow bar (Phase 7.1): status, transitions (separate from match status),
 *  and the aggregated validation warnings. Approved scorecards are authoritative for official stats. */
function ApprovalBar({ match, canManage, onAction }: {
  match: MatchDetail; canManage: boolean;
  onAction: (action: "submit" | "approve" | "reject" | "reopen", reason?: string) => void;
}) {
  const [reason, setReason] = useState("");
  const st = match.approval_status ?? "draft";
  const warnings = match.validation ?? [];
  const humanise = (c: string) => c.replace(/_/g, " ").replace(/:.*/, "").replace(/^\w/, (x) => x.toUpperCase());
  return (
    <SectionCard icon={ClipboardCheck} title="Scorecard Approval"
      description="Separate from the match status. Only an approved scorecard contributes to official statistics.">
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-muted-foreground">Status:</span>
          <Badge variant={st === "approved" ? "success" : st === "rejected" ? "warning" : st === "awaiting_approval" ? "outline" : "muted"}>{titleCase(st)}</Badge>
          {match.revised_since_approval && <span className="text-xs text-warning">Edited since approval — re-approve to update official statistics (the last approved version is kept meanwhile).</span>}
          {st === "rejected" && match.approval_reason && <span className="text-xs text-muted-foreground">Reason: {match.approval_reason}</span>}
          {st === "approved" && match.approved_at && <span className="text-xs text-muted-foreground">Approved {new Date(match.approved_at).toLocaleString()}</span>}
        </div>
        {canManage && (
          <div className="flex flex-wrap items-end gap-2">
            {(st === "awaiting_approval" || st === "rejected") && (
              <label className="flex flex-col gap-1 text-xs">Reason (for rejection)
                <Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="optional" className="w-64" />
              </label>
            )}
            {st === "draft" && <Button size="sm" onClick={() => onAction("submit")}>Submit for approval</Button>}
            {st === "rejected" && <Button size="sm" onClick={() => onAction("submit")}>Resubmit</Button>}
            {st === "awaiting_approval" && <Button size="sm" onClick={() => onAction("approve")}>Approve</Button>}
            {st === "awaiting_approval" && <Button size="sm" variant="outline" onClick={() => onAction("reject", reason || undefined)}>Reject</Button>}
            {(st === "approved" || st === "rejected" || st === "awaiting_approval") && <Button size="sm" variant="ghost" onClick={() => onAction("reopen")}>Reopen to draft</Button>}
          </div>
        )}
        {warnings.length > 0 && (
          <div className="rounded-[var(--radius-app)] border border-warning/40 bg-warning/5 p-3 text-xs">
            <p className="mb-1 flex items-center gap-1 font-medium text-warning"><AlertTriangle className="h-3.5 w-3.5" aria-hidden /> Validation — {warnings.length} item(s) for review (advisory; incomplete historical records remain valid)</p>
            <ul className="flex flex-col gap-0.5">
              {warnings.map((w, i) => <li key={i}><span className="font-medium">{w.scope} · {w.area}:</span> {humanise(w.code)}</li>)}
            </ul>
          </div>
        )}
      </div>
    </SectionCard>
  );
}

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
  // the club (organisation) behind a team — used to scope player selectors to that club (Phase 7.4)
  const teamOrg = useCallback((id: string | null) => (id ? teams.find((t) => t.id === id)?.organisation_id ?? null : null), [teams]);
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

  // Focus Mode: a distraction-free entry layout. It collapses the sidebar and hides the secondary
  // match sections (without unmounting them, so unsaved edits are preserved), leaving the scorecard
  // expanded. It never saves, navigates or changes match data/status.
  const { sidebarCollapsed, setSidebarCollapsed } = useLayout();
  const [focus, setFocus] = useState(false);
  const prevSidebar = useRef(sidebarCollapsed);
  const enterFocus = () => { prevSidebar.current = sidebarCollapsed; setSidebarCollapsed(true); setFocus(true); };
  const exitFocus = useCallback(() => { setFocus(false); setSidebarCollapsed(prevSidebar.current); }, [setSidebarCollapsed]);
  useEffect(() => {
    if (!focus) return;
    const onKey = (e: KeyboardEvent) => {
      // Escape exits — but only when nothing else needs it (no open modal/dialog).
      if (e.key === "Escape" && !document.querySelector('[role="dialog"]')) {
        e.preventDefault();
        exitFocus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [focus, exitFocus]);

  const patchMatch = async (body: Record<string, unknown>) => {
    try {
      await api.updateMatch(workspaceId, matchId, body);
      await load();
      onSaved();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Save failed");
    }
  };

  // Only the FIRST load replaces the editor with a full-screen loader. A refetch (after an edit)
  // keeps the editor mounted so child components never remount and lose unsaved local state — e.g.
  // an in-progress classification selection. (Matches the Focus-Mode intent above.)
  if (loading && !match) return <LoadingState label="Loading scorecard…" />;
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
        <Badge variant={match.approval_status === "approved" ? "success" : match.approval_status === "rejected" ? "warning" : match.approval_status === "awaiting_approval" ? "outline" : "muted"}>
          {titleCase(match.approval_status ?? "draft")}
        </Badge>
        {match.revised_since_approval && <Badge variant="warning">revised since approval</Badge>}
        {match.classification !== "unclassified" && <Badge variant="brand">{titleCase(match.classification)}</Badge>}
        <div className="flex-1" />
        {msg && <span className="text-sm text-success">{msg}</span>}
        {err && <span className="text-sm text-danger">{err}</span>}
        <Button variant="outline" size="sm" onClick={() => (focus ? exitFocus() : enterFocus())}
          aria-pressed={focus} title={focus ? "Exit Focus Mode (Esc)" : "Focus Mode"}>
          {focus ? <Minimize2 className="h-4 w-4" aria-hidden /> : <Maximize2 className="h-4 w-4" aria-hidden />}
          {focus ? "Exit Focus Mode" : "Focus Mode"}
        </Button>
      </div>

      {focus && (
        <p className="rounded-[var(--radius-app)] bg-muted/50 px-3 py-1.5 text-xs text-muted-foreground">
          Focus Mode — match details, toss and result are hidden (not changed). Press <kbd className="rounded border border-border bg-card px-1">Esc</kbd> or Exit Focus Mode to restore.
        </p>
      )}

      <div className={focus ? "hidden" : "contents"}>
        <Legend />

        <ApprovalBar match={match} canManage={canManage}
          onAction={async (action, reason) => {
            try { await api.matchApproval(workspaceId, matchId, action, reason); await load(); flash("Approval updated."); }
            catch (e) { setErr(e instanceof ApiError ? e.message : "Could not update approval."); }
          }} />

        <MatchDetailsSection
          match={match} teams={teams} venues={venues} comps={comps} compDetail={compDetail}
          canManage={canManage} teamName={teamName} reload={load}
          onComp={async (cid) => { await patchMatch({ competition_id: cid || null }); }}
          onPatch={patchMatch}
          onSetTeam={async (team_id, is_home) => {
            try { await api.setMatchTeam(workspaceId, matchId, { team_id, is_home }); await load(); }
            catch (e) { setErr(e instanceof ApiError ? e.message : "Could not set team"); }
          }}
        />

        <TossAndOfficialsSection
          workspaceId={workspaceId} matchId={matchId} match={match} canManage={canManage}
          teamName={teamName} teamOrg={teamOrg} nameOf={nameOf} addName={addName}
          reload={async () => { setMatch(await api.getMatch(workspaceId, matchId)); }}
          onError={(m) => setErr(m)} flash={flash}
        />
      </div>

      <InningsSection
        workspaceId={workspaceId} matchId={matchId} match={match} innings={innings}
        canManage={canManage} activeInnings={activeInnings} setActiveInnings={setActiveInnings}
        nameOf={nameOf} teamName={teamName} teamOrg={teamOrg} addName={addName}
        reloadInnings={async () => setInnings(await api.listInnings(workspaceId, matchId))}
        onDirty={(m) => m && setErr(m)} flash={flash}
      />

      <div className={focus ? "hidden" : "contents"}>
        <ResultNotesSection match={match} teamName={teamName} canManage={canManage} onPatch={patchMatch}
          onResult={async (body) => {
            try { await api.setMatchResult(workspaceId, matchId, body); await load(); flash("Result saved."); }
            catch (e) { setErr(e instanceof ApiError ? e.message : "Could not save result"); }
          }} />
        <MatchSourcesSection workspaceId={workspaceId} matchId={matchId} />
      </div>
    </div>
  );
}

function MatchSourcesSection({ workspaceId, matchId }: { workspaceId: string; matchId: string }) {
  const [sources, setSources] = useState<import("../../lib/api").MatchSource[]>([]);
  const [conflicts, setConflicts] = useState<import("../../lib/api").MatchSourceConflict[]>([]);
  useEffect(() => {
    let alive = true;
    void api.matchSources(workspaceId, matchId)
      .then((r) => { if (alive) { setSources(r.sources); setConflicts(r.conflicts); } })
      .catch(() => { /* provenance is best-effort */ });
    return () => { alive = false; };
  }, [workspaceId, matchId]);
  if (sources.length === 0) return null;
  return (
    <SectionCard icon={ClipboardList} title="Sources & Provenance"
      description="Where this match came from. Additional sources are kept as evidence; conflicting accounts are flagged, never auto-resolved.">
      <ul className="flex flex-col gap-1 text-sm">
        {sources.map((s) => (
          <li key={s.id} className="flex flex-wrap items-center gap-2">
            <Badge variant="outline">{s.source_system}</Badge>
            <span className="text-muted-foreground">{s.source_ref}</span>
            {s.edition && <span className="text-xs">· {s.edition}</span>}
            {s.source_filename && <span className="text-xs text-muted-foreground">· {s.source_filename}</span>}
          </li>
        ))}
      </ul>
      {conflicts.length > 0 && (
        <div className="mt-3 rounded-[var(--radius-app)] border border-warning/40 bg-warning/5 p-2 text-xs">
          <div className="mb-1 font-medium text-warning">Conflicting source information — review, do not assume</div>
          {conflicts.map((c) => (
            <div key={c.field} className="mb-1">
              <span className="font-medium">{c.field.replace(/_/g, " ")}:</span>{" "}
              {c.values.map((v, i) => (
                <span key={i} className="text-muted-foreground">{i > 0 ? " · " : ""}{String(v.value)} <span className="opacity-60">({v.source_system})</span></span>
              ))}
            </div>
          ))}
        </div>
      )}
    </SectionCard>
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
  match, teams, venues, comps, compDetail, canManage, teamName, onComp, onPatch, onSetTeam, reload,
}: {
  match: MatchDetail; teams: Team[]; venues: Venue[]; comps: Competition[]; compDetail: CompetitionDetail | null;
  canManage: boolean; teamName: (id: string | null) => string | null;
  onComp: (cid: string) => void; onPatch: (b: Record<string, unknown>) => void;
  onSetTeam: (teamId: string, isHome: boolean) => void; reload: () => Promise<void>;
}) {
  const home = match.teams.find((t) => t.is_home)?.team_id ?? "";
  const away = match.teams.find((t) => !t.is_home)?.team_id ?? "";
  const grades: Grade[] = compDetail?.grades ?? [];
  const seasons: Season[] = compDetail?.seasons ?? [];
  const workspaceId = useWorkspaceId() ?? "";
  const [formats, setFormats] = useState<MatchFormat[]>([]);
  useEffect(() => {
    if (workspaceId) api.listMatchFormats(workspaceId, { enabled_only: true }).then(setFormats).catch(() => {});
  }, [workspaceId]);
  return (
    <SectionCard icon={ClipboardList} title="Match Details"
      description="Competition, grade, season, venue, date and the explicit classification.">
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
        <Field label="Season" hint={(match.season_warnings?.length ?? 0) > 0 ? "Season unresolved — set the competition's season rule (Competitions) or choose a season here." : undefined}>
          <Select value={match.season_id ?? ""} disabled={!canManage || !seasons.length} onChange={(e) => onPatch({ season_id: e.target.value || null })}
            className={(match.season_warnings?.length ?? 0) > 0 ? "border-warning/60" : undefined}>
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
          {/* commit on blur (not on every change) so the reload never re-renders mid-edit and
              closes the date picker; keyed to the match so switching matches refreshes the value */}
          <Input key={match.id} type="date" defaultValue={match.match_date ?? ""} disabled={!canManage}
            onBlur={(e) => { if ((e.target.value || null) !== match.match_date) onPatch({ match_date: e.target.value || null }); }} />
        </Field>
        <Field label="Format" hint="Playing format only — separate from the statistical classification. Configure the list in Settings.">
          <Select value={match.format ?? ""} disabled={!canManage}
            onChange={(e) => { if ((e.target.value || null) !== match.format) onPatch({ format: e.target.value || null }); }}>
            <option value="">— none —</option>
            {/* preserve a historical/imported/disabled value that isn't in the enabled list */}
            {match.format && !formats.some((f) => f.label === match.format) &&
              <option value={match.format}>{match.format} (current)</option>}
            {formats.map((f) => <option key={f.id} value={f.label}>{f.label}{f.is_default ? " (default)" : ""}</option>)}
          </Select>
        </Field>
        <Field label="Round" hint="A label only — never used to classify the match.">
          <Input defaultValue={match.round ?? ""} placeholder="e.g. Round 5, GF" disabled={!canManage}
            onBlur={(e) => { if ((e.target.value || null) !== match.round) onPatch({ round: e.target.value || null }); }} />
        </Field>
      </div>

      <ClassificationControl match={match} canManage={canManage} reload={reload} />

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <TeamPanel side="home" teamName={teamName(home || null)}>
          <Field label="Home team">
            <Select value={home} disabled={!canManage} onChange={(e) => e.target.value && onSetTeam(e.target.value, true)}>
              <option value="">— select —</option>
              {teams.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </Select>
          </Field>
        </TeamPanel>
        <TeamPanel side="away" teamName={teamName(away || null)}>
          <Field label="Away team">
            <Select value={away} disabled={!canManage} onChange={(e) => e.target.value && onSetTeam(e.target.value, false)}>
              <option value="">— select —</option>
              {teams.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </Select>
          </Field>
        </TeamPanel>
      </div>
    </SectionCard>
  );
}

function ClassificationControl({ match, canManage, reload }: {
  match: MatchDetail; canManage: boolean; reload?: () => Promise<void>;
}) {
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
      await reload?.();   // refresh the match so the classification badge reflects the saved value
      setDone(true);
      setTimeout(() => setDone(false), 2000);
    } finally {
      setBusy(false);
    }
  };
  const isFinal = cls === "final" || cls === "grand_final" || cls === "other";
  return (
    <div className="mt-4 rounded-[var(--radius-app)] border border-border bg-muted/30 p-3">
      <div className="mb-2 flex items-center gap-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Classification</span>
        <span className="text-xs text-muted-foreground">— explicit; never taken from the round label.</span>
      </div>
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Type">
          <Select value={cls} disabled={!canManage} onChange={(e) => setCls(e.target.value)} className="w-40">
            {CLASSIFICATIONS.map((c) => <option key={c} value={c}>{titleCase(c)}</option>)}
          </Select>
        </Field>
        {isFinal && (
          <Field label="Finals stage">
            <Select value={stage} disabled={!canManage} onChange={(e) => setStage(e.target.value)} className="w-44">
              <option value="">— unspecified —</option>
              {FINALS_STAGES.map((s) => <option key={s} value={s}>{titleCase(s)}</option>)}
            </Select>
          </Field>
        )}
        <label className="flex items-center gap-2 pb-2 text-sm"
          title="Tick only when this classification is confirmed against a reliable source. Unverified classifications are kept but flagged for review. Never auto-ticked.">
          <input type="checkbox" checked={verified} disabled={!canManage} onChange={(e) => setVerified(e.target.checked)}
            className="h-4 w-4 focus-visible:outline-2 focus-visible:outline-[var(--ring)]" />
          <span>Verified</span>
        </label>
        {canManage && (
          <Button size="sm" variant="outline" onClick={() => void save()} disabled={busy} className="sm:mb-0.5">
            {done ? "Saved" : busy ? "Saving…" : "Set Classification"}
          </Button>
        )}
      </div>
      <p className="mt-2 text-xs text-muted-foreground">
        “Verified” marks the classification as confirmed against a source — it is advisory, never set automatically.
      </p>
    </div>
  );
}

// tiny workspace-id accessor without threading props everywhere (reads the same context the app uses)
function useWorkspaceId(): string | null {
  const { current } = useWorkspace();
  return current?.id ?? null;
}

const TOSS_DECISIONS = ["bat", "field", "no_toss", "not_recorded", "unknown"];

function TossAndOfficialsSection({
  workspaceId, matchId, match, canManage, teamName, teamOrg, nameOf, addName, reload, onError, flash,
}: {
  workspaceId: string; matchId: string; match: MatchDetail; canManage: boolean;
  teamName: (id: string | null) => string | null; teamOrg: (id: string | null) => string | null;
  nameOf: (id: string | null) => string | null;
  addName: (p: Person) => void; reload: () => Promise<void>; onError: (m: string) => void; flash: (m: string) => void;
}) {
  const sides = match.teams; // one home, one away (where recorded)
  const [tossWinner, setTossWinner] = useState(match.toss_winner_team_id ?? "");
  const [tossDecision, setTossDecision] = useState(match.toss_decision ?? "");

  const saveToss = async () => {
    try {
      await api.setMatchToss(workspaceId, matchId, {
        toss_winner_team_id: tossWinner || null, toss_decision: tossDecision || null,
      });
      await reload();
      flash("Toss recorded.");
    } catch (e) {
      onError(e instanceof ApiError ? e.message : "Could not save toss");
    }
  };

  const saveOfficial = async (mt: MatchTeam, patch: Partial<MatchTeam>) => {
    // set_team replaces the whole side row, so send the complete current officials each time.
    try {
      await api.setMatchTeam(workspaceId, matchId, {
        team_id: mt.team_id, is_home: mt.is_home,
        captain_person_id: patch.captain_person_id !== undefined ? patch.captain_person_id : mt.captain_person_id,
        acting_captain_person_id: patch.acting_captain_person_id !== undefined ? patch.acting_captain_person_id : mt.acting_captain_person_id,
        wicketkeeper_person_id: patch.wicketkeeper_person_id !== undefined ? patch.wicketkeeper_person_id : mt.wicketkeeper_person_id,
        wicketkeeper2_person_id: patch.wicketkeeper2_person_id !== undefined ? patch.wicketkeeper2_person_id : mt.wicketkeeper2_person_id,
      });
      await reload();
    } catch (e) {
      onError(e instanceof ApiError ? e.message : "Could not save officials");
    }
  };

  return (
    <SectionCard icon={Coins} title="Toss, Captains and Wicketkeepers"
      description="Recorded explicitly — the toss is never inferred from who batted first.">
      <div className="mb-4 rounded-[var(--radius-app)] border border-border bg-muted/30 p-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <div className="flex-1">
            <Field label="Toss won by">
              <Select value={tossWinner} disabled={!canManage} onChange={(e) => setTossWinner(e.target.value)}>
                <option value="">— unknown —</option>
                {sides.map((s) => <option key={s.team_id} value={s.team_id}>{teamName(s.team_id) ?? (s.is_home ? "Home" : "Away")}</option>)}
              </Select>
            </Field>
          </div>
          <div className="flex-1">
            <Field label="Decision">
              <Select value={tossDecision} disabled={!canManage} onChange={(e) => setTossDecision(e.target.value)}>
                <option value="">— unknown —</option>
                {TOSS_DECISIONS.map((d) => <option key={d} value={d}>{titleCase(d)}</option>)}
              </Select>
            </Field>
          </div>
          {canManage && (
            <Button size="sm" onClick={() => void saveToss()} className="shrink-0">Save Toss</Button>
          )}
        </div>
      </div>

      {sides.length === 0 && <p className="text-sm text-muted-foreground">Set the home and away teams above to record captains and wicketkeepers.</p>}
      <div className="grid gap-4 sm:grid-cols-2">
        {sides.map((mt) => {
          const org = teamOrg(mt.team_id); const club = teamName(mt.team_id);
          return (
          <TeamPanel key={mt.id} side={mt.is_home ? "home" : "away"} teamName={club}>
            <div className="flex flex-col gap-2">
              <Field label="Captain">
                <PlayerSelect workspaceId={workspaceId} value={mt.captain_person_id} nameOf={nameOf} onPersonLoaded={addName}
                  disabled={!canManage} aria-label="Captain" roleLabel="Captain" organisationId={org} scopeLabel={club}
                  onChange={(pid) => void saveOfficial(mt, { captain_person_id: pid })} />
              </Field>
              <Field label="Acting / replacement captain">
                <PlayerSelect workspaceId={workspaceId} value={mt.acting_captain_person_id} nameOf={nameOf} onPersonLoaded={addName}
                  disabled={!canManage} aria-label="Acting captain" roleLabel="Captain" organisationId={org} scopeLabel={club}
                  onChange={(pid) => void saveOfficial(mt, { acting_captain_person_id: pid })} />
              </Field>
              <Field label="Wicketkeeper">
                <PlayerSelect workspaceId={workspaceId} value={mt.wicketkeeper_person_id} nameOf={nameOf} onPersonLoaded={addName}
                  disabled={!canManage} aria-label="Wicketkeeper" roleLabel="Wicketkeeper" organisationId={org} scopeLabel={club}
                  onChange={(pid) => void saveOfficial(mt, { wicketkeeper_person_id: pid })} />
              </Field>
              <Field label="Second / replacement keeper">
                <PlayerSelect workspaceId={workspaceId} value={mt.wicketkeeper2_person_id} nameOf={nameOf} onPersonLoaded={addName}
                  disabled={!canManage} aria-label="Second wicketkeeper" roleLabel="Wicketkeeper" organisationId={org} scopeLabel={club}
                  onChange={(pid) => void saveOfficial(mt, { wicketkeeper2_person_id: pid })} />
              </Field>
            </div>
          </TeamPanel>
          );
        })}
      </div>
    </SectionCard>
  );
}

function InningsSection({
  workspaceId, matchId, match, innings, canManage, activeInnings, setActiveInnings,
  nameOf, teamName, teamOrg, addName, reloadInnings, onDirty, flash,
}: {
  workspaceId: string; matchId: string; match: MatchDetail; innings: Innings[];
  canManage: boolean; activeInnings: string | null; setActiveInnings: (id: string) => void;
  nameOf: (id: string | null) => string | null; teamName: (id: string | null) => string | null;
  teamOrg: (id: string | null) => string | null;
  addName: (p: Person) => void; reloadInnings: () => Promise<void>; onDirty: (m: string | null) => void; flash: (m: string) => void;
}) {
  const fmt = useScoreFormat();
  const [scores, setScores] = useState<Record<string, InningsTotals>>({});
  const [scoreKey, setScoreKey] = useState(0);
  useEffect(() => {
    let live = true;
    Promise.all(innings.map((i) =>
      api.getInningsTotals(workspaceId, matchId, i.id).then((t) => [i.id, t] as const).catch(() => null)))
      .then((rs) => { if (live) setScores(Object.fromEntries(rs.filter(Boolean) as [string, InningsTotals][])); });
    return () => { live = false; };
  }, [workspaceId, matchId, innings, scoreKey]);

  // the tab/header score for an innings: official where set, else calculated (distinction kept)
  const tabScore = (id: string, status: string | null): string => {
    const t = scores[id];
    if (!t) return "—";
    const runs = t.official_total ?? t.derived_total;
    const wkts = t.official_total !== null ? t.official_wickets : t.derived_wickets;
    return formatScore(runs, wkts, { format: fmt, declared: status === "declared" });
  };

  const addInnings = async () => {
    const n = innings.length + 1;
    // Do NOT assume the home team bats first: create the innings with an UNKNOWN batting side;
    // the user chooses it in the innings header (supporting follow-ons and unknown order).
    try {
      const created = await api.createInnings(workspaceId, matchId, {
        inns_number: n, batting_team_id: null, bowling_team_id: null,
      });
      await reloadInnings();
      setActiveInnings(created.id);
    } catch (e) {
      onDirty(e instanceof ApiError ? e.message : "Could not add innings");
    }
  };

  const active = innings.find((i) => i.id === activeInnings) ?? null;
  return (
    <SectionCard icon={Layers} title="Innings" description="Batting, bowling, extras, fall of wickets and partnerships.">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        {innings.map((i) => (
          <button key={i.id} onClick={() => setActiveInnings(i.id)}
            className={`flex flex-col items-start rounded-[var(--radius-app)] border px-3 py-1 text-sm ${i.id === activeInnings ? "border-brand bg-brand/10 text-brand" : "border-border hover:bg-muted"}`}>
            <span>Innings {i.inns_number} <span className="text-xs text-muted-foreground">{teamName(i.batting_team_id) ?? "—"}</span></span>
            <span className="font-semibold tabular-nums">{tabScore(i.id, i.status)}</span>
          </button>
        ))}
        {canManage && (
          <Button size="sm" variant="outline" onClick={() => void addInnings()}>Add innings</Button>
        )}
      </div>
      {!active && <p className="text-sm text-muted-foreground">No innings yet. Add the first innings to begin entry.</p>}
      {active && (
        <InningsEditor key={active.id} workspaceId={workspaceId} matchId={matchId} innings={active}
          canManage={canManage} nameOf={nameOf} teamName={teamName} teamOrg={teamOrg} addName={addName}
          sides={{ home: match.teams.find((t) => t.is_home)?.team_id ?? null,
                   away: match.teams.find((t) => !t.is_home)?.team_id ?? null }}
          reloadInnings={reloadInnings} onDirty={onDirty} flash={flash}
          onScoreChanged={() => setScoreKey((k) => k + 1)} />
      )}
    </SectionCard>
  );
}

function InningsEditor({
  workspaceId, matchId, innings, canManage, nameOf, teamName, teamOrg, addName, sides, reloadInnings, onDirty, flash, onScoreChanged,
}: {
  workspaceId: string; matchId: string; innings: Innings; canManage: boolean;
  nameOf: (id: string | null) => string | null; teamName: (id: string | null) => string | null;
  teamOrg: (id: string | null) => string | null;
  addName: (p: Person) => void; sides: { home: string | null; away: string | null };
  reloadInnings: () => Promise<void>; onDirty: (m: string | null) => void; flash: (m: string) => void;
  onScoreChanged?: () => void;
}) {
  const fmt = useScoreFormat();
  const [totals, setTotals] = useState<InningsTotals | null>(null);
  const [backendWarnings, setBackendWarnings] = useState<string[]>([]);
  const [clientWarnings, setClientWarnings] = useState<{ code: string; message: string }[]>([]);
  const [pendingBatting, setPendingBatting] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);  // bumped so sibling grids re-fetch (e.g. FOW -> partnerships)
  const w = workspaceId;

  const recompute = useCallback(async () => {
    try {
      const [t, batting, bowling, fows] = await Promise.all([
        api.getInningsTotals(w, matchId, innings.id),
        api.listBatting(w, innings.id),
        api.listBowling(w, innings.id),
        api.listFow(w, innings.id),
      ]);
      setTotals(t);
      // merge the batting/bowling/extras advisories with the immediate FOW and batting-order ones,
      // deduped by code, so the panel reflects these without a manual server re-check
      const merged = [
        ...inningsAdvisories({
          batting: batting.map((b) => ({ person_id: b.person_id, batting_position: b.batting_position, runs: b.runs, dismissal_type: b.dismissal_type, bowler_person_id: b.bowler_person_id })),
          bowling: bowling.map((b) => ({ person_id: b.person_id, wickets: b.wickets, runs_conceded: b.runs_conceded })),
          extras: { byes: innings.byes, legbyes: innings.legbyes, wides: innings.wides, noballs: innings.noballs, penalty: innings.penalty },
          officialTotal: innings.official_total, officialWickets: innings.official_wickets,
        }),
        ...fowIssues(fows.map((f) => ({ id: f.id, wicket_number: f.wicket_number, team_score: f.team_score }))).messages,
        ...battingOrderIssues(batting.map((b) => ({ id: b.id, batting_position: b.batting_position, person_id: b.person_id }))).messages,
      ];
      const byCode = new Map(merged.map((m) => [m.code, m]));
      setClientWarnings([...byCode.values()]);
      onScoreChanged?.();  // let the innings tabs refresh their scores
    } catch {
      /* totals are advisory; ignore transient errors */
    }
  }, [w, matchId, innings, onScoreChanged]);

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
    onDirty, refreshKey, onChanged: () => { setRefreshKey((k) => k + 1); void recompute(); },
    battingOrgId: teamOrg(innings.batting_team_id), bowlingOrgId: teamOrg(innings.bowling_team_id),
    battingTeamName: teamName(innings.batting_team_id), bowlingTeamName: teamName(innings.bowling_team_id) };

  // Batting side is explicit (never assumed). Choosing it sets bowling to the other recorded side.
  const applyBatting = (battingId: string | null) => {
    const other = battingId && battingId === sides.home ? sides.away
      : battingId && battingId === sides.away ? sides.home : null;
    void patchInnings({ batting_team_id: battingId, bowling_team_id: other });
  };
  const changeBatting = (battingId: string | null) => {
    if (innings.batting_team_id && battingId && battingId !== innings.batting_team_id) {
      setPendingBatting(battingId);  // confirm before reassigning an existing innings' batting team
    } else {
      applyBatting(battingId);
    }
  };
  const sideOptions = [
    ...(sides.home ? [{ id: sides.home, label: teamName(sides.home) ?? "Home" }] : []),
    ...(sides.away ? [{ id: sides.away, label: teamName(sides.away) ?? "Away" }] : []),
  ];

  return (
    <div className="flex flex-col gap-4 rounded-[var(--radius-app)] border border-border p-3">
      <InningsScoreHeader teamName={teamName} innings={innings} totals={totals} format={fmt} />
      {/* aligned responsive grid: labels on one row, controls of equal height on the next */}
      <div className="grid items-start gap-3 sm:grid-cols-3">
        <Field label="Batting team" hint="Not assumed from home/away — choose who batted.">
          <Select value={innings.batting_team_id ?? ""} disabled={!canManage}
            onChange={(e) => changeBatting(e.target.value || null)}>
            <option value="">— unknown —</option>
            {sideOptions.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
          </Select>
        </Field>
        <Field label="Innings status">
          <Select value={innings.status} disabled={!canManage} onChange={(e) => void patchInnings({ status: e.target.value })}>
            {INNINGS_STATUSES.map((s) => <option key={s} value={s}>{titleCase(s)}</option>)}
          </Select>
        </Field>
        <Field label="Bowling team">
          <div className="flex h-9 items-center rounded-[var(--radius-app)] border border-border bg-muted/40 px-3 text-sm">
            <span className={teamName(innings.bowling_team_id) ? "text-foreground" : "italic text-muted-foreground"}>
              {teamName(innings.bowling_team_id) ?? "—"}
            </span>
          </div>
        </Field>
      </div>
      <ConfirmDialog
        open={pendingBatting !== null}
        title="Change batting team?"
        description={`This innings is currently recorded as ${teamName(innings.batting_team_id) ?? "a team"} batting. Reassign it to ${teamName(pendingBatting) ?? "the selected team"}? Batting and bowling figures already entered stay attached to this innings.`}
        confirmLabel="Reassign"
        onCancel={() => setPendingBatting(null)}
        onConfirm={() => { applyBatting(pendingBatting); setPendingBatting(null); }}
      />

      <ExtrasRow innings={innings} canManage={canManage} onCommit={patchInnings} />

      <TotalsBar totals={totals} innings={innings} canManage={canManage}
        onOfficial={async (total, wickets, reason) => {
          try { await api.setInningsOfficialTotal(w, matchId, innings.id, { total, wickets, reason }); await reloadInnings(); await recompute(); flash("Official total recorded."); }
          catch (e) { onDirty(e instanceof ApiError ? e.message : "Could not save official total"); }
        }} />

      <SubPanel icon={ListOrdered} title="Batting"><BattingGrid {...ctx} /></SubPanel>
      <SubPanel icon={Target} title="Bowling"><BowlingGrid {...ctx} /></SubPanel>
      <SubPanel icon={TrendingDown} title="Fall of Wickets"><FowGrid {...ctx} /></SubPanel>
      <SubPanel icon={Users} title="Partnerships"><PartnershipsGrid {...ctx} /></SubPanel>

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

export function TotalsBar({ totals, innings, canManage, onOfficial }: {
  totals: InningsTotals | null; innings: Innings; canManage: boolean;
  onOfficial: (total: number | null, wickets: number | null, reason: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [total, setTotal] = useState("");
  const [wkts, setWkts] = useState("");
  const [reason, setReason] = useState("");
  const calcTotal = totals?.derived_total ?? null;
  const calcWkts = totals?.derived_wickets ?? null;
  const officialSet = innings.official_total !== null;
  // the common case: the scorecard adds up, so confirm it in one click rather than re-typing it
  const matchesCalc = officialSet && calcTotal !== null && innings.official_total === calcTotal
    && (innings.official_wickets ?? null) === (calcWkts ?? null);
  const openOverride = () => {
    // prefill the override with the calculated figures so even a correction is minimal typing
    setTotal(calcTotal !== null ? String(calcTotal) : (officialSet ? String(innings.official_total) : ""));
    setWkts(calcWkts !== null ? String(calcWkts) : (innings.official_wickets !== null ? String(innings.official_wickets) : ""));
    setReason("");
    setOpen(true);
  };
  return (
    <div className="flex flex-col gap-2">
      <SubtleBar>
        <span className="text-muted-foreground">Extras: <span className="text-foreground tabular-nums">{showNum(totals?.extras_total ?? null)}</span></span>
        <span className="text-muted-foreground">Batting runs: <span className="text-foreground tabular-nums">{showNum(totals?.batting_runs ?? null)}</span></span>
        <span className="text-muted-foreground">Calculated total: <span className="text-brand tabular-nums">{showNum(calcTotal)}</span></span>
        <span className="text-muted-foreground">Calculated wkts: <span className="text-brand tabular-nums">{showNum(calcWkts)}</span></span>
        <span className="text-muted-foreground">Official: <span className={`tabular-nums ${officialSet ? "text-success" : "italic text-muted-foreground"}`}>
          {officialSet ? `${innings.official_total}/${showNum(innings.official_wickets)}` : "—"}</span></span>
        <span className="text-muted-foreground">Overs: <span className="text-foreground tabular-nums">{totals?.overs_bowled ?? "—"}</span></span>
        <span className="text-muted-foreground">Run rate: <span className="text-foreground tabular-nums">{totals?.run_rate != null ? totals.run_rate.toFixed(2) : "—"}</span></span>
        {canManage && (
          <div className="ml-auto flex items-center gap-3">
            {matchesCalc ? (
              <span className="flex items-center gap-1 text-xs text-success"><Check className="h-3.5 w-3.5" aria-hidden /> Confirmed from scorecard</span>
            ) : calcTotal !== null && (
              <Button size="sm" onClick={() => onOfficial(calcTotal, calcWkts, "Confirmed from scorecard")}>
                <Check className="h-4 w-4" aria-hidden /> Confirm total {calcTotal}/{showNum(calcWkts)}
              </Button>
            )}
            <button className="text-xs font-medium text-brand hover:underline" onClick={() => (open ? setOpen(false) : openOverride())}>
              {open ? "Cancel" : calcTotal !== null ? "Different total" : "Record official total"}
            </button>
          </div>
        )}
      </SubtleBar>
      {open && canManage && (
        <div className="flex flex-wrap items-end gap-2 rounded-[var(--radius-app)] border border-border bg-card p-3">
          <p className="w-full text-xs text-muted-foreground">Use this only when the scoresheet's official total differs from the card (e.g. an incomplete or amended card). It is kept as the authoritative total alongside the calculated one.</p>
          <label className="flex flex-col gap-1 text-xs">Total<input value={total} onChange={(e) => setTotal(e.target.value)} className="w-20 h-8 rounded-[var(--radius-app)] border border-border bg-card px-2 text-sm" /></label>
          <label className="flex flex-col gap-1 text-xs">Wickets<input value={wkts} onChange={(e) => setWkts(e.target.value)} className="w-20 h-8 rounded-[var(--radius-app)] border border-border bg-card px-2 text-sm" /></label>
          <label className="flex flex-col gap-1 text-xs">Reason / evidence<input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. RMCC scorebook p.4" className="w-56 h-8 rounded-[var(--radius-app)] border border-border bg-card px-2 text-sm" /></label>
          <Button size="sm" onClick={() => { const t = /^\d+$/.test(total.trim()) ? Number(total) : null; const wv = /^\d+$/.test(wkts.trim()) ? Number(wkts) : null; onOfficial(t, wv, reason || "Entered from scoresheet"); setOpen(false); }}>
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
    <SectionCard icon={Trophy} title="Match Result and Notes"
      description="Result, winner and margin (tie and draw are distinct); notes and match status.">
      <div className="mb-3 flex flex-wrap items-center gap-2 rounded-[var(--radius-app)] border border-border bg-muted/30 p-3">
        <Trophy className="h-5 w-5 shrink-0 text-brand" aria-hidden />
        <span className="text-base font-semibold">{formatResult(match, teamName)}</span>
        {match.result_source && match.result_source !== "unknown" && (
          <Badge variant={match.result_source === "manual" ? "muted" : match.result_source === "recorded" ? "outline" : "success"}>
            {match.result_source === "calculated" ? "Auto-calculated" : titleCase(match.result_source)}
          </Badge>
        )}
      </div>
      {(match.result_warnings?.length ?? 0) > 0 && (
        <div className="mb-3 rounded-[var(--radius-app)] border border-warning/40 bg-warning/5 p-2 text-xs text-warning">
          {match.result_warnings!.map((w, i) => <div key={i}>⚠ {w}</div>)}
        </div>
      )}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Field label="Result">
          <Select value={resultType} disabled={!canManage} onChange={(e) => setResultType(e.target.value)}>
            {RESULT_TYPES.map((r) => <option key={r} value={r}>{sentenceCase(r.replace(/_/g, " "))}</option>)}
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
          result_source: "manual",  // a manual edit overrides and is preserved from auto-calculation
        })}>Save result (manual override)</Button>
      )}
      <div className="mt-4">
        <Field label="Notes" hint="Autosaved locally as you type; committed to the record on blur.">
          <Textarea defaultValue={match.notes ?? ""} disabled={!canManage}
            onChange={(e) => persistDraftNote(workspaceId, match.id, { notes: e.target.value })}
            onBlur={(e) => { if ((e.target.value || null) !== match.notes) onPatch({ notes: e.target.value || null }); }} />
        </Field>
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <span className="text-xs font-medium text-muted-foreground">Match status</span>
        <div className="inline-flex overflow-hidden rounded-[var(--radius-app)] border border-border" role="group" aria-label="Match status">
          {MATCH_STATUSES.map((s) => {
            const activeState = match.status === s;
            const tone = s === "final" ? "bg-success/15 text-success" : s === "abandoned" ? "bg-warning/15 text-warning" : "bg-brand/10 text-brand";
            return (
              <button key={s} disabled={!canManage} onClick={() => onPatch({ status: s })}
                aria-pressed={activeState}
                title={s === "draft" ? "Editable; excluded from statistics until finalised" : s === "final" ? "Finalised; included in statistics" : "Abandoned"}
                className={`border-r border-border px-3 py-1 text-xs capitalize last:border-r-0 ${activeState ? `font-semibold ${tone}` : "text-muted-foreground hover:bg-muted"}`}>
                {s}
              </button>
            );
          })}
        </div>
        <span className="text-xs text-muted-foreground">Draft keeps it editable and out of statistics until finalised.</span>
      </div>
      <DraftNote matchId={match.id} />
    </SectionCard>
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

// expose draft serializer usage so the helper is referenced (notes autosave hook point)
export function persistDraftNote(workspaceId: string, matchId: string, state: Record<string, unknown>) {
  try {
    localStorage.setItem(draftKey(workspaceId, matchId), serializeDraft(state));
  } catch {
    /* storage unavailable — editing still works against the backend */
  }
}
