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

/** Whether the Bowler selector should be shown for a batting row. Shown only for dismissals that credit
 *  a bowler (BOWLER_CREDIT); hidden for not out, retired, run out, dnb/absent and other non-bowler
 *  outcomes — but always shown when a bowler is already recorded, so existing data is never hidden. */
export function bowlerApplies(dismissalType: string | null | undefined, hasBowler = false): boolean {
  if (hasBowler) return true;
  return BOWLER_CREDIT.has(dismissalType ?? "");
}
/** Dismissals that involve a fielder, so the Fielder box is relevant: catches, stumpings and run-outs.
 *  caught_and_bowled credits the bowler as the catcher, so it needs no separate fielder. Bowled, lbw
 *  and hit wicket are the bowler's alone. */
export const FIELDER_DISMISSALS = new Set([
  "caught", "caught_behind", "stumped", "run_out",
]);

/** Whether the Fielder selector should be shown for a batting row. Hidden for bowler-only dismissals
 *  (bowled, lbw, hit wicket, caught & bowled) and other non-fielding outcomes — but always shown when
 *  a fielder is already recorded, so existing data is never hidden behind the rule. */
export function fielderApplies(dismissalType: string | null | undefined, hasFielder = false): boolean {
  if (hasFielder) return true;
  return FIELDER_DISMISSALS.has(dismissalType ?? "");
}

/** Positions opened ready for input on a fresh batting card — a full XI. Extras can be added and
 *  unused ones removed; an empty row is simply a position with everything still unknown. */
export const DEFAULT_BATTING_SLOTS = 11;

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

/**
 * Immediate, per-row Fall-of-Wickets advisories, driving a subtle inline highlight as well as the
 * advisory list — no server round-trip. Rows arrive ordered by wicket number. Advisory only: an
 * incomplete or odd historical card still saves. Nothing is inferred and no value is changed.
 */
export interface FowRowLike {
  id: string;
  wicket_number: number | null;
  team_score: number | null;
}
export interface FowIssues {
  /** rows whose team score is lower than an earlier wicket's (Law 18 — the total only rises). */
  decreasingScoreIds: Set<string>;
  /** rows that repeat a wicket number already used in this innings. */
  duplicateWicketIds: Set<string>;
  messages: AdvisoryWarning[];
}
export function fowIssues(rows: FowRowLike[]): FowIssues {
  const decreasingScoreIds = new Set<string>();
  const duplicateWicketIds = new Set<string>();
  let prevScore: number | null = null;
  for (const r of rows) {
    if (r.team_score === null) continue;
    if (prevScore !== null && r.team_score < prevScore) decreasingScoreIds.add(r.id);
    prevScore = r.team_score;
  }
  const firstForWicket = new Map<number, string>();
  for (const r of rows) {
    if (r.wicket_number === null) continue;
    const first = firstForWicket.get(r.wicket_number);
    if (first !== undefined) { duplicateWicketIds.add(r.id); duplicateWicketIds.add(first); }
    else firstForWicket.set(r.wicket_number, r.id);
  }
  const messages: AdvisoryWarning[] = [];
  if (decreasingScoreIds.size > 0)
    messages.push({ code: "fow_scores_not_increasing", message: "A fall-of-wicket score is lower than an earlier wicket — the team total only rises." });
  if (duplicateWicketIds.size > 0)
    messages.push({ code: "fow_duplicate_wicket", message: "Two falls of wicket share the same wicket number." });
  return { decreasingScoreIds, duplicateWicketIds, messages };
}

/**
 * Immediate, per-row batting-order advisories (inline highlight + list). The card is shown in
 * batting-position order, so a batter is "out of order" when their position repeats or is not
 * greater than a preceding batter's. Advisory only; never blocks saving and changes nothing.
 */
export interface BattingOrderRowLike {
  id: string;
  batting_position: number | null;
  person_id: string | null;
}
export interface BattingOrderIssues {
  outOfOrderIds: Set<string>;
  duplicatePersonIds: Set<string>;
  messages: AdvisoryWarning[];
}
export function battingOrderIssues(rows: BattingOrderRowLike[]): BattingOrderIssues {
  const outOfOrderIds = new Set<string>();
  let prev: number | null = null;
  for (const r of rows) {
    if (r.batting_position === null) continue;
    if (prev !== null && r.batting_position <= prev) outOfOrderIds.add(r.id);
    prev = r.batting_position;
  }
  const duplicatePersonIds = new Set<string>();
  const firstForPerson = new Map<string, string>();
  for (const r of rows) {
    if (r.person_id === null) continue;
    const first = firstForPerson.get(r.person_id);
    if (first !== undefined) { duplicatePersonIds.add(r.id); duplicatePersonIds.add(first); }
    else firstForPerson.set(r.person_id, r.id);
  }
  const messages: AdvisoryWarning[] = [];
  if (outOfOrderIds.size > 0)
    messages.push({ code: "batting_order_out_of_sequence", message: "A batter's position is out of order (positions should increase down the card)." });
  if (duplicatePersonIds.size > 0)
    messages.push({ code: "duplicate_batter", message: "A player appears more than once in this batting innings." });
  return { outOfOrderIds, duplicatePersonIds, messages };
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

// ---- score display (Phase 7.7) ---------------------------------------------------------------
export type ScoreFormat = "au" | "en";

/**
 * Format an innings score for display. DISPLAY ONLY — runs and wickets are stored separately and
 * are never altered by the chosen format. Australian shows wickets/runs (10/127); English shows
 * runs/wickets (127/10). An unknown total stays "—"; an unknown wicket count shows "?"; a declared
 * innings is suffixed "dec". Supports fewer than, or (in special formats) more than, ten wickets.
 */
export function formatScore(
  runs: number | null | undefined,
  wickets: number | null | undefined,
  opts: { format: ScoreFormat; declared?: boolean } = { format: "au" },
): string {
  if (runs === null || runs === undefined) return "—";
  const w = wickets === null || wickets === undefined ? "?" : String(wickets);
  const pair = opts.format === "en" ? `${runs}/${w}` : `${w}/${runs}`;
  return opts.declared ? `${pair} dec` : pair;
}

/** All out / declared / in-progress label for a score where known, else null. */
export function scoreStatusLabel(
  wickets: number | null | undefined, status: string | null | undefined, maxWickets = 10,
): string | null {
  if (status === "declared") return "Declared";
  if (status === "forfeited") return "Forfeited";
  if (wickets != null && wickets >= maxWickets) return "All out";
  if (status === "completed" || status === "closed") return "Completed";
  if (status === "in_progress") return "In progress";
  return null;
}
