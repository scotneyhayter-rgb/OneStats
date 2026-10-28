/**
 * Spreadsheet-style entry grids for batting, bowling, fall of wicket and partnerships (Stage 7,
 * §3/§5). Each grid edits rows directly against the Phase 6 API (add/remove/edit), commits on blur
 * (no per-keystroke chatter), keeps unknown distinct from zero, and supports keyboard navigation
 * (arrows / Enter / Tab) within the numeric cells via the tested nextCell helper.
 */

import { ChevronDown, ChevronUp, GripVertical, Plus, Trash2 } from "lucide-react";
import { type KeyboardEvent, useCallback, useEffect, useRef, useState } from "react";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { ConfirmDialog } from "../../components/ui/dialog";
import { Select } from "../../components/ui/select";
import { api, ApiError, type BattingEntry, type BowlingEntry, type DismissalFielder, type FallOfWicket, type Partnership, type Person } from "../../lib/api";
import { PlayerSelect } from "./PlayerSelect";
import {
  battingOrderIssues,
  DISMISSAL_TYPES,
  fowIssues,
  nextCell,
  parseIntOrNull,
  PARTNERSHIP_END_REASONS,
} from "./scorecard-logic";

type Saver = (msg: string | null) => void;

/** This innings' batters, as always-available options for the FOW/partnership batter selectors —
 *  a fall of wicket or partnership can only involve a batter who batted, even a fill-in from
 *  another club who would otherwise be hidden by the club-scoped default. Names come from the
 *  editor's preloaded cache; re-fetched when the batting card changes. */
function useInningsBatters(
  workspaceId: string, inningsId: string, nameOf: (id: string | null) => string | null, refreshKey?: number,
): { id: string; display_name: string }[] {
  const [ids, setIds] = useState<string[]>([]);
  useEffect(() => {
    let alive = true;
    void api.listBatting(workspaceId, inningsId)
      .then((rows) => { if (alive) setIds(rows.map((r) => r.person_id).filter((x): x is string => !!x)); })
      .catch(() => { if (alive) setIds([]); });
    return () => { alive = false; };
  }, [workspaceId, inningsId, refreshKey]);
  // dedupe, keep batting order; resolve names from the shared cache (fallback keeps them selectable)
  const seen = new Set<string>();
  const out: { id: string; display_name: string }[] = [];
  for (const id of ids) {
    if (seen.has(id)) continue;
    seen.add(id);
    out.push({ id, display_name: nameOf(id) ?? "Unknown player" });
  }
  return out;
}

interface GridCtx {
  workspaceId: string;
  inningsId: string;
  canManage: boolean;
  nameOf: (id: string | null) => string | null;
  onPersonLoaded: (p: Person) => void;
  onDirty: Saver;
  onChanged: () => void; // ask parent to recompute totals/validation
  refreshKey?: number;   // bumped by the parent so sibling grids re-fetch (e.g. FOW -> partnerships)
  // club scoping for player selectors (Phase 7.4): batters scope to the batting club, bowlers/
  // fielders to the bowling club; "Show all" in the selector keeps everyone discoverable
  battingOrgId?: string | null;
  bowlingOrgId?: string | null;
  battingTeamName?: string | null;
  bowlingTeamName?: string | null;
}

/** A focus grid: register inputs by (row,col); handle arrow/Enter keys to move focus. */
function useFocusGrid(cols: number, rows: number) {
  const refs = useRef(new Map<string, HTMLInputElement>());
  const key = (r: number, c: number) => `${r}:${c}`;
  const register = (r: number, c: number) => (el: HTMLInputElement | null) => {
    const k = key(r, c);
    if (el) refs.current.set(k, el);
    else refs.current.delete(k);
  };
  const onKeyDown = (r: number, c: number) => (e: KeyboardEvent) => {
    let mapped: Parameters<typeof nextCell>[1] | null = null;
    if (e.key === "ArrowUp") mapped = "ArrowUp";
    else if (e.key === "ArrowDown") mapped = "ArrowDown";
    else if (e.key === "Enter") mapped = "Enter";
    // Arrow left/right inside a text input should move the caret, not the cell — leave them.
    if (!mapped) return;
    e.preventDefault();
    const target = nextCell({ row: r, col: c }, mapped, { rows, cols });
    refs.current.get(key(target.row, target.col))?.focus();
  };
  return { register, onKeyDown };
}

/** Numeric cell: blank = unknown (italic), a number = recorded. Commits parsed value on blur. */
function NumCell({
  value,
  onCommit,
  inputRef,
  onKeyDown,
  ariaLabel,
  disabled,
  width = "w-16",
  invalid = false,
  invalidTitle,
}: {
  value: number | null;
  onCommit: (v: number | null) => void;
  inputRef?: (el: HTMLInputElement | null) => void;
  onKeyDown?: (e: KeyboardEvent) => void;
  ariaLabel: string;
  disabled?: boolean;
  width?: string;
  /** Subtle advisory highlight (e.g. a FOW score that decreased); never blocks editing. */
  invalid?: boolean;
  invalidTitle?: string;
}) {
  const [text, setText] = useState(value === null ? "" : String(value));
  useEffect(() => setText(value === null ? "" : String(value)), [value]);
  return (
    <input
      ref={inputRef}
      aria-label={ariaLabel}
      aria-invalid={invalid || undefined}
      title={invalid ? invalidTitle : undefined}
      inputMode="numeric"
      disabled={disabled}
      value={text}
      placeholder="—"
      onChange={(e) => setText(e.target.value)}
      onKeyDown={onKeyDown}
      onBlur={() => {
        const parsed = parseIntOrNull(text);
        setText(parsed === null ? "" : String(parsed));
        if (parsed !== value) onCommit(parsed);
      }}
      className={`${width} h-8 rounded-[var(--radius-app)] border px-2 text-sm tabular-nums placeholder:italic placeholder:text-muted-foreground focus-visible:outline-2 focus-visible:outline-[var(--ring)] disabled:opacity-50 ${
        invalid ? "border-danger/60 bg-danger/5 text-danger" : "border-border bg-card"
      }`}
    />
  );
}

function useRows<T>(load: () => Promise<T[]>, onError: Saver, refreshKey = 0) {
  const [rows, setRows] = useState<T[]>([]);
  const refresh = useCallback(async () => {
    try {
      setRows(await load());
    } catch (e) {
      onError(e instanceof ApiError ? e.message : "Failed to load rows");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  // re-fetch on mount and whenever a sibling signals derived data changed (e.g. FOW -> partnerships)
  useEffect(() => {
    void refresh();
  }, [refresh, refreshKey]);
  return { rows, setRows, refresh };
}

// ---- batting ---------------------------------------------------------------------------------

export function BattingGrid(ctx: GridCtx) {
  const { workspaceId, inningsId, canManage, nameOf, onPersonLoaded, onDirty, onChanged } = ctx;
  const { rows, refresh } = useRows<BattingEntry>(() => api.listBatting(workspaceId, inningsId), onDirty, ctx.refreshKey);
  const nav = useFocusGrid(4, rows.length); // runs, balls, 4s, 6s
  // immediate, non-blocking advisories: a batter out of order / appearing twice (subtle highlight)
  const bIssues = battingOrderIssues(rows.map((r) => ({ id: r.id, batting_position: r.batting_position, person_id: r.person_id })));
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [confirmRemove, setConfirmRemove] = useState<BattingEntry | null>(null);

  const commit = async (id: string, body: Record<string, unknown>) => {
    try {
      await api.updateBatting(workspaceId, inningsId, id, body);
      await refresh(); // re-read so row-bound fields (player, how-out) show the saved value
      onChanged();
    } catch (e) {
      onDirty(e instanceof ApiError ? e.message : "Save failed");
    }
  };
  const addRow = async () => {
    try {
      await api.createBatting(workspaceId, inningsId, { batting_position: rows.length + 1 });
      await refresh();
      onChanged();
    } catch (e) {
      onDirty(e instanceof ApiError ? e.message : "Could not add batter");
    }
  };

  // reorder: send the complete new order of ids; the backend renumbers 1..n (records keep stats)
  const applyOrder = async (orderedIds: string[]) => {
    try {
      await api.reorderBatting(workspaceId, inningsId, orderedIds);
      await refresh();
      onChanged();
    } catch (e) {
      onDirty(e instanceof ApiError ? e.message : "Could not reorder batters");
    }
  };
  const move = (i: number, dir: -1 | 1) => {
    const j = i + dir;
    if (j < 0 || j >= rows.length) return;
    const ids = rows.map((r) => r.id);
    [ids[i], ids[j]] = [ids[j], ids[i]];
    void applyOrder(ids);
  };
  const dropOn = (to: number) => {
    if (dragIndex === null || dragIndex === to) { setDragIndex(null); return; }
    const ids = rows.map((r) => r.id);
    const [moved] = ids.splice(dragIndex, 1);
    ids.splice(to, 0, moved);
    setDragIndex(null);
    void applyOrder(ids);
  };

  const hasStats = (r: BattingEntry) =>
    r.person_id !== null || r.runs !== null || r.balls_faced !== null || r.fours !== null ||
    r.sixes !== null || r.minutes !== null || r.dismissal_type !== null ||
    r.bowler_person_id !== null || r.fielder_person_id !== null;
  const requestRemove = (r: BattingEntry) => (hasStats(r) ? setConfirmRemove(r) : void doRemove(r.id));
  const doRemove = async (id: string) => {
    try {
      await api.deleteBatting(workspaceId, inningsId, id);
      // renumber the remaining entries so positions stay 1..n (no gaps, no resurrection)
      const remaining = rows.filter((r) => r.id !== id).map((r) => r.id);
      if (remaining.length) await api.reorderBatting(workspaceId, inningsId, remaining);
      await refresh();
      onChanged();
    } catch (e) {
      onDirty(e instanceof ApiError ? e.message : "Could not remove batter");
    }
  };

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[720px] border-collapse text-sm">
        <thead>
          <tr className="text-left text-xs uppercase text-muted-foreground">
            {canManage && <th className="w-6" />}
            <th className="w-8 px-1 py-1">#</th>
            <th className="px-1 py-1">Batter</th>
            <th className="px-1 py-1">How out</th>
            <th className="px-1 py-1">Fielder</th>
            <th className="px-1 py-1">Bowler</th>
            <th className="px-1 py-1">R</th>
            <th className="px-1 py-1">B</th>
            <th className="px-1 py-1">4s</th>
            <th className="px-1 py-1">6s</th>
            {canManage && <th className="w-14 px-1 py-1 text-center">Order</th>}
            {canManage && <th className="w-8" />}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.id} className={`border-t border-border ${dragIndex === i ? "opacity-50" : ""}`}
              onDragOver={canManage ? (e) => e.preventDefault() : undefined}
              onDrop={canManage ? () => dropOn(i) : undefined}>
              {canManage && (
                <td className="px-1 py-1">
                  <span draggable onDragStart={() => setDragIndex(i)} onDragEnd={() => setDragIndex(null)}
                    role="button" aria-label={`Drag batter ${i + 1}`} title="Drag to reorder"
                    className="flex cursor-grab items-center justify-center text-muted-foreground hover:text-foreground active:cursor-grabbing">
                    <GripVertical className="h-4 w-4" aria-hidden />
                  </span>
                </td>
              )}
              <td className={`px-1 py-1 tabular-nums ${bIssues.outOfOrderIds.has(r.id) ? "font-semibold text-danger" : "text-muted-foreground"}`}
                title={bIssues.outOfOrderIds.has(r.id) ? "Batting position is out of order (positions should increase down the card)." : undefined}>
                {r.batting_position ?? "—"}</td>
              <td className="min-w-[180px] px-1 py-1">
                <div className={bIssues.duplicatePersonIds.has(r.id) ? "rounded-[var(--radius-app)] ring-1 ring-danger/60" : undefined}
                  title={bIssues.duplicatePersonIds.has(r.id) ? "This player already appears in this batting innings." : undefined}>
                  <PlayerSelect workspaceId={workspaceId} value={r.person_id} nameOf={nameOf} onPersonLoaded={onPersonLoaded}
                    disabled={!canManage} aria-label={`Batter ${i + 1}`} organisationId={ctx.battingOrgId} scopeLabel={ctx.battingTeamName}
                    onChange={(pid) => void commit(r.id, { person_id: pid })} />
                </div>
              </td>
              <td className="px-1 py-1">
                <Select aria-label={`How out ${i + 1}`} disabled={!canManage} value={r.dismissal_type ?? ""}
                  onChange={(e) => void commit(r.id, { dismissal_type: e.target.value || null })} className="h-8 w-36">
                  <option value="">— unknown —</option>
                  {DISMISSAL_TYPES.map((d) => <option key={d} value={d}>{d.replace(/_/g, " ")}</option>)}
                </Select>
              </td>
              <td className="min-w-[150px] px-1 py-1">
                <PlayerSelect workspaceId={workspaceId} value={r.fielder_person_id} nameOf={nameOf} onPersonLoaded={onPersonLoaded}
                  disabled={!canManage} aria-label={`Fielder for batter ${i + 1}`} organisationId={ctx.bowlingOrgId} scopeLabel={ctx.bowlingTeamName}
                  onChange={(pid) => void commit(r.id, { fielder_person_id: pid })} />
                {r.dismissal_type === "run_out" && r.fielder_person_id && (
                  <RunOutAssists ctx={ctx} entryId={r.id} primaryId={r.fielder_person_id} />
                )}
              </td>
              <td className="min-w-[150px] px-1 py-1">
                <PlayerSelect workspaceId={workspaceId} value={r.bowler_person_id} nameOf={nameOf} onPersonLoaded={onPersonLoaded}
                  disabled={!canManage} aria-label={`Bowler for batter ${i + 1}`} organisationId={ctx.bowlingOrgId} scopeLabel={ctx.bowlingTeamName}
                  onChange={(pid) => void commit(r.id, { bowler_person_id: pid })} />
              </td>
              <td className="px-1 py-1"><NumCell value={r.runs} ariaLabel={`Runs ${i + 1}`} disabled={!canManage}
                inputRef={nav.register(i, 0)} onKeyDown={nav.onKeyDown(i, 0)} onCommit={(v) => void commit(r.id, { runs: v })} /></td>
              <td className="px-1 py-1"><NumCell value={r.balls_faced} ariaLabel={`Balls ${i + 1}`} disabled={!canManage}
                inputRef={nav.register(i, 1)} onKeyDown={nav.onKeyDown(i, 1)} onCommit={(v) => void commit(r.id, { balls_faced: v })} /></td>
              <td className="px-1 py-1"><NumCell value={r.fours} ariaLabel={`Fours ${i + 1}`} disabled={!canManage} width="w-12"
                inputRef={nav.register(i, 2)} onKeyDown={nav.onKeyDown(i, 2)} onCommit={(v) => void commit(r.id, { fours: v })} /></td>
              <td className="px-1 py-1"><NumCell value={r.sixes} ariaLabel={`Sixes ${i + 1}`} disabled={!canManage} width="w-12"
                inputRef={nav.register(i, 3)} onKeyDown={nav.onKeyDown(i, 3)} onCommit={(v) => void commit(r.id, { sixes: v })} /></td>
              {canManage && (
                <td className="px-1 py-1">
                  <div className="flex items-center justify-center gap-0.5">
                    <button aria-label={`Move batter ${i + 1} up`} disabled={i === 0} onClick={() => move(i, -1)}
                      className="rounded-[var(--radius-app)] p-1 text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-30">
                      <ChevronUp className="h-3.5 w-3.5" aria-hidden />
                    </button>
                    <button aria-label={`Move batter ${i + 1} down`} disabled={i === rows.length - 1} onClick={() => move(i, 1)}
                      className="rounded-[var(--radius-app)] p-1 text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-30">
                      <ChevronDown className="h-3.5 w-3.5" aria-hidden />
                    </button>
                  </div>
                </td>
              )}
              {canManage && (
                <td className="px-1 py-1">
                  <button aria-label={`Remove batter ${i + 1}`} onClick={() => requestRemove(r)}
                    className="rounded-[var(--radius-app)] p-1 text-muted-foreground hover:bg-muted hover:text-danger">
                    <Trash2 className="h-3.5 w-3.5" aria-hidden />
                  </button>
                </td>
              )}
            </tr>
          ))}
          {rows.length === 0 && (
            <tr><td colSpan={12} className="px-1 py-3 text-sm text-muted-foreground">No batters recorded. Add rows as the card allows — partial cards are fine.</td></tr>
          )}
        </tbody>
      </table>
      {bIssues.messages.length > 0 && (
        <ul className="mt-2 space-y-0.5 text-[11px] text-danger">
          {bIssues.messages.map((m) => <li key={m.code}>• {m.message}</li>)}
        </ul>
      )}
      {canManage && (
        <Button variant="outline" size="sm" className="mt-2" onClick={() => void addRow()}>
          <Plus className="h-4 w-4" aria-hidden /> Add batter
        </Button>
      )}
      <ConfirmDialog
        open={confirmRemove !== null}
        title="Remove this batter?"
        description={`This batting entry has recorded figures${confirmRemove && nameOf(confirmRemove.person_id) ? ` for ${nameOf(confirmRemove.person_id)}` : ""}. Removing it deletes the entry and its dismissal (the player's profile is kept; linked fall-of-wicket/partnership references are cleared). The remaining batters renumber.`}
        confirmLabel="Remove"
        danger
        onCancel={() => setConfirmRemove(null)}
        onConfirm={() => { const id = confirmRemove?.id; setConfirmRemove(null); if (id) void doRemove(id); }}
      />
    </div>
  );
}

// ---- bowling ---------------------------------------------------------------------------------

export function BowlingGrid(ctx: GridCtx) {
  const { workspaceId, inningsId, canManage, nameOf, onPersonLoaded, onDirty, onChanged } = ctx;
  const { rows, refresh } = useRows<BowlingEntry>(() => api.listBowling(workspaceId, inningsId), onDirty, ctx.refreshKey);
  const [overs, setOvers] = useState<Record<string, string>>({});

  const commit = async (id: string, body: Record<string, unknown>) => {
    try {
      await api.updateBowling(workspaceId, inningsId, id, body);
      await refresh();
      onChanged();
    } catch (e) {
      onDirty(e instanceof ApiError ? e.message : "Save failed");
    }
  };
  const addRow = async () => {
    try {
      await api.createBowling(workspaceId, inningsId, { bowling_order: rows.length + 1 });
      await refresh();
    } catch (e) {
      onDirty(e instanceof ApiError ? e.message : "Could not add bowler");
    }
  };
  const remove = async (id: string) => {
    await api.deleteBowling(workspaceId, inningsId, id);
    await refresh();
    onChanged();
  };

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] border-collapse text-sm">
        <thead>
          <tr className="text-left text-xs uppercase text-muted-foreground">
            <th className="px-1 py-1">Bowler</th>
            <th className="px-1 py-1">Overs</th>
            <th className="px-1 py-1">M</th>
            <th className="px-1 py-1">R</th>
            <th className="px-1 py-1">W</th>
            <th className="px-1 py-1">Wd</th>
            <th className="px-1 py-1">Nb</th>
            {canManage && <th className="w-8" />}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.id} className="border-t border-border">
              <td className="min-w-[180px] px-1 py-1">
                <PlayerSelect workspaceId={workspaceId} value={r.person_id} nameOf={nameOf} onPersonLoaded={onPersonLoaded}
                  disabled={!canManage} aria-label={`Bowler ${i + 1}`} organisationId={ctx.bowlingOrgId} scopeLabel={ctx.bowlingTeamName}
                  onChange={(pid) => void commit(r.id, { person_id: pid })} />
              </td>
              <td className="px-1 py-1">
                <input aria-label={`Overs ${i + 1}`} disabled={!canManage}
                  value={overs[r.id] ?? r.overs_text ?? ""} placeholder="—"
                  onChange={(e) => setOvers((o) => ({ ...o, [r.id]: e.target.value }))}
                  onBlur={() => { const t = (overs[r.id] ?? r.overs_text ?? "").trim(); if (t !== (r.overs_text ?? "")) void commit(r.id, { overs_text: t || null }); }}
                  title="Cricket-over notation e.g. 5.3 = 5 overs 3 balls (never a decimal)"
                  className="w-16 h-8 rounded-[var(--radius-app)] border border-border bg-card px-2 text-sm tabular-nums placeholder:italic placeholder:text-muted-foreground focus-visible:outline-2 focus-visible:outline-[var(--ring)] disabled:opacity-50" />
              </td>
              <td className="px-1 py-1"><NumCell value={r.maidens} ariaLabel={`Maidens ${i + 1}`} disabled={!canManage} width="w-12" onCommit={(v) => void commit(r.id, { maidens: v })} /></td>
              <td className="px-1 py-1"><NumCell value={r.runs_conceded} ariaLabel={`Runs conceded ${i + 1}`} disabled={!canManage} onCommit={(v) => void commit(r.id, { runs_conceded: v })} /></td>
              <td className="px-1 py-1"><NumCell value={r.wickets} ariaLabel={`Wickets ${i + 1}`} disabled={!canManage} width="w-12" onCommit={(v) => void commit(r.id, { wickets: v })} /></td>
              <td className="px-1 py-1"><NumCell value={r.wides} ariaLabel={`Wides ${i + 1}`} disabled={!canManage} width="w-12" onCommit={(v) => void commit(r.id, { wides: v })} /></td>
              <td className="px-1 py-1"><NumCell value={r.noballs} ariaLabel={`No-balls ${i + 1}`} disabled={!canManage} width="w-12" onCommit={(v) => void commit(r.id, { noballs: v })} /></td>
              {canManage && (
                <td className="px-1 py-1">
                  <button aria-label={`Remove bowler ${i + 1}`} onClick={() => void remove(r.id)}
                    className="rounded-[var(--radius-app)] p-1 text-muted-foreground hover:bg-muted hover:text-danger">
                    <Trash2 className="h-3.5 w-3.5" aria-hidden />
                  </button>
                </td>
              )}
            </tr>
          ))}
          {rows.length === 0 && (
            <tr><td colSpan={8} className="px-1 py-3 text-sm text-muted-foreground">No bowlers recorded.</td></tr>
          )}
        </tbody>
      </table>
      {canManage && (
        <Button variant="outline" size="sm" className="mt-2" onClick={() => void addRow()}>
          <Plus className="h-4 w-4" aria-hidden /> Add bowler
        </Button>
      )}
    </div>
  );
}

// ---- fall of wicket --------------------------------------------------------------------------

export function FowGrid(ctx: GridCtx) {
  const { workspaceId, inningsId, canManage, nameOf, onPersonLoaded, onDirty, onChanged } = ctx;
  const { rows, refresh } = useRows<FallOfWicket>(() => api.listFow(workspaceId, inningsId), onDirty, ctx.refreshKey);
  const batters = useInningsBatters(workspaceId, inningsId, nameOf, ctx.refreshKey);
  // immediate, non-blocking advisories driving the subtle inline highlight (never blocks saving)
  const issues = fowIssues(rows.map((r) => ({ id: r.id, wicket_number: r.wicket_number, team_score: r.team_score })));

  const commit = async (id: string, body: Record<string, unknown>) => {
    try {
      await api.updateFow(workspaceId, inningsId, id, body);
      await refresh(); // re-read so the dismissed-player field shows the saved value
      onChanged();
    } catch (e) {
      onDirty(e instanceof ApiError ? e.message : "Save failed");
    }
  };
  const addRow = async () => {
    try {
      // Use the smallest unused wicket number, not rows.length + 1: imported falls of wicket need not
      // be a contiguous 1..N (a gap would make rows.length + 1 collide with an existing number and the
      // backend rejects it as a duplicate_wicket_number). This fills any gap and never collides.
      const used = new Set(rows.map((r) => r.wicket_number).filter((n): n is number => n != null));
      let next = 1;
      while (used.has(next)) next += 1;
      await api.createFow(workspaceId, inningsId, { wicket_number: next });
      await refresh();
    } catch (e) {
      onDirty(e instanceof ApiError ? e.message : "Could not add fall of wicket");
    }
  };
  const remove = async (id: string) => { await api.deleteFow(workspaceId, inningsId, id); await refresh(); onChanged(); };

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[520px] border-collapse text-sm">
        <thead>
          <tr className="text-left text-xs uppercase text-muted-foreground">
            <th className="px-1 py-1">Wkt</th>
            <th className="px-1 py-1">Score</th>
            <th className="px-1 py-1">Batter out</th>
            {canManage && <th className="w-8" />}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.id} className="border-t border-border">
              <td className="px-1 py-1"><NumCell value={r.wicket_number} ariaLabel={`Wicket number ${i + 1}`} disabled={!canManage} width="w-12"
                invalid={issues.duplicateWicketIds.has(r.id)} invalidTitle="This wicket number is used by another fall of wicket."
                onCommit={(v) => void commit(r.id, { wicket_number: v })} /></td>
              <td className="px-1 py-1"><NumCell value={r.team_score} ariaLabel={`Team score ${i + 1}`} disabled={!canManage}
                invalid={issues.decreasingScoreIds.has(r.id)} invalidTitle="Lower than an earlier wicket — the team total only rises."
                onCommit={(v) => void commit(r.id, { team_score: v })} /></td>
              <td className="min-w-[180px] px-1 py-1">
                <PlayerSelect workspaceId={workspaceId} value={r.dismissed_person_id} nameOf={nameOf} onPersonLoaded={onPersonLoaded}
                  disabled={!canManage} aria-label={`Batter out ${i + 1}`} organisationId={ctx.battingOrgId} scopeLabel={ctx.battingTeamName}
                  priorityPeople={batters}
                  onChange={(pid) => void commit(r.id, { dismissed_person_id: pid })} />
              </td>
              {canManage && (
                <td className="px-1 py-1">
                  <button aria-label={`Remove fall ${i + 1}`} onClick={() => void remove(r.id)}
                    className="rounded-[var(--radius-app)] p-1 text-muted-foreground hover:bg-muted hover:text-danger">
                    <Trash2 className="h-3.5 w-3.5" aria-hidden />
                  </button>
                </td>
              )}
            </tr>
          ))}
          {rows.length === 0 && (
            <tr><td colSpan={4} className="px-1 py-3 text-sm text-muted-foreground">No fall-of-wicket recorded.</td></tr>
          )}
        </tbody>
      </table>
      {issues.messages.length > 0 && (
        <ul className="mt-2 space-y-0.5 text-[11px] text-danger">
          {issues.messages.map((m) => <li key={m.code}>• {m.message}</li>)}
        </ul>
      )}
      {canManage && (
        <Button variant="outline" size="sm" className="mt-2" onClick={() => void addRow()}>
          <Plus className="h-4 w-4" aria-hidden /> Add fall of wicket
        </Button>
      )}
    </div>
  );
}

// ---- partnerships ----------------------------------------------------------------------------

export function PartnershipsGrid(ctx: GridCtx) {
  const { workspaceId, inningsId, canManage, nameOf, onPersonLoaded, onDirty, onChanged } = ctx;
  const { rows, refresh } = useRows<Partnership>(() => api.listPartnerships(workspaceId, inningsId), onDirty, ctx.refreshKey);
  const batters = useInningsBatters(workspaceId, inningsId, nameOf, ctx.refreshKey);

  const commit = async (id: string, body: Record<string, unknown>) => {
    try {
      await api.updatePartnership(workspaceId, inningsId, id, body);
      await refresh(); // re-read so partnership players and end-reason show the saved value
      onChanged();
    } catch (e) {
      onDirty(e instanceof ApiError ? e.message : "Save failed");
    }
  };
  const remove = async (id: string) => { await api.deletePartnership(workspaceId, inningsId, id); await refresh(); onChanged(); };
  const originBadge = (o: string) =>
    o === "calculated" ? <Badge variant="brand">Auto</Badge>
      : o === "verified" ? <Badge variant="success">Verified</Badge>
        : o === "manual" ? <Badge variant="muted">Manual</Badge>
          : <Badge variant="outline">?</Badge>;

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[720px] border-collapse text-sm">
        <thead>
          <tr className="text-left text-xs uppercase text-muted-foreground">
            <th className="px-1 py-1">Wkt</th>
            <th className="px-1 py-1">Runs</th>
            <th className="px-1 py-1">Batter 1</th>
            <th className="px-1 py-1">Batter 2</th>
            <th className="px-1 py-1">Ended</th>
            <th className="px-1 py-1 text-center">Unbroken</th>
            <th className="px-1 py-1">Source</th>
            {canManage && <th className="w-8" />}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.id} className="border-t border-border">
              <td className="px-1 py-1"><NumCell value={r.wicket_number} ariaLabel={`Partnership wicket ${i + 1}`} disabled={!canManage} width="w-12" onCommit={(v) => void commit(r.id, { wicket_number: v })} /></td>
              <td className="px-1 py-1"><NumCell value={r.runs} ariaLabel={`Partnership runs ${i + 1}`} disabled={!canManage} onCommit={(v) => void commit(r.id, { runs: v })} /></td>
              <td className="min-w-[150px] px-1 py-1">
                <PlayerSelect workspaceId={workspaceId} value={r.player1_person_id} nameOf={nameOf} onPersonLoaded={onPersonLoaded}
                  disabled={!canManage} aria-label={`Partnership ${i + 1} batter 1`} priorityPeople={batters}
                  onChange={(pid) => void commit(r.id, { player1_person_id: pid })} />
              </td>
              <td className="min-w-[150px] px-1 py-1">
                <PlayerSelect workspaceId={workspaceId} value={r.player2_person_id} nameOf={nameOf} onPersonLoaded={onPersonLoaded}
                  disabled={!canManage} aria-label={`Partnership ${i + 1} batter 2`} priorityPeople={batters}
                  onChange={(pid) => void commit(r.id, { player2_person_id: pid })} />
              </td>
              <td className="px-1 py-1">
                <Select aria-label={`Partnership ended ${i + 1}`} disabled={!canManage} value={r.end_reason ?? ""}
                  onChange={(e) => void commit(r.id, { end_reason: e.target.value || null })} className="h-8 w-32">
                  <option value="">— unknown —</option>
                  {PARTNERSHIP_END_REASONS.map((x) => <option key={x} value={x}>{x.replace(/_/g, " ")}</option>)}
                </Select>
              </td>
              <td className="px-1 py-1 text-center">
                <input type="checkbox" aria-label={`Partnership ${i + 1} unbroken`} disabled={!canManage}
                  checked={r.unbroken === true}
                  onChange={(e) => void commit(r.id, { unbroken: e.target.checked })}
                  className="h-4 w-4 focus-visible:outline-2 focus-visible:outline-[var(--ring)]" />
              </td>
              <td className="px-1 py-1">{originBadge(r.origin)}</td>
              {canManage && (
                <td className="px-1 py-1">
                  <button aria-label={`Remove partnership ${i + 1}`} onClick={() => void remove(r.id)}
                    className="rounded-[var(--radius-app)] p-1 text-muted-foreground hover:bg-muted hover:text-danger">
                    <Trash2 className="h-3.5 w-3.5" aria-hidden />
                  </button>
                </td>
              )}
            </tr>
          ))}
          {rows.length === 0 && (
            <tr><td colSpan={8} className="px-1 py-3 text-sm text-muted-foreground">No partnerships yet. They generate automatically once Fall of Wickets (with team scores) are entered.</td></tr>
          )}
        </tbody>
      </table>
      <p className="mt-2 text-xs text-muted-foreground">
        <Badge variant="brand">Auto</Badge> partnerships are calculated automatically from Fall of Wickets (runs include extras) whenever the FOW or batting order changes;
        <Badge variant="muted">Manual</Badge>/<Badge variant="success">Verified</Badge> entries are preserved and stay editable.
      </p>
    </div>
  );
}

/**
 * Additional run-out fielders (R-3). The primary fielder is set in the cell above; this manages the
 * OTHER involved fielders for a run-out (e.g. the thrower), credited as run-out assists. Changes are
 * saved immediately and the parent recomputes stats.
 */
function RunOutAssists({ ctx, entryId, primaryId }: { ctx: GridCtx; entryId: string; primaryId: string }) {
  const { workspaceId, inningsId, canManage, nameOf, onPersonLoaded, onChanged } = ctx;
  const [fielders, setFielders] = useState<DismissalFielder[]>([]);
  const [adding, setAdding] = useState(false);

  useEffect(() => {
    let live = true;
    void api.getRunOutFielders(workspaceId, inningsId, entryId)
      .then((f) => { if (live) setFielders(f); })
      .catch(() => { /* a fresh entry may have none yet */ });
    return () => { live = false; };
  }, [workspaceId, inningsId, entryId]);

  const save = async (ids: { person_id: string; role?: string }[]) => {
    try {
      setFielders(await api.setRunOutFielders(workspaceId, inningsId, entryId, ids));
      onChanged();
    } catch { /* surfaced by the parent's own error handling on next load */ }
  };
  const add = (pid: string | null) => {
    setAdding(false);
    if (!pid || pid === primaryId || fielders.some((f) => f.person_id === pid)) return;
    void save([...fielders.map((f) => ({ person_id: f.person_id, role: f.role })), { person_id: pid, role: "assist" }]);
  };
  const remove = (pid: string) =>
    void save(fielders.filter((f) => f.person_id !== pid).map((f) => ({ person_id: f.person_id, role: f.role })));

  return (
    <div className="mt-1 flex flex-col gap-1">
      {fielders.length > 0 && (
        <div className="flex flex-wrap items-center gap-1">
          <span className="text-[11px] text-muted-foreground">assisted by</span>
          {fielders.map((f) => (
            <Badge key={f.id} variant="outline" className="gap-1">
              {nameOf(f.person_id) ?? "Unknown"}
              {canManage && (
                <button type="button" aria-label={`Remove assisting fielder ${nameOf(f.person_id) ?? ""}`}
                  className="text-muted-foreground hover:text-danger" onClick={() => remove(f.person_id)}>×</button>
              )}
            </Badge>
          ))}
        </div>
      )}
      {canManage && (adding ? (
        <PlayerSelect workspaceId={workspaceId} value={null} nameOf={nameOf} onPersonLoaded={onPersonLoaded}
          aria-label="Add assisting fielder" organisationId={ctx.bowlingOrgId} scopeLabel={ctx.bowlingTeamName}
          onChange={add} />
      ) : (
        <button type="button" className="self-start text-[11px] text-brand hover:underline"
          onClick={() => setAdding(true)}>+ add fielder</button>
      ))}
    </div>
  );
}
