/**
 * Records & Achievements (Phase 13) — all-time record holders (prominent No.1 + expanded ranking),
 * seasonal leaders, upcoming milestones and Life Members, plus one-click Club Record Book PDF. Reads
 * from the Records Engine (approved data only); ties and known-minimum flags are shown, nothing invented.
 */
import { Award, BookOpen, RefreshCw, Users } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AppShell } from "../../components/layout/AppShell";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import { Select } from "../../components/ui/select";
import { api, ApiError, type Organisation, type RecordCategory } from "../../lib/api";
import { openBlobUrl } from "../../lib/utils";
import { useWorkspace } from "../../lib/workspace-context";

type Seasonal = Awaited<ReturnType<typeof api.recordsSeasonal>>;
type Upcoming = Awaited<ReturnType<typeof api.recordsUpcoming>>;
type ByWicket = Awaited<ReturnType<typeof api.recordsPartnershipsByWicket>>;
const WICKET_LABELS = ["1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "8th", "9th", "10th"];
const CLUB_LENS_KEY = "onestats.records.clubLens";
// Record tiles are grouped by genre, in this order; within a genre, by this key order (others fall last).
const GENRE_ORDER = ["Batting", "Partnerships", "Bowling", "Fielding & Wicketkeeping", "Captaincy & Appearances", "Other"];
const RECORD_ORDER = [
  "most_runs", "highest_score", "most_centuries", "most_fifties",
  "highest_partnership", "partnership_aggregate_career", "partnership_aggregate_season",
  "most_wickets", "best_bowling_innings", "best_match_bowling", "most_five_fors",
  "most_catches", "most_stumpings", "most_run_outs",
  "most_matches", "most_captained", "most_captain_wins",
];
const orderOf = (key: string) => { const i = RECORD_ORDER.indexOf(key); return i < 0 ? 999 : i; };

export function Records() {
  const { current } = useWorkspace();
  const [all, setAll] = useState<Record<string, RecordCategory> | null>(null);
  const [seasonal, setSeasonal] = useState<Seasonal>([]);
  const [upcoming, setUpcoming] = useState<Upcoming>([]);
  const [byWicket, setByWicket] = useState<ByWicket>([]);
  const [honours, setHonours] = useState<Record<string, unknown>[]>([]);
  const [clubs, setClubs] = useState<Organisation[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [clubMode, setClubMode] = useState<"primary" | "global">("primary");
  // the "club lens" — restrict every record to one club's performances. "" = all clubs. Remembered.
  const [orgId, setOrgId] = useState<string>(() => {
    try { return localStorage.getItem(CLUB_LENS_KEY) ?? ""; } catch { return ""; }
  });

  // load the workspace's clubs once, to populate the lens dropdown
  useEffect(() => {
    if (!current) return;
    void api.listOrganisations(current.id, { kind: "club" })
      .then((rows) => setClubs(rows.filter((o) => !o.merged_into_id)
        .sort((a, b) => a.name.localeCompare(b.name))))
      .catch(() => setClubs([]));
  }, [current]);

  const load = useCallback(async () => {
    if (!current) return;
    setBusy(true);
    setError(null);
    const org = orgId || undefined;
    try {
      const [a, s, u, w, h] = await Promise.all([
        api.recordsAllTime(current.id, { club_mode: clubMode, organisation_id: org }),
        api.recordsSeasonal(current.id), api.recordsUpcoming(current.id, undefined, org),
        api.recordsPartnershipsByWicket(current.id, org), api.recordsHonours(current.id),
      ]);
      setAll(a);
      setSeasonal(s);
      setUpcoming(u);
      setByWicket(w);
      setHonours(h);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load records.");
    } finally {
      setBusy(false);
    }
  }, [current, clubMode, orgId]);
  useEffect(() => {
    void load();
  }, [load]);

  const selectClubLens = (value: string) => {
    setOrgId(value);
    try { localStorage.setItem(CLUB_LENS_KEY, value); } catch { /* ignore */ }
  };

  if (!current) {
    return (
      <AppShell title="Records & Achievements" subtitle="Select or create a workspace">
        <Card><CardContent><p className="text-sm text-muted-foreground">No workspace selected.</p></CardContent></Card>
      </AppShell>
    );
  }

  const exportBook = async () => {
    try {
      openBlobUrl(await api.recordBookPdfUrl(current.id), "Club Record Book.pdf");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Record book export failed.");
    }
  };

  const categories = all ? Object.entries(all).filter(([, c]) => c.holder) : [];
  // Group the record tiles by genre, in GENRE_ORDER, and order within each genre by RECORD_ORDER.
  const genreGroups = GENRE_ORDER
    .map((genre) => ({
      genre,
      items: categories
        .filter(([, c]) => (c.genre ?? "Other") === genre)
        .sort(([ka], [kb]) => orderOf(ka) - orderOf(kb)),
    }))
    .filter((g) => g.items.length > 0);

  return (
    <AppShell title="Records & Achievements" subtitle={current.name}>
      <div className="mx-auto flex max-w-5xl flex-col gap-4">
        {error && <p className="rounded-[var(--radius-app)] border border-danger/40 bg-danger/5 px-3 py-2 text-sm text-danger">{error}</p>}

        <div className="flex items-center gap-2">
          <Button size="sm" variant="outline" disabled={busy} onClick={() => void load()}>
            <RefreshCw className="h-4 w-4" aria-hidden /> Refresh
          </Button>
          <Button size="sm" className="ml-auto" onClick={() => void exportBook()}>
            <BookOpen className="h-4 w-4" aria-hidden /> Club Record Book (PDF)
          </Button>
        </div>

        <Card><CardContent className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-sm font-semibold">All-time record holders</h3>
            <div className="flex flex-wrap items-center gap-3">
              <label className="flex items-center gap-1 text-xs text-muted-foreground">
                Club:
                <Select value={orgId} disabled={busy} className="h-7 w-44"
                  onChange={(e) => selectClubLens(e.target.value)}>
                  <option value="">All clubs</option>
                  {clubs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
                </Select>
              </label>
              {orgId === "" && (
                <label className="flex items-center gap-1 text-xs text-muted-foreground">
                  Club shown:
                  <Select value={clubMode} disabled={busy} className="h-7 w-32"
                    onChange={(e) => setClubMode(e.target.value as "primary" | "global")}>
                    <option value="primary">Primary club</option>
                    <option value="global">All clubs</option>
                  </Select>
                </label>
              )}
            </div>
          </div>
          {orgId !== "" && (
            <p className="text-xs text-muted-foreground">
              Showing records for <span className="font-medium text-foreground">{clubs.find((o) => o.id === orgId)?.name ?? "selected club"}</span> only.
            </p>
          )}
          {categories.length === 0 && <p className="text-xs text-muted-foreground">No approved records yet.</p>}
          {genreGroups.map((group) => (
            <div key={group.genre} className="flex flex-col gap-2">
              <h4 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{group.genre}</h4>
              <div className="grid gap-2 sm:grid-cols-2">
                {group.items.map(([key, c]) => (
                  <button key={key} type="button" onClick={() => setExpanded(expanded === key ? null : key)}
                    className="flex flex-col gap-1 rounded-[var(--radius-app)] border border-border p-3 text-left hover:border-brand">
                    <div className="flex items-center gap-2">
                      <Award className="h-4 w-4 text-brand" aria-hidden />
                      <span className="text-xs text-muted-foreground">{c.title}</span>
                    </div>
                    <div className="flex items-baseline gap-2">
                      <span className="text-lg font-semibold">{c.holder?.player}</span>
                      <span className="text-xl font-bold tabular-nums text-brand">{c.value}</span>
                      {c.holder?.tied && <Badge variant="muted">tied</Badge>}
                      {c.holder?.known_minimum && (
                        <Badge variant="warning"
                          title="At least this many — this record total includes innings with unknown figures, so it's a floor, never overstated. Completing those innings can only raise it.">
                          known min.
                        </Badge>
                      )}
                    </div>
                    {c.holder?.club && <span className="text-xs text-muted-foreground">{c.holder.club}</span>}
                    {expanded === key && (
                      <div className="mt-1 flex flex-col gap-0.5 border-t border-border pt-1 text-xs">
                        {c.ranking.map((r) => (
                          <div key={r.rank} className="flex justify-between gap-2">
                            <span>{r.rank}. {r.player}{r.club ? <span className="text-muted-foreground"> · {r.club}</span> : null}</span>
                            <span className="tabular-nums">{r.value}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </CardContent></Card>

        <Card><CardContent className="flex flex-col gap-2">
          <div className="flex items-center gap-2">
            <Users className="h-4 w-4 text-brand" aria-hidden />
            <h3 className="text-sm font-semibold">Highest partnership for each wicket</h3>
          </div>
          {byWicket.length === 0 && <p className="text-xs text-muted-foreground">No recorded partnerships yet.</p>}
          <div className="grid gap-x-4 gap-y-1 sm:grid-cols-2">
            {byWicket.map((p) => (
              <div key={p.wicket} className="flex items-baseline gap-2 border-b border-border/40 py-1 text-sm last:border-0">
                <span className="w-8 shrink-0 text-xs font-semibold text-muted-foreground">{WICKET_LABELS[p.wicket - 1] ?? `${p.wicket}th`}</span>
                <span className="font-bold tabular-nums text-brand">{p.runs}{p.unbroken ? "*" : ""}</span>
                <span className="truncate">{p.player1_name} &amp; {p.player2_name}</span>
              </div>
            ))}
          </div>
        </CardContent></Card>

        <div className="grid gap-4 md:grid-cols-2">
          <Card><CardContent className="flex flex-col gap-2">
            <h3 className="text-sm font-semibold">Seasonal leaders</h3>
            {seasonal.length === 0 && <p className="text-xs text-muted-foreground">No seasons with approved data.</p>}
            {seasonal.map((s) => (
              <div key={s.season_id} className="flex flex-col gap-0.5 border-t border-border pt-1 text-sm first:border-0">
                <span className="font-medium">{s.label}</span>
                <span className="text-xs text-muted-foreground">
                  Runs: {s.leading_run_scorer ? `${s.leading_run_scorer.player} (${s.leading_run_scorer.value})` : "—"}
                  {" · "}Wkts: {s.leading_wicket_taker ? `${s.leading_wicket_taker.player} (${s.leading_wicket_taker.value})` : "—"}
                </span>
              </div>
            ))}
          </CardContent></Card>

          <Card><CardContent className="flex flex-col gap-2">
            <h3 className="text-sm font-semibold">Upcoming milestones</h3>
            {upcoming.length === 0 && <p className="text-xs text-muted-foreground">None approaching (from confirmed totals).</p>}
            {upcoming.slice(0, 12).map((u, i) => (
              <div key={i} className="flex items-center gap-2 text-sm">
                <Badge variant="brand">{u.to_go}</Badge>
                <Link to={`/people/${u.person_id}`} className="font-medium hover:text-brand hover:underline">{u.player}</Link>
                <span className="text-muted-foreground">— {u.to_go} from {u.threshold} {u.metric} (on {u.current})</span>
              </div>
            ))}
          </CardContent></Card>
        </div>

        <Card><CardContent className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold">Life Members & honorary recognition</h3>
          {honours.length === 0 && <p className="text-xs text-muted-foreground">None recorded.</p>}
          {honours.map((h, i) => (
            <div key={i} className="flex flex-wrap items-center gap-2 text-sm">
              <Badge variant="muted">{String(h.honour_type).replace(/_/g, " ")}</Badge>
              <span className="font-medium">{String(h.title)}</span>
              {h.awarded_season ? <span className="text-xs text-muted-foreground">{String(h.awarded_season)}</span> : null}
            </div>
          ))}
          <p className="text-xs text-muted-foreground">
            Honours are explicitly recorded and authorised — never inferred from statistics.
          </p>
        </CardContent></Card>
      </div>
    </AppShell>
  );
}
