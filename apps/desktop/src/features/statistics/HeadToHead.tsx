/**
 * Head-to-Head — the record between two clubs (W/L/D/T each way) plus the match list, from the one engine
 * (reusing the opposition filter). A Part 5.2 / Deliverable F capability. All-time by default; a competition
 * scope is optional. Nothing fabricated; unknown results simply aren't counted as decided.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { AppShell } from "../../components/layout/AppShell";
import { Card, CardContent } from "../../components/ui/card";
import { Select } from "../../components/ui/select";
import { api, ApiError, type Competition, type HeadToHead as H2H, type Organisation } from "../../lib/api";
import { formatDate, useDateStyle } from "../../lib/dates";
import { useWorkspace } from "../../lib/workspace-context";

export function HeadToHead() {
  const { current } = useWorkspace();
  const workspaceId = current?.id;
  const dateStyle = useDateStyle();
  const [orgs, setOrgs] = useState<Organisation[]>([]);
  const [comps, setComps] = useState<Competition[]>([]);
  const [a, setA] = useState("");
  const [b, setB] = useState("");
  const [competitionId, setCompetitionId] = useState("");
  const [data, setData] = useState<H2H | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!workspaceId) return;
    api.listOrganisations(workspaceId).then((o) => {
      setOrgs(o);
      api.statsPrimaryClub(workspaceId).then((pc) => { if (pc.organisation_id) setA(pc.organisation_id); }).catch(() => {});
    }).catch(() => setOrgs([]));
    api.listCompetitions(workspaceId).then(setComps).catch(() => setComps([]));
  }, [workspaceId]);

  const run = useCallback(() => {
    if (!workspaceId || !a || !b || a === b) { setData(null); return; }
    api.statsHeadToHead(workspaceId, a, b, { competition_id: competitionId || undefined })
      .then(setData).catch((e) => setError(e instanceof ApiError ? e.message : "Head-to-head failed."));
  }, [workspaceId, a, b, competitionId]);
  useEffect(() => { run(); }, [run]);

  const chart = useMemo(() => {
    if (!data) return null;
    const total = data.a.wins + data.b.wins + data.a.draws + data.a.ties;
    if (!total) return null;
    const pct = (n: number) => `${(n * 100 / total).toFixed(0)}%`;
    return { aw: pct(data.a.wins), bw: pct(data.b.wins), dr: pct(data.a.draws + data.a.ties) };
  }, [data]);

  if (!current) return <AppShell title="Head-to-Head"><Card><CardContent><p className="text-sm text-muted-foreground">No workspace selected.</p></CardContent></Card></AppShell>;

  const RecordCard = ({ r, accent }: { r: H2H["a"]; accent: string }) => (
    <div className="flex-1 rounded-[var(--radius-app)] border border-border p-3">
      <div className="text-sm font-semibold" style={{ color: accent }}>{r.name}</div>
      <div className="mt-1 text-3xl font-bold tabular-nums">{r.wins}<span className="text-base font-normal text-muted-foreground"> wins</span></div>
      <div className="mt-1 grid grid-cols-2 gap-x-4 gap-y-0.5 text-xs text-muted-foreground">
        <span>Played</span><span className="text-right tabular-nums text-foreground">{r.played}</span>
        <span>Lost</span><span className="text-right tabular-nums text-foreground">{r.losses}</span>
        <span>Drawn</span><span className="text-right tabular-nums text-foreground">{r.draws}</span>
        <span>Tied</span><span className="text-right tabular-nums text-foreground">{r.ties}</span>
        <span>Win %</span><span className="text-right tabular-nums text-foreground">{r.win_pct ?? "—"}</span>
      </div>
    </div>
  );

  return (
    <AppShell title="Head-to-Head" subtitle={current.name}>
      <div className="mx-auto flex max-w-4xl flex-col gap-4">
        <Card><CardContent className="flex flex-wrap items-end gap-2">
          <label className="flex flex-col gap-1 text-sm"><span className="text-xs text-muted-foreground">Club</span>
            <Select value={a} onChange={(e) => setA(e.target.value)} className="w-48"><option value="">— pick —</option>
              {orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}</Select></label>
          <span className="pb-2 text-sm text-muted-foreground">vs</span>
          <label className="flex flex-col gap-1 text-sm"><span className="text-xs text-muted-foreground">Opponent</span>
            <Select value={b} onChange={(e) => setB(e.target.value)} className="w-48"><option value="">— pick —</option>
              {orgs.filter((o) => o.id !== a).map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}</Select></label>
          {comps.length > 0 && (
            <label className="flex flex-col gap-1 text-sm"><span className="text-xs text-muted-foreground">Competition</span>
              <Select value={competitionId} onChange={(e) => setCompetitionId(e.target.value)} className="w-44"><option value="">All</option>
                {comps.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select></label>
          )}
        </CardContent></Card>

        {error && <p className="text-sm text-danger">{error}</p>}
        {(!a || !b || a === b) && <p className="text-sm text-muted-foreground">Pick two different clubs to see their head-to-head.</p>}

        {data && (
          <>
            <Card><CardContent className="flex flex-col gap-3">
              <div className="flex gap-3">
                <RecordCard r={data.a} accent="var(--brand)" />
                <RecordCard r={data.b} accent="var(--muted-foreground)" />
              </div>
              {chart && (
                <div>
                  <div className="flex h-3 overflow-hidden rounded-full bg-muted" role="img"
                    aria-label={`${data.a.name} ${data.a.wins} wins, ${data.b.name} ${data.b.wins} wins`}>
                    <div style={{ width: chart.aw, background: "var(--brand)" }} />
                    <div style={{ width: chart.dr, background: "var(--muted-foreground)" }} />
                    <div style={{ width: chart.bw, background: "var(--warning)" }} />
                  </div>
                  <div className="mt-1 flex justify-between text-[11px] text-muted-foreground">
                    <span>{data.a.name} {chart.aw}</span><span>drawn/tied {chart.dr}</span><span>{chart.bw} {data.b.name}</span>
                  </div>
                </div>
              )}
            </CardContent></Card>

            {data.matches.length > 0 && (
              <Card><CardContent className="flex flex-col gap-1">
                <h3 className="text-sm font-semibold">Matches ({data.matches.length})</h3>
                {data.matches.map((m) => (
                  <a key={m.match_id} href={`#/matches?open=${m.match_id}`}
                    className="flex items-center justify-between gap-2 rounded-[var(--radius-app)] border border-border px-2 py-1 text-xs hover:border-brand">
                    <span>{m.match_date ? formatDate(m.match_date, dateStyle) : "date unknown"}</span>
                    <span className="font-medium">
                      {m.winner === "a" ? `${data.a.name} won` : m.winner === "b" ? `${data.b.name} won` : (m.result_type ? m.result_type.replace(/_/g, " ") : "—")}
                    </span>
                  </a>
                ))}
              </CardContent></Card>
            )}
          </>
        )}
      </div>
    </AppShell>
  );
}
