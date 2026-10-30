/**
 * Matches & scorecard entry (Phase 6, Stage 7). A single screen: search/select existing matches,
 * create a new one, and open the integrated scorecard editor in place — no hopping between screens.
 * Incomplete matches save as drafts. Connected to the real Phase 6 backend; management actions are
 * gated by match.manage (the backend is the authority; this only decides what to show).
 */

import { ChevronDown, ChevronRight, Plus, Trophy } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { AppShell } from "../../components/layout/AppShell";
import { EmptyState, ErrorState, LoadingState } from "../../components/states/States";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import { Modal } from "../../components/ui/dialog";
import { Input } from "../../components/ui/input";
import { Select } from "../../components/ui/select";
import {
  api, ApiError, type Competition, type CompetitionDetail, type Match, type Team, type Venue,
} from "../../lib/api";
// (Team is used by the create modal and the list's team-name lookup.)
import { formatDate, useDateStyle } from "../../lib/dates";
import { Field, NoWorkspace, useManage } from "../manage/_shared";
import { ScorecardEditor } from "./ScorecardEditor";

// The cricket season a match belongs to, derived from its date. Australian seasons span two calendar
// years and roll over mid-winter, so e.g. Oct 2025 and Mar 2026 are both "2025/26". Undated matches group
// under "Unknown date".
function seasonOf(dateStr: string | null): string {
  if (!dateStr) return "Unknown date";
  const t = Date.parse(dateStr);
  if (Number.isNaN(t)) return "Unknown date";
  const d = new Date(dateStr);
  const y = d.getUTCFullYear();
  const start = d.getUTCMonth() + 1 >= 7 ? y : y - 1;   // July rollover
  return `${start}/${String(start + 1).slice(-2)}`;
}

export function Scorecard() {
  const { workspaceId, canManage } = useManage();
  const [matches, setMatches] = useState<Match[]>([]);
  const [comps, setComps] = useState<Competition[]>([]);
  const [teams, setTeams] = useState<Team[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [compFilter, setCompFilter] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [openMatch, setOpenMatch] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const dateStyle = useDateStyle();   // re-render the list when the date-format preference changes
  // Return-to-last-match: remember the match just closed, then scroll to & highlight it in the list.
  const [returnToId, setReturnToId] = useState<string | null>(null);
  // Collapsible season groups (collapsed labels); all expanded by default.
  const [collapsedSeasons, setCollapsedSeasons] = useState<Set<string>>(new Set());
  // Deep-link: ?open=<matchId> opens that match's editor directly (e.g. from a Research Centre gap).
  const [searchParams, setSearchParams] = useSearchParams();

  const load = useCallback(async () => {
    if (!workspaceId) return;
    setLoading(true);
    setError(null);
    try {
      const [m, c, t] = await Promise.all([
        api.listMatches(workspaceId, { competition_id: compFilter || undefined }),
        api.listCompetitions(workspaceId),
        api.listTeams(workspaceId),
      ]);
      setMatches(m);
      setComps(c);
      setTeams(t);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load matches");
    } finally {
      setLoading(false);
    }
  }, [workspaceId, compFilter]);

  useEffect(() => {
    void load();
  }, [load]);

  // Honour a ?open=<matchId> deep-link once, then strip the param so Back returns to the list.
  useEffect(() => {
    const open = searchParams.get("open");
    if (!open) return;
    setOpenMatch(open);
    const next = new URLSearchParams(searchParams);
    next.delete("open");
    setSearchParams(next, { replace: true });
  }, [searchParams, setSearchParams]);

  // After returning from a match, scroll it into view and briefly highlight it, so the user lands back
  // where they were in the list instead of at the top.
  useEffect(() => {
    if (openMatch || loading || !returnToId) return;
    const el = document.getElementById(`match-row-${returnToId}`);
    if (!el) { setReturnToId(null); return; }
    el.scrollIntoView({ block: "center" });
    const t = setTimeout(() => setReturnToId(null), 1800);
    return () => clearTimeout(t);
  }, [openMatch, loading, returnToId]);

  if (!workspaceId) {
    return (
      <AppShell title="Matches" subtitle="Match management and scorecard entry">
        <NoWorkspace />
      </AppShell>
    );
  }

  if (openMatch) {
    return (
      <AppShell title="Scorecard" subtitle="Integrated match & scorecard editor">
        <ScorecardEditor
          workspaceId={workspaceId}
          matchId={openMatch}
          canManage={canManage}
          onBack={() => { setReturnToId(openMatch); setOpenMatch(null); void load(); }}
          onSaved={() => void load()}
        />
      </AppShell>
    );
  }

  const compName = (id: string | null) => (id ? comps.find((c) => c.id === id)?.name ?? "—" : "No competition");
  const teamName = (id: string | null | undefined) => (id ? teams.find((t) => t.id === id)?.name ?? "—" : null);
  const matchTitle = (m: Match) => {
    const h = teamName(m.home_team_id);
    const a = teamName(m.away_team_id);
    if (h || a) return `${h ?? "TBC"} v ${a ?? "TBC"}`;
    return "Teams not set";
  };
  const filtered = matches.filter((m) => {
    const hay = `${matchTitle(m)} ${m.round ?? ""} ${m.match_date ?? ""} ${compName(m.competition_id)}`.toLowerCase();
    return hay.includes(search.toLowerCase());
  });

  const toggleSel = (id: string) => setSelected((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const allFilteredSelected = filtered.length > 0 && filtered.every((m) => selected.has(m.id));
  const toggleAllFiltered = () => setSelected((s) => {
    if (allFilteredSelected) { const n = new Set(s); filtered.forEach((m) => n.delete(m.id)); return n; }
    return new Set([...s, ...filtered.map((m) => m.id)]);
  });
  // Run a bulk action in small chunks so a large selection (e.g. all 940) never sends one giant
  // request that ties up the single-process backend and times out. Progress is shown as it goes.
  const BULK_CHUNK = 40;
  const runBulk = async (
    apiCall: (chunkIds: string[]) => Promise<{ updated: number; skipped: { reason: string }[] }>,
    label: string,
  ) => {
    setBulkBusy(true); setError(null); setMsg(null);
    const all = [...selected];
    let updated = 0, skipped = 0;
    try {
      for (let i = 0; i < all.length; i += BULK_CHUNK) {
        const r = await apiCall(all.slice(i, i + BULK_CHUNK));
        updated += r.updated; skipped += r.skipped.length;
        if (all.length > BULK_CHUNK) setMsg(`${label}: ${Math.min(i + BULK_CHUNK, all.length)} of ${all.length}…`);
      }
      setMsg(`${label}: ${updated} match${updated === 1 ? "" : "es"}${skipped ? `, ${skipped} skipped` : ""}.`);
      setSelected(new Set());
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Bulk action failed.");
    } finally { setBulkBusy(false); }
  };

  // Group the (already date-ordered) matches into seasons, most recent first, preserving order within.
  const seasonGroups: { season: string; matches: Match[] }[] = [];
  const seasonIdx = new Map<string, number>();
  for (const m of filtered) {
    const s = seasonOf(m.match_date);
    let i = seasonIdx.get(s);
    if (i === undefined) { i = seasonGroups.length; seasonIdx.set(s, i); seasonGroups.push({ season: s, matches: [] }); }
    seasonGroups[i].matches.push(m);
  }
  const toggleSeason = (s: string) =>
    setCollapsedSeasons((c) => { const n = new Set(c); n.has(s) ? n.delete(s) : n.add(s); return n; });

  const matchCard = (m: Match) => (
    <Card key={m.id} id={`match-row-${m.id}`}
      className={`hover:border-brand ${selected.has(m.id) || returnToId === m.id ? "border-brand ring-2 ring-brand" : ""}`}>
      <CardContent className="flex items-center gap-3 py-4">
        {canManage && (
          <input type="checkbox" aria-label={`Select ${matchTitle(m)}`} checked={selected.has(m.id)}
            onChange={() => toggleSel(m.id)} onClick={(e) => e.stopPropagation()} className="h-4 w-4" />
        )}
        <div className="flex flex-1 cursor-pointer items-center gap-3" onClick={() => setOpenMatch(m.id)}>
          <Trophy className="h-5 w-5 text-muted-foreground" aria-hidden />
          <div className="min-w-0 flex-1">
            <div className="truncate font-medium">{matchTitle(m)}</div>
            <div className="truncate text-xs text-muted-foreground">
              {compName(m.competition_id)}
              {m.round ? ` · ${m.round}` : ""}
              {m.match_date ? ` · ${formatDate(m.match_date, dateStyle)}` : " · date unknown"}
              {m.format ? ` · ${m.format}` : ""}
            </div>
          </div>
          {m.classification !== "unclassified" && <Badge variant="brand">{m.classification.replace(/_/g, " ")}</Badge>}
          <Badge variant={m.status === "final" ? "success" : m.status === "abandoned" ? "warning" : "muted"}>{m.status}</Badge>
        </div>
      </CardContent>
    </Card>
  );

  return (
    <AppShell title="Matches" subtitle="Match management and scorecard entry">
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Input placeholder="Search matches…" value={search} onChange={(e) => setSearch(e.target.value)} className="max-w-xs" />
        <Select value={compFilter} onChange={(e) => setCompFilter(e.target.value)} className="max-w-xs">
          <option value="">All competitions</option>
          {comps.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </Select>
        <div className="flex-1" />
        {canManage && (
          <Button onClick={() => setShowCreate(true)}>
            <Plus className="h-4 w-4" aria-hidden /> New match
          </Button>
        )}
      </div>

      {canManage && filtered.length > 0 && (
        <div className="mb-3 flex flex-wrap items-center gap-2 rounded-[var(--radius-app)] border border-border bg-muted/30 px-3 py-2 text-sm">
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={allFilteredSelected} onChange={toggleAllFiltered} className="h-4 w-4" />
            <span className="text-muted-foreground">{selected.size > 0 ? `${selected.size} selected` : "Select all"}</span>
          </label>
          <div className="flex-1" />
          {selected.size > 0 && (
            <>
              <Button size="sm" variant="outline" disabled={bulkBusy}
                onClick={() => void runBulk((chunk) => api.bulkStatusMatches(workspaceId, { match_ids: chunk, status: "final" }), "Marked Final")}>
                Mark Final
              </Button>
              <Select aria-label="Set match type for selected" value="" disabled={bulkBusy} className="w-36"
                onChange={(e) => { const v = e.target.value; if (v) void runBulk((chunk) => api.bulkClassifyMatches(workspaceId, { match_ids: chunk, classification: v, finals_stage: v === "grand_final" ? "grand_final" : undefined }), "Type set"); }}>
                <option value="">Set type…</option>
                <option value="home_away">Home &amp; Away</option>
                <option value="final">Final</option>
                <option value="grand_final">Grand Final</option>
                <option value="unclassified">Unclassified</option>
              </Select>
              <Button size="sm" variant="outline" disabled={bulkBusy}
                onClick={() => void runBulk((chunk) => api.bulkClassifyMatches(workspaceId, { match_ids: chunk, verify_existing: true }), "Types verified")}>
                Verify types
              </Button>
              <Button size="sm" variant="outline" disabled={bulkBusy}
                onClick={() => void runBulk((chunk) => api.bulkApproveMatches(workspaceId, { match_ids: chunk, status: "approved" }), "Approved")}>
                Approve
              </Button>
              <Button size="sm" variant="ghost" disabled={bulkBusy} onClick={() => setSelected(new Set())}>Clear</Button>
            </>
          )}
        </div>
      )}
      {msg && <div className="mb-3 rounded-[var(--radius-app)] border border-success/40 bg-success/5 px-4 py-2 text-sm text-success">{msg}</div>}

      {loading && <LoadingState label="Loading matches…" />}
      {!loading && error && <ErrorState message={error} onRetry={() => void load()} />}
      {!loading && !error && filtered.length === 0 && (
        <EmptyState icon={<Trophy className="h-8 w-8" aria-hidden />} title="No matches"
          description="Create a match to start a scorecard. Incomplete matches save as drafts." />
      )}
      {!loading && !error && filtered.length > 0 && (
        <div className="grid gap-4">
          {seasonGroups.map((g) => {
            const isCollapsed = collapsedSeasons.has(g.season);
            return (
              <div key={g.season} className="grid gap-2">
                <button type="button" onClick={() => toggleSeason(g.season)}
                  className="flex items-center gap-2 px-1 text-left text-sm font-semibold hover:text-brand">
                  {isCollapsed ? <ChevronRight className="h-4 w-4" aria-hidden /> : <ChevronDown className="h-4 w-4" aria-hidden />}
                  <span>{g.season}</span>
                  <span className="font-normal text-muted-foreground">
                    · {g.matches.length} match{g.matches.length === 1 ? "" : "es"}
                  </span>
                </button>
                {!isCollapsed && g.matches.map(matchCard)}
              </div>
            );
          })}
        </div>
      )}

      {showCreate && (
        <CreateMatchModal
          workspaceId={workspaceId}
          comps={comps}
          onClose={() => setShowCreate(false)}
          onCreated={(id) => { setShowCreate(false); setOpenMatch(id); }}
        />
      )}
    </AppShell>
  );
}

function CreateMatchModal({ workspaceId, comps, onClose, onCreated }: {
  workspaceId: string; comps: Competition[]; onClose: () => void; onCreated: (matchId: string) => void;
}) {
  const [competitionId, setCompetitionId] = useState("");
  const [detail, setDetail] = useState<CompetitionDetail | null>(null);
  const [gradeId, setGradeId] = useState("");
  const [seasonId, setSeasonId] = useState("");
  const [teams, setTeams] = useState<Team[]>([]);
  const [venues, setVenues] = useState<Venue[]>([]);
  const [homeId, setHomeId] = useState("");
  const [awayId, setAwayId] = useState("");
  const [venueId, setVenueId] = useState("");
  const [matchDate, setMatchDate] = useState("");
  const [format, setFormat] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      const [t, v] = await Promise.all([api.listTeams(workspaceId), api.listVenues(workspaceId)]);
      setTeams(t);
      setVenues(v);
    })();
  }, [workspaceId]);

  useEffect(() => {
    void (async () => {
      setGradeId("");
      setSeasonId("");
      if (competitionId) setDetail(await api.getCompetition(workspaceId, competitionId));
      else setDetail(null);
    })();
  }, [workspaceId, competitionId]);

  const submit = async () => {
    setBusy(true);
    setErr(null);
    try {
      const created = await api.createMatch(workspaceId, {
        competition_id: competitionId || null, grade_id: gradeId || null, season_id: seasonId || null,
        venue_id: venueId || null, match_date: matchDate || null, format: format || null, status: "draft",
      });
      // teams are optional at creation; set whichever were chosen
      if (homeId) await api.setMatchTeam(workspaceId, created.id, { team_id: homeId, is_home: true });
      if (awayId && awayId !== homeId) await api.setMatchTeam(workspaceId, created.id, { team_id: awayId, is_home: false });
      onCreated(created.id);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Could not create match");
      setBusy(false);
    }
  };

  return (
    <Modal open title="New match" onClose={onClose} footer={
      <>
        <Button variant="outline" size="sm" onClick={onClose} disabled={busy}>Cancel</Button>
        <Button size="sm" onClick={() => void submit()} disabled={busy}>{busy ? "Creating…" : "Create & open"}</Button>
      </>
    }>
      <div className="flex flex-col gap-3">
        {err && <ErrorState message={err} />}
        <Field label="Competition" hint="Optional — a match can be recorded without one.">
          <Select value={competitionId} onChange={(e) => setCompetitionId(e.target.value)}>
            <option value="">— none —</option>
            {comps.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </Select>
        </Field>
        {detail && (
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Grade">
              <Select value={gradeId} onChange={(e) => setGradeId(e.target.value)}>
                <option value="">— none —</option>
                {detail.grades.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
              </Select>
            </Field>
            <Field label="Season">
              <Select value={seasonId} onChange={(e) => setSeasonId(e.target.value)}>
                <option value="">— none —</option>
                {detail.seasons.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
              </Select>
            </Field>
          </div>
        )}
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Home team"><Select value={homeId} onChange={(e) => setHomeId(e.target.value)}>
            <option value="">— set later —</option>
            {teams.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </Select></Field>
          <Field label="Away team"><Select value={awayId} onChange={(e) => setAwayId(e.target.value)}>
            <option value="">— set later —</option>
            {teams.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </Select></Field>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Venue"><Select value={venueId} onChange={(e) => setVenueId(e.target.value)}>
            <option value="">— unknown —</option>
            {venues.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
          </Select></Field>
          <Field label="Date" hint="Leave blank if unknown."><Input type="date" value={matchDate} onChange={(e) => setMatchDate(e.target.value)} /></Field>
        </div>
        <Field label="Format"><Input value={format} placeholder="e.g. two-day, limited overs" onChange={(e) => setFormat(e.target.value)} /></Field>
      </div>
    </Modal>
  );
}
