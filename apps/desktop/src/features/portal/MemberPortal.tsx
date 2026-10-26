/**
 * Member Portal (Phase 16 follow-up) — the authenticated, read-only club portal for members.
 *
 * Shows the club's published public items PLUS the non-public catalogue the member is permitted to see
 * (each flagged public / member-only), and an embedded read-only **Ask OneStats** box (Ask-on-portal)
 * when the member may query. Read-only: links open published snapshots; nothing here writes or publishes.
 */
import { Globe, Lock, MessageCircleQuestion, Search } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { AppShell } from "../../components/layout/AppShell";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import { Input } from "../../components/ui/input";
import { api, ApiError, type AskAnswer, type MemberPortal as MemberPortalData } from "../../lib/api";
import { NoWorkspace, useManage } from "../manage/_shared";

export function MemberPortal() {
  const { workspaceId } = useManage();
  const [data, setData] = useState<MemberPortalData | null>(null);
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!workspaceId) return;
    try { setData(await api.memberPortal(workspaceId)); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Could not load the portal."); }
  }, [workspaceId]);
  useEffect(() => { void load(); }, [load]);

  if (!workspaceId) return <NoWorkspace />;

  const q = query.trim().toLowerCase();
  const items = (data?.items ?? []).filter((i) => !q || i.title.toLowerCase().includes(q));
  const players = items.filter((i) => i.kind === "player_profile");
  const reports = items.filter((i) => i.kind !== "player_profile");

  const section = (name: string, list: typeof items) => list.length > 0 && (
    <Card><CardContent className="flex flex-col gap-2">
      <h3 className="text-sm font-semibold">{name}</h3>
      {list.map((i) => (
        <div key={i.slug} className="flex flex-wrap items-center gap-2 border-t border-border pt-1.5 text-sm first:border-0 first:pt-0">
          <span className="font-medium">{i.title}</span>
          {i.public
            ? <Badge variant="success"><Globe className="mr-1 h-3 w-3" aria-hidden />Public</Badge>
            : <Badge variant="muted"><Lock className="mr-1 h-3 w-3" aria-hidden />Members only</Badge>}
          {i.stale && <Badge variant="warning">Needs refresh</Badge>}
          {i.path && (
            <a href={`#/public-view${i.path}`} className="ml-auto text-xs text-brand underline"
               onClick={(e) => { e.preventDefault(); if (i.path) window.open(i.path, "_blank"); }}>Open</a>
          )}
        </div>
      ))}
    </CardContent></Card>
  );

  return (
    <AppShell title="Member Portal" subtitle={data ? `${data.club} — members' records` : "Members' records"}>
      <div className="mx-auto flex max-w-3xl flex-col gap-4">
        {error && <p className="rounded-[var(--radius-app)] border border-danger/40 bg-danger/5 px-3 py-2 text-sm text-danger">{error}</p>}

        <Card><CardContent className="flex flex-col gap-2">
          <label className="relative">
            <Search className="pointer-events-none absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
            <Input className="pl-8" placeholder="Search players and reports…" value={query}
              onChange={(e) => setQuery(e.target.value)} />
          </label>
          {data && (
            <p className="text-xs text-muted-foreground">
              {data.public_count} public · {data.member_only_count} members-only. Members-only items are not
              on the public website.
            </p>
          )}
        </CardContent></Card>

        {data?.ask?.enabled && <PortalAsk workspaceId={workspaceId} />}

        {items.length === 0 && <p className="text-xs text-muted-foreground">No records match.</p>}
        {section("Players", players)}
        {section("Reports", reports)}
      </div>
    </AppShell>
  );
}

/** Embedded read-only Ask OneStats box — reuses the one deterministic engine; numbers are never invented. */
function PortalAsk({ workspaceId }: { workspaceId: string }) {
  const [q, setQ] = useState("");
  const [answer, setAnswer] = useState<AskAnswer | null>(null);
  const [busy, setBusy] = useState(false);

  const ask = async () => {
    if (!q.trim()) return;
    setBusy(true);
    try { setAnswer(await api.askOneStats(workspaceId, q.trim())); }
    catch { setAnswer(null); }
    finally { setBusy(false); }
  };

  return (
    <Card><CardContent className="flex flex-col gap-2">
      <h3 className="flex items-center gap-2 text-sm font-semibold">
        <MessageCircleQuestion className="h-4 w-4 text-brand" aria-hidden /> Ask OneStats
      </h3>
      <div className="flex gap-2">
        <Input placeholder="e.g. Who has scored the most runs?" value={q}
          onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") void ask(); }} />
        <Button size="sm" disabled={busy || !q.trim()} onClick={() => void ask()}>Ask</Button>
      </div>
      {answer && (
        answer.matched
          ? <p className="text-sm">{answer.answer_summary || answer.interpretation || answer.report_name}</p>
          : <p className="text-sm text-muted-foreground">{answer.message || "Couldn't map that question."}</p>
      )}
      {answer?.qualifications?.map((qf, i) => <p key={i} className="text-[11px] text-muted-foreground">{qf}</p>)}
    </CardContent></Card>
  );
}
