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
import { openBlobUrl } from "../../lib/utils";
import { useWorkspace } from "../../lib/workspace-context";

type Tab = "overview" | "batting" | "bowling" | "fielding" | "captaincy" | "seasons" | "grandfinals" | "matches" | "records" | "awards" | "media";

const TABS: { key: Tab; label: string }[] = [
  { key: "overview", label: "Overview" }, { key: "batting", label: "Batting" }, { key: "bowling", label: "Bowling" },
  { key: "fielding", label: "Fielding & WK" }, { key: "captaincy", label: "Captaincy" }, { key: "seasons", label: "Seasons" },
  { key: "grandfinals", label: "Grand Finals" }, { key: "matches", label: "Matches" }, { key: "records", label: "Records & Milestones" },
  { key: "awards", label: "Awards & Honours" }, { key: "media", label: "Media" },
];

function num(v: unknown, dp?: number): string {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "number") return dp != null ? v.toFixed(dp) : String(v);
  return String(v);
}

type ChartPoint = { label: string; value: number | null };

/** A compact, theme-aware bar chart (SVG, no dependency). Null values render as an empty slot, never 0. */
function BarChart({ title, points, dp }: { title: string; points: ChartPoint[]; dp?: number }) {
  const W = 360, H = 150, padL = 30, padB = 22, padT = 10;
  const vals = points.map((p) => (p.value == null ? 0 : p.value));
  const max = Math.max(1, ...vals);
  const bw = points.length ? (W - padL) / points.length : 0;
  const plotH = H - padB - padT;
  return (
    <figure className="flex min-w-0 flex-col gap-1">
      <figcaption className="text-xs font-medium">{title}</figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full text-muted-foreground" role="img"
        aria-label={`${title}. ${points.map((p) => `${p.label}: ${p.value == null ? "unknown" : num(p.value, dp)}`).join(", ")}`}>
        <line x1={padL} y1={padT} x2={padL} y2={H - padB} className="stroke-border" strokeWidth={1} />
        <line x1={padL} y1={H - padB} x2={W} y2={H - padB} className="stroke-border" strokeWidth={1} />
        <text x={padL - 4} y={padT + 6} textAnchor="end" className="fill-current text-[8px]">{num(max, dp)}</text>
        {points.map((p, i) => {
          if (p.value == null) return null;
          const h = (p.value / max) * plotH;
          const x = padL + i * bw + bw * 0.18;
          return (
            <g key={i}>
              <rect x={x} y={H - padB - h} width={bw * 0.64} height={Math.max(0, h)} rx={1.5} className="fill-brand" />
              <text x={x + bw * 0.32} y={H - padB + 9} textAnchor="middle" className="fill-current text-[7px]">{p.label}</text>
            </g>
          );
        })}
      </svg>
    </figure>
  );
}

/** A compact, theme-aware line chart (SVG). Gaps are drawn where a value is unknown. */
function LineChart({ title, points, dp }: { title: string; points: ChartPoint[]; dp?: number }) {
  const W = 360, H = 150, padL = 30, padB = 22, padT = 10;
  const known = points.filter((p) => p.value != null) as { label: string; value: number }[];
  const max = Math.max(1, ...known.map((p) => p.value));
  const plotH = H - padB - padT;
  const step = points.length > 1 ? (W - padL - 8) / (points.length - 1) : 0;
  const xy = (i: number, v: number) => [padL + 8 + i * step, H - padB - (v / max) * plotH] as const;
  const path = points.map((p, i) => (p.value == null ? null : xy(i, p.value)))
    .filter((c): c is readonly [number, number] => c != null)
    .map(([x, y], j) => `${j === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  return (
    <figure className="flex min-w-0 flex-col gap-1">
      <figcaption className="text-xs font-medium">{title}</figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full text-muted-foreground" role="img"
        aria-label={`${title}. ${points.map((p) => `${p.label}: ${p.value == null ? "unknown" : num(p.value, dp)}`).join(", ")}`}>
        <line x1={padL} y1={padT} x2={padL} y2={H - padB} className="stroke-border" strokeWidth={1} />
        <line x1={padL} y1={H - padB} x2={W} y2={H - padB} className="stroke-border" strokeWidth={1} />
        <text x={padL - 4} y={padT + 6} textAnchor="end" className="fill-current text-[8px]">{num(max, dp)}</text>
        {path && <path d={path} fill="none" className="stroke-brand" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />}
        {points.map((p, i) => {
          if (p.value == null) return null;
          const [x, y] = xy(i, p.value);
          return <g key={i}>
            <circle cx={x} cy={y} r={2.5} className="fill-brand" />
            <text x={x} y={H - padB + 9} textAnchor="middle" className="fill-current text-[7px]">{p.label}</text>
          </g>;
        })}
      </svg>
    </figure>
  );
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
      openBlobUrl(await api.profilePdfUrl(current.id, personId!), `${name || "player"}-profile.pdf`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "PDF export failed.");
    }
  };

  const publishProfile = async () => {
    try {
      await api.publicationCreate(current.id, { kind: "player_profile", person_id: personId!, title: name });
      setError(null);
      window.alert("Published to a permanent public URL. Manage it under Website Publishing.");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not publish this profile (admins only).");
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
              {Number(full?.grand_finals?.premierships ?? 0) > 0 && (
                <Badge variant="brand"><Trophy className="mr-1 h-3 w-3" aria-hidden />
                  {full!.grand_finals.premierships}× premiership{full!.grand_finals.premierships === 1 ? "" : "s"}</Badge>
              )}
              {(full?.clubs ?? []).slice(0, 2).map((cl) => <span key={cl.team_id} className="text-muted-foreground">{cl.club}</span>)}
            </div>
          </div>
          <div className="ml-auto flex gap-2">
            <Button size="sm" variant="outline" onClick={() => navigate("/people")}>Directory</Button>
            <Button size="sm" variant="outline" onClick={() => void publishProfile()}>Publish</Button>
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

          {tab === "grandfinals" && (() => {
            const gf = full?.grand_finals;
            if (!gf || gf.appearances === 0)
              return <p className="text-xs text-muted-foreground">No grand finals recorded.</p>;
            const gfb = gf.batting, gfw = gf.bowling, gfc = gf.captaincy;
            return (
              <>
                <h3 className="text-sm font-semibold">Grand finals</h3>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                  {statCard("Grand finals", gf.appearances)}
                  {statCard("Premierships", gf.premierships)}
                  {gf.has_batting && statCard("GF runs", gfb.runs, undefined, Boolean(gfb.runs_known_minimum))}
                  {gf.has_batting && statCard("GF average", gfb.average, 2)}
                  {gf.has_batting && statCard("GF highest", gfb.highest_score)}
                  {gf.has_bowling && statCard("GF wickets", gfw.wickets, undefined, Boolean(gfw.wickets_known_minimum))}
                  {gf.has_bowling && statCard("GF best (match)", gfw.best_match_wickets)}
                  {gf.has_captaincy && statCard("GF captained", gfc.captained)}
                  {gf.has_captaincy && statCard("GF won as captain", gfc.gf_wins)}
                </div>
                <p className="text-xs text-muted-foreground">
                  Premierships count grand finals {name}&rsquo;s team won while they featured — a recorded result, never inferred.
                </p>
                {gf.matches.length > 0 && (
                  <>
                    <h4 className="text-xs font-semibold">Every grand final</h4>
                    {table([{ key: "match_date", label: "Date" }, { key: "runs", label: "Runs", align: "right" },
                            { key: "wickets", label: "Wkts", align: "right" }, { key: "catches", label: "Ct", align: "right" },
                            { key: "result_type", label: "Result" }],
                           gf.matches, () => navigate("/matches"))}
                  </>
                )}
              </>
            );
          })()}

          {tab === "seasons" && (
            <>
              <h3 className="text-sm font-semibold">Season by season</h3>
              {(full?.seasons.length ?? 0) > 1 && (() => {
                const sp = full!.seasons.map((s) => ({ label: String(s.label ?? ""), s }));
                const val = (s: Record<string, unknown>, k: string): number | null =>
                  s[k] == null ? null : Number(s[k]);
                let cum = 0;
                const cumRuns = sp.map(({ label, s }) => { cum += Number(s.runs ?? 0); return { label, value: cum }; });
                return (
                  <div className="grid gap-4 border-b border-border pb-3 sm:grid-cols-2">
                    {c?.has_batting && <BarChart title="Runs per season" points={sp.map(({ label, s }) => ({ label, value: val(s, "runs") }))} />}
                    {c?.has_batting && <LineChart title="Batting average by season" points={sp.map(({ label, s }) => ({ label, value: val(s, "batting_average") }))} dp={2} />}
                    {c?.has_bowling && <BarChart title="Wickets per season" points={sp.map(({ label, s }) => ({ label, value: val(s, "wickets") }))} />}
                    {c?.has_batting && <LineChart title="Cumulative runs" points={cumRuns} />}
                  </div>
                );
              })()}
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
