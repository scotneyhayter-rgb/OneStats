/**
 * Pure scorecard logic shared by the Stage 7 editor components (no React, no DOM — unit-tested).
 *
 * Everything here keeps the Phase 6 invariants the backend also enforces: unknown is never zero,
 * nothing is invented, and figures are classified so the UI can visually distinguish recorded,
 * calculated, unknown, conflicting and verified information. The backend remains the authority;
 * these helpers drive immediate in-grid feedback and the draft/keyboard behaviour.
 */

// Canonical vocabularies (mirror the backend domain modules).
export const DISMISSAL_TYPES = [
  "dnb", "absent", "not_out", "retired_not_out",
  "bowled", "caught", "caught_behind", "caught_and_bowled", "lbw",
  "stumped", "hit_wicket",
  "run_out", "retired_out", "obstructing", "hit_twice", "timed_out",
  "unknown_out", "retired", "unknown",
] as const;
export type DismissalType = (typeof DISMISSAL_TYPES)[number];

/** Dismissal statuses that do NOT count as a wicket (fall). Mirrors backend NON_WICKET_STATUSES. */
export const NON_WICKET_STATUSES = new Set([
  "dnb", "absent", "not_out", "retired_not_out", "retired", "unknown",
]);
/** Dismissals that credit a bowler. Mirrors backend BOWLER_CREDIT. */
export const BOWLER_CREDIT = new Set([
  "bowled", "caught", "caught_behind", "caught_and_bowled", "lbw", "stumped", "hit_wicket",
]);
export const INNINGS_STATUSES = [
  "in_progress", "completed", "declared", "closed", "forfeited", "incomplete", "unknown",
] as const;
export const PARTNERSHIP_END_REASONS = [
  "wicket", "retired", "declared", "forfeited", "innings_closed", "unknown",
] as const;

/**
 * How a single value should be shown. Keeps unknown distinct from zero and surfaces a conflict
 * between a recorded figure and the one calculated from underlying data.
 */
export type ValueState = "recorded" | "calculated" | "unknown" | "conflicting" | "verified";

export function valueState(opts: {
  recorded?: number | null;
  calculated?: number | null;
  verified?: boolean;
}): ValueState {
  const { recorded, calculated, verified } = opts;
  const hasRec = recorded !== null && recorded !== undefined;
  const hasCalc = calculated !== null && calculated !== undefined;
  if (hasRec && hasCalc && recorded !== calculated) return "conflicting";
  if (hasRec && verified) return "verified";
  if (hasRec) return "recorded";
  if (hasCalc) return "calculated";
  return "unknown";
}

/**
 * Parse a numeric field. Empty/whitespace → null (UNKNOWN, never 0); "0" → 0 (a real zero);
 * anything non-numeric or negative → null. This is the rule that keeps unknown ≠ zero at input.
 */
export function parseIntOrNull(raw: string): number | null {
  const s = (raw ?? "").trim();
  if (s === "") return null;
  if (!/^\d+$/.test(s)) return null;
  return Number.parseInt(s, 10);
}

/** Display a number that may be unknown. null/undefined → "—" (unknown), 0 stays "0". */
export function showNum(v: number | null | undefined): string {
  return v === null || v === undefined ? "—" : String(v);
}

/** Sum only the KNOWN values; null if none are known (so an all-blank line is unknown, not 0). */
export function sumKnown(values: (number | null | undefined)[]): number | null {
  const known = values.filter((v): v is number => v !== null && v !== undefined);
  return known.length ? known.reduce((a, b) => a + b, 0) : null;
}

export interface ExtrasLike {
  byes: number | null;
  legbyes: number | null;
  wides: number | null;
  noballs: number | null;
  penalty: number | null;
}
export function extrasTotal(e: ExtrasLike): number | null {
  return sumKnown([e.byes, e.legbyes, e.wides, e.noballs, e.penalty]);
}

export interface BattingLike {
  person_id: string | null;
  batting_position: number | null;
  runs: number | null;
  dismissal_type: string | null;
}
/** Batters' runs only (excludes extras); unknown if no runs recorded. */
export function battingRunsTotal(rows: BattingLike[]): number | null {
  return sumKnown(rows.map((r) => r.runs));
}
/** Genuine dismissals (wickets). unknown_out counts; not-out/dnb/absent/unresolved do not. */
export function wicketCount(rows: BattingLike[]): number {
  return rows.filter((r) => r.dismissal_type !== null && !NON_WICKET_STATUSES.has(r.dismissal_type ?? "")).length;
}
/** Derived innings total = batting runs + extras; unknown while batting runs are unknown. */
export function derivedInningsTotal(battingRuns: number | null, extras: number | null): number | null {
  if (battingRuns === null) return null;
  return battingRuns + (extras ?? 0);
}

export interface BowlingLike {
  person_id: string | null;
  wickets: number | null;
  runs_conceded: number | null;
}
/** Wickets clearly credited to bowlers from the batting card (bowler-credit + a named bowler). */
export function creditedBowlerWickets(batting: { dismissal_type: string | null; bowler_person_id: string | null }[]): number {
  return batting.filter((b) => b.bowler_person_id !== null && BOWLER_CREDIT.has(b.dismissal_type ?? "")).length;
}

export interface AdvisoryWarning {
  code: string;
  message: string;
}

/**
 * Immediate, non-blocking advisory warnings for one innings, shown in-grid before the authoritative
 * backend /validate call. Covers the Stage 7 categories: innings-total and extras discrepancies,
 * wicket-count and bowling/dismissal discrepancies, duplicate batting entries, and
 * unusual/incomplete scorecards. Never blocks saving.
 */
export function inningsAdvisories(input: {
  batting: (BattingLike & { bowler_person_id: string | null })[];
  bowling: BowlingLike[];
  extras: ExtrasLike;
  officialTotal: number | null;
  officialWickets: number | null;
}): AdvisoryWarning[] {
  const out: AdvisoryWarning[] = [];
  const { batting, bowling, extras, officialTotal, officialWickets } = input;

  // duplicate batting entries (same player, or same position) — advisory here, hard-guarded by the DB
  const seenPos = new Set<number>();
  const seenPerson = new Set<string>();
  let dupPos = false;
  let dupPerson = false;
  for (const b of batting) {
    if (b.batting_position !== null) {
      if (seenPos.has(b.batting_position)) dupPos = true;
      seenPos.add(b.batting_position);
    }
    if (b.person_id !== null) {
      if (seenPerson.has(b.person_id)) dupPerson = true;
      seenPerson.add(b.person_id);
    }
  }
  if (dupPos) out.push({ code: "duplicate_batting_position", message: "Two batters share a batting position." });
  if (dupPerson) out.push({ code: "duplicate_batter", message: "A player appears more than once in this batting innings." });

  const wkts = wicketCount(batting);
  if (wkts > 10) out.push({ code: "more_than_10_wickets", message: `Batting card shows ${wkts} dismissals (more than 10).` });

  const extrasT = extrasTotal(extras);
  if (officialTotal !== null && extrasT !== null && officialTotal < extrasT) {
    out.push({ code: "official_total_less_than_extras", message: "Official innings total is less than the recorded extras." });
  }

  const derived = derivedInningsTotal(battingRunsTotal(batting), extrasT);
  if (derived !== null && officialTotal !== null && derived !== officialTotal) {
    out.push({ code: "derived_total_differs_from_official", message: `Calculated total (${derived}) differs from the official total (${officialTotal}).` });
  }

  // bowling wickets vs clearly-credited dismissals
  const recordedBowlerWkts = sumKnown(bowling.map((b) => b.wickets));
  const credited = creditedBowlerWickets(batting);
  if (recordedBowlerWkts !== null && credited > 0 && recordedBowlerWkts !== credited) {
    out.push({ code: "bowling_wickets_differ_from_dismissals", message: `Bowlers' recorded wickets (${recordedBowlerWkts}) differ from clearly-credited dismissals (${credited}).` });
  }

  // official wickets vs batting card
  if (officialWickets !== null && wkts > 0 && officialWickets !== wkts) {
    out.push({ code: "official_wickets_differ_from_card", message: `Official wickets (${officialWickets}) differ from the batting card (${wkts}).` });
  }
  return out;
}

// ---- keyboard navigation (spreadsheet-style grids) -------------------------------------------

export interface GridPos {
  row: number;
  col: number;
}
/**
 * Next cell for a keyboard move within an rows×cols grid. Arrow keys clamp at edges; Enter moves
 * down; Tab/Shift+Tab flow across then wrap to the next/previous row (stopping at the grid edge).
 * Pure and fully testable — the components bind this to onKeyDown.
 */
export function nextCell(
  pos: GridPos,
  key: "ArrowUp" | "ArrowDown" | "ArrowLeft" | "ArrowRight" | "Enter" | "Tab" | "ShiftTab",
  dims: { rows: number; cols: number },
): GridPos {
  const { rows, cols } = dims;
  const clamp = (r: number, c: number): GridPos => ({
    row: Math.max(0, Math.min(rows - 1, r)),
    col: Math.max(0, Math.min(cols - 1, c)),
  });
  switch (key) {
    case "ArrowUp":
      return clamp(pos.row - 1, pos.col);
    case "ArrowDown":
    case "Enter":
      return clamp(pos.row + 1, pos.col);
    case "ArrowLeft":
      return clamp(pos.row, pos.col - 1);
    case "ArrowRight":
      return clamp(pos.row, pos.col + 1);
    case "Tab": {
      if (pos.col < cols - 1) return { row: pos.row, col: pos.col + 1 };
      if (pos.row < rows - 1) return { row: pos.row + 1, col: 0 };
      return pos; // at the last cell — stay
    }
    case "ShiftTab": {
      if (pos.col > 0) return { row: pos.row, col: pos.col - 1 };
      if (pos.row > 0) return { row: pos.row - 1, col: cols - 1 };
      return pos; // at the first cell — stay
    }
  }
}

// ---- draft persistence (per-viewer convenience; backend status='draft' is authoritative) -----

const DRAFT_PREFIX = "onestats.scorecard.draft";

export function draftKey(workspaceId: string, matchId: string): string {
  return `${DRAFT_PREFIX}:${workspaceId}:${matchId}`;
}

/** Serialise a local draft of unsaved field edits. Pure; the component handles localStorage I/O. */
export function serializeDraft(state: Record<string, unknown>): string {
  return JSON.stringify({ v: 1, savedAt: new Date().toISOString(), state });
}
export function deserializeDraft(raw: string | null): { savedAt: string; state: Record<string, unknown> } | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as { v?: number; savedAt?: string; state?: Record<string, unknown> };
    if (!parsed || parsed.v !== 1 || !parsed.state) return null;
    return { savedAt: parsed.savedAt ?? "", state: parsed.state };
  } catch {
    return null;
  }
}
