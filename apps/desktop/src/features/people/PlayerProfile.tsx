/**
 * Player Profile (Phase 13) — a professional career profile: header, adaptive career-summary cards,
 * and tabbed sections (Overview, Batting, Bowling, Fielding & WK, Captaincy, Seasons, Matches,
 * Records & Milestones, Awards & Honours, Media). All figures come from the one statistics/records
 * engine via /full-profile; nothing is fabricated, unknown is never shown as zero. Export to PDF.
 *
 * Design: premium statistics platform meets historical archive — restrained cards, clear hierarchy,
 * right-aligned numerics, elegant badges, light/dark, workspace branding.
 */
import { Award, Download, Medal, ScrollText, Shield, Trophy, User } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { AppShell } from "../../components/layout/AppShell";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import { api, ApiError, type PlayerFullProfile } from "../../lib/api";
import { useWorkspace } from "../../lib/workspace-context";

type Tab = "overview" | "batting" | "bowling" | "fielding" | "captaincy" | "seasons" | "matches" | "records" | "awards" | "media";

const TABS: { key: Tab; label: string }[] = [
  { key: "overview", label: "Overview" }, { key: "batting", label: "Batting" }, { key: "bowling", label: "Bowling" },
  { key: "fielding", label: "Fielding & WK" }, { key: "captaincy", label: "Captaincy" }, { key: "seasons", label: "Seasons" },
  { key: "matches", label: "Matches" }, { key: "records", label: "Records & Milestones" },
  { key: "awards", label: "Awards & Honours" }, { key: "media", label: "Media" },
];

function num(v: unknown, dp?: number): string {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "number") return dp != null ? v.toFixed(dp) : String(v);
  return String(v);
}

export function PlayerProfile() {
  const { personId } = useParams();
  const { current } = useWorkspace();
  const navigate = useNavigate();
  const [full, setFull] = useState<PlayerFullProfile | null>(null);
  const [name, setName] = useState<string>("Player");
  const [photos, setPhotos] = useState<{ id: string; caption: string | null }[]>([]);
  const [photoUrls, setPhotoUrls] = useState<Record<string, string>>({});
  const [matches, setMatches] = useState<Record<string, unknown>[] | null>(null);
  const [tab, setTab] = useState<Tab>("overview");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!current || !personId) return;
    try {
      const [f, prof] = await Promise.all([
        api.profileFull(current.id, personId),
        api.getProfile(current.id, personId).catch(() => null),
      ]);
      setFull(f);
      const person = (prof as { person?: { display_name?: string } })?.person;
      if (person?.display_name) setName(person.display_name);
      const ph = (prof as { photos?: { id: string; caption: string | null }[] })?.photos ?? [];
      setPhotos(ph);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load the player profile.");
    }
  }, [current, personId]);
  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    if (!current || tab !== "matches" || matches) return;
    api.profileMatches(current.id, personId!).then(setMatches).catch(() => setMatches([]));
  }, [tab, current, personId, matches]);

  useEffect(() => {
    if (!current || tab !== "media" || photos.length === 0) return;
    let revoked = false;
    photos.forEach((p) => {
      if (photoUrls[p.id]) return;
      api.personPhotoUrl(current.id, p.id).then((u) => { if (!revoked) setPhotoUrls((m) => ({ ...m, [p.id]: u })); }).catch(() => {});
    });
    return () => { revoked = true; };
  }, [tab, current, photos, photoUrls]);

  const initials = useMemo(() => name.split(/\s+/).map((w) => w[0]).slice(0, 2).join("").toUpperCase(), [name]);

  if (!current) return <AppShell title="Player Profile" subtitle="Select a workspace"><div /></AppShell>;

  const c = full?.career;
  const bat = c?.batting ?? {};
  const bowl = c?.bowling ?? {};
  const field = c?.fielding ?? {};
  const capt = c?.captaincy ?? {};

  const honourBadges = (full?.honours ?? []).filter((h) => ["life_member", "honorary_member"].includes(String(h.honour_type)));

  const exportPdf = async () => {
    try {
      window.open(await api.profilePdfUrl(current.id, personId!), "_blank");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "PDF export failed.");
    }
  };

  const statCard = (label: string, value: unknown, dp?: number, flag?: boolean) => (
    <div className="rounded-[var(--radius-app)] border border-border p-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="flex items-baseline gap-1">
        <span className="text-2xl font-semibold tabular-nums">{num(value, dp)}</span>
        {flag && <Badge variant="warning">min.</Badge>}
      </div>
    </div>
  );

  const table = (cols: { key: string; label: string; align?: string; dp?: number }[], rows: Record<string, unknown>[],
                 onRow?: (r: Record<string, unknown>) => void) => (
    <div className="max-h-[30rem] overflow-auto rounded-[var(--radius-app)] border border-border">
      <table className="w-full border-collapse text-sm">
        <thead className="sticky top-0 bg-brand text-white">
          <tr>{cols.map((col) => (
            <th key={col.key} className={`whitespace-nowrap px-2 py-1.5 font-semibold ${col.align === "right" ? "text-right" : "text-left"}`}>{col.label}</th>
          ))}</tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className={`${i % 2 ? "bg-muted/30" : ""} ${onRow ? "cursor-pointer hover:bg-brand/10" : ""}`}
              onClick={() => onRow?.(r)}>
              {cols.map((col) => (
                <td key={col.key} className={`whitespace-nowrap px-2 py-1 tabular-nums ${col.align === "right" ? "text-right" : "text-left"}`}>
                  {num(r[col.key], col.dp)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  return (
    <AppShell title="Player Profile" subtitle={current.name}>
      <div className="mx-auto flex max-w-5xl flex-col gap-4">
        {error && <p className="rounded-[var(--radius-app)] border border-danger/40 bg-danger/5 px-3 py-2 text-sm text-danger">{error}</p>}

        {/* header */}
        <Card><CardContent className="flex flex-wrap items-center gap-4">
          <div className="flex h-20 w-20 items-center justify-center rounded-full border border-border bg-brand/10 text-2xl font-semibold text-brand">
            {initials || <User className="h-8 w-8" aria-hidden />}
          </div>
          <div className="flex flex-col gap-1">
            <h2 className="text-2xl font-semibold">{name}</h2>
            <div className="flex flex-wrap items-center gap-2 text-xs">
              {c?.derived_role && <Badge variant="brand">{c.derived_role}</Badge>}
              {c?.has_captaincy && <Badge variant="muted"><Shield className="mr-1 h-3 w-3" aria-hidden />Captain</Badge>}
              {honourBadges.map((h, i) => (
                <Badge key={i} variant="success"><Medal className="mr-1 h-3 w-3" aria-hidden />{String(h.honour_type).replace(/_/g, " ")}</Badge>
              ))}
              {(full?.records ?? []).length > 0 && <Badge variant="warning"><Trophy className="mr-1 h-3 w-3" aria-hidden />Record holder</Badge>}
              {(full?.clubs ?? []).slice(0, 2).map((cl) => <span key={cl.team_id} className="text-muted-foreground">{cl.club}</span>)}
            </div>
          </div>
          <div className="ml-auto flex gap-2">
            <Button size="sm" variant="outline" onClick={() => navigate("/people")}>Directory</Button>
            <Button size="sm" onClick={() => void exportPdf()}><Download className="h-4 w-4" aria-hidden /> Export PDF</Button>
          </div>
        </CardContent></Card>

        {/* adaptive career summary */}
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {statCard("Matches", c?.matches)}
          {c?.has_batting && statCard("Runs", bat.runs, undefined, Boolean(bat.runs_known_minimum))}
          {c?.has_batting && statCard("Bat average", bat.average, 2)}
          {c?.has_batting && statCard("Highest", bat.highest_score)}
          {c?.has_bowling && statCard("Wickets", bowl.wickets, undefined, Boolean(bowl.wickets_known_minimum))}
          {c?.has_bowling && statCard("Bowl average", bowl.average, 2)}
          {Number(field.catches ?? 0) + Number(field.stumpings ?? 0) + Number(field.run_outs ?? 0) > 0 &&
            statCard("Ct / St / RO", `${field.catches ?? 0} / ${field.stumpings ?? 0} / ${field.run_outs ?? 0}`)}
          {c?.has_captaincy && statCard("Captained", capt.captained)}
        </div>

        {/* tabs */}
        <div className="flex flex-wrap items-center gap-2">
          {TABS.map((t) => (
            <button key={t.key} type="button" onClick={() => setTab(t.key)}
              className={`rounded-[var(--radius-app)] border px-3 py-1.5 text-sm ${tab === t.key ? "border-brand bg-brand/10 font-medium text-brand" : "border-border text-muted-foreground"}`}>
              {t.label}
            </button>
          ))}
        </div>

        <Card><CardContent className="flex flex-col gap-3">
          {tab === "overview" && (
            <>
              <h3 className="text-sm font-semibold">Career overview</h3>
              <p className="text-xs text-muted-foreground">
                {name} has played {c?.matches ?? 0} recorded match{(c?.matches ?? 0) === 1 ? "" : "es"}
                {c?.has_batting ? `, scoring ${num(bat.runs)} runs at ${num(bat.average, 2)}` : ""}
                {c?.has_bowling ? `, taking ${num(bowl.wickets)} wickets at ${num(bowl.average, 2)}` : ""}.
                {" "}Figures are from approved scorecards; unknown values are never counted as zero.
              </p>
              {(full?.records ?? []).length > 0 && (
                <div className="flex flex-col gap-1">
                  <h4 className="text-xs font-semibold">Records held</h4>
                  {full!.records.map((r, i) => (
                    <div key={i} className="flex items-center gap-2 text-sm">
                      <Trophy className="h-4 w-4 text-brand" aria-hidden />{r.title}
                      <span className="ml-auto font-semibold tabular-nums">{num(r.value)}</span>
                      {r.known_minimum && <Badge variant="warning">min.</Badge>}
                    </div>
                  ))}
                </div>
              )}
              <div className="flex flex-wrap gap-1.5">
                {full?.badges.calculated.slice(0, 12).map((b, i) => (
                  <Badge key={i} variant={b.state === "achieved_confirmed" ? "success" : "warning"}>
                    <Award className="mr-1 h-3 w-3" aria-hidden />{b.label}
                  </Badge>
                ))}
              </div>
            </>
          )}

          {tab === "batting" && c?.has_batting && (
            <>
              <h3 className="text-sm font-semibold">Batting</h3>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                {statCard("Innings", bat.innings)}{statCard("Not outs", bat.not_outs)}{statCard("Runs", bat.runs, undefined, Boolean(bat.runs_known_minimum))}
                {statCard("Highest", bat.highest_score)}{statCard("Average", bat.average, 2)}{statCard("Strike rate", bat.strike_rate, 2)}
                {statCard("50s", bat.fifties)}{statCard("100s", bat.hundreds)}{statCard("Ducks", bat.ducks)}
                {statCard("Fours", bat.fours)}{statCard("Sixes", bat.sixes)}
              </div>
            </>
          )}
          {tab === "batting" && !c?.has_batting && <p className="text-xs text-muted-foreground">No recorded batting.</p>}

          {tab === "bowling" && c?.has_bowling && (
            <>
              <h3 className="text-sm font-semibold">Bowling</h3>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                {statCard("Innings", bowl.innings)}{statCard("Overs", bowl.overs, 1)}{statCard("Maidens", bowl.maidens)}
                {statCard("Runs", bowl.runs)}{statCard("Wickets", bowl.wickets, undefined, Boolean(bowl.wickets_known_minimum))}
                {statCard("Average", bowl.average, 2)}{statCard("Economy", bowl.economy, 2)}{statCard("Strike rate", bowl.strike_rate, 2)}
                {statCard("5wi", bowl.five_wkt_innings)}{statCard("Best (match)", bowl.best_match_wickets)}
              </div>
            </>
          )}
          {tab === "bowling" && !c?.has_bowling && <p className="text-xs text-muted-foreground">No recorded bowling.</p>}

          {tab === "fielding" && (
            <>
              <h3 className="text-sm font-semibold">Fielding & Wicketkeeping</h3>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                {statCard("Catches", field.catches)}{statCard("Keeper catches", field.keeper_catches)}
                {statCard("Stumpings", field.stumpings)}{statCard("Run outs", field.run_outs)}
                {statCard("WK dismissals", field.keeper_dismissals)}
              </div>
            </>
          )}

          {tab === "captaincy" && c?.has_captaincy && (
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {statCard("Captained", capt.captained)}{statCard("Wins", capt.wins)}{statCard("Losses", capt.losses)}
              {statCard("Draws", capt.draws)}{statCard("Ties", capt.ties)}{statCard("GF captained", capt.gf_captained)}
              {statCard("GF wins", capt.gf_wins)}
            </div>
          )}
          {tab === "captaincy" && !c?.has_captaincy && <p className="text-xs text-muted-foreground">No captaincy history recorded.</p>}

          {tab === "seasons" && (
            <>
              <h3 className="text-sm font-semibold">Season by season</h3>
              {(full?.seasons.length ?? 0) === 0 ? <p className="text-xs text-muted-foreground">No seasons.</p> :
                table([{ key: "label", label: "Season" }, { key: "matches", label: "M", align: "right" },
                       { key: "runs", label: "Runs", align: "right" }, { key: "batting_average", label: "Bat Avg", align: "right", dp: 2 },
                       { key: "wickets", label: "Wkts", align: "right" }, { key: "bowling_average", label: "Bowl Avg", align: "right", dp: 2 },
                       { key: "catches", label: "Ct", align: "right" }, { key: "captained", label: "Capt", align: "right" }],
                      full!.seasons)}
            </>
          )}

          {tab === "matches" && (
            <>
              <h3 className="text-sm font-semibold">Match history</h3>
              {matches === null ? <p className="text-xs text-muted-foreground">Loading…</p> :
                matches.length === 0 ? <p className="text-xs text-muted-foreground">No matches.</p> :
                table([{ key: "match_date", label: "Date" }, { key: "classification", label: "Class" },
                       { key: "runs", label: "Runs", align: "right" }, { key: "wickets", label: "Wkts", align: "right" },
                       { key: "catches", label: "Ct", align: "right" }, { key: "result_type", label: "Result" }],
                      matches, () => navigate("/matches"))}
            </>
          )}

          {tab === "records" && (
            <>
              <h3 className="text-sm font-semibold">Records & Milestones</h3>
              <div className="flex flex-col gap-2">
                {Object.entries(full?.milestones.metrics ?? {}).map(([k, m]) => (
                  <div key={k} className="flex flex-wrap items-center gap-2 border-t border-border pt-2 text-sm first:border-0">
                    <span className="font-medium">{m.label}</span>
                    <span className="tabular-nums text-muted-foreground">{m.total}{m.known_minimum ? "+" : ""}</span>
                    {m.milestones.filter((x) => x.state.startsWith("achieved")).slice(-1).map((x, i) => (
                      <Badge key={i} variant="success">{x.threshold} reached</Badge>
                    ))}
                    {m.next && <span className="ml-auto text-xs text-muted-foreground">{m.next.to_go} to {m.next.threshold}</span>}
                  </div>
                ))}
              </div>
            </>
          )}

          {tab === "awards" && (
            <>
              <h3 className="text-sm font-semibold">Awards & Honours</h3>
              {(full?.honours.length ?? 0) === 0 ? <p className="text-xs text-muted-foreground">None recorded.</p> :
                full!.honours.map((h, i) => (
                  <div key={i} className="flex flex-wrap items-center gap-2 border-t border-border pt-2 text-sm first:border-0">
                    <Medal className="h-4 w-4 text-brand" aria-hidden />
                    <span className="font-medium">{String(h.title)}</span>
                    <Badge variant="muted">{String(h.award_category ?? h.honour_type).replace(/_/g, " ")}</Badge>
                    {h.awarded_season ? <span className="text-xs text-muted-foreground">{String(h.awarded_season)}</span> : null}
                  </div>
                ))}
              <p className="text-xs text-muted-foreground">Honours are explicitly recorded and authorised — never inferred from statistics.</p>
            </>
          )}

          {tab === "media" && (
            <>
              <h3 className="text-sm font-semibold">Photographs & media</h3>
              {photos.length === 0 ? <p className="text-xs text-muted-foreground">No photographs recorded.</p> :
                <div className="flex flex-wrap gap-3">
                  {photos.map((p) => (
                    <div key={p.id} className="flex flex-col gap-1">
                      {photoUrls[p.id]
                        ? <img src={photoUrls[p.id]} alt={p.caption ?? name} className="h-32 w-32 rounded object-cover" />
                        : <div className="flex h-32 w-32 items-center justify-center rounded bg-muted/40 text-muted-foreground"><ScrollText className="h-6 w-6" aria-hidden /></div>}
                      {p.caption && <span className="w-32 truncate text-xs text-muted-foreground">{p.caption}</span>}
                    </div>
                  ))}
                </div>}
            </>
          )}
        </CardContent></Card>
      </div>
    </AppShell>
  );
}
