import { describe, expect, it } from "vitest";
import {
  battingRunsTotal,
  creditedBowlerWickets,
  derivedInningsTotal,
  deserializeDraft,
  draftKey,
  extrasTotal,
  inningsAdvisories,
  nextCell,
  parseIntOrNull,
  serializeDraft,
  showNum,
  sumKnown,
  valueState,
  wicketCount,
} from "./scorecard-logic";

describe("unknown vs zero", () => {
  it("treats blank as unknown (null) and '0' as a real zero", () => {
    expect(parseIntOrNull("")).toBeNull();
    expect(parseIntOrNull("   ")).toBeNull();
    expect(parseIntOrNull("0")).toBe(0);
    expect(parseIntOrNull("42")).toBe(42);
    expect(parseIntOrNull("-3")).toBeNull();
    expect(parseIntOrNull("x")).toBeNull();
  });
  it("shows unknown as em dash, zero as 0", () => {
    expect(showNum(null)).toBe("—");
    expect(showNum(undefined)).toBe("—");
    expect(showNum(0)).toBe("0");
  });
  it("sumKnown ignores unknowns and returns null when nothing known", () => {
    expect(sumKnown([null, undefined])).toBeNull();
    expect(sumKnown([4, null, 2])).toBe(6);
    expect(sumKnown([0])).toBe(0);
  });
});

describe("value state classification", () => {
  it("distinguishes recorded / calculated / unknown / conflicting / verified", () => {
    expect(valueState({ recorded: null, calculated: null })).toBe("unknown");
    expect(valueState({ recorded: 10 })).toBe("recorded");
    expect(valueState({ calculated: 10 })).toBe("calculated");
    expect(valueState({ recorded: 10, verified: true })).toBe("verified");
    expect(valueState({ recorded: 10, calculated: 12 })).toBe("conflicting");
    expect(valueState({ recorded: 10, calculated: 10 })).toBe("recorded");
  });
});

describe("totals (unknown-aware)", () => {
  it("extras total sums known, null if none", () => {
    expect(extrasTotal({ byes: 4, legbyes: 2, wides: null, noballs: null, penalty: null })).toBe(6);
    expect(extrasTotal({ byes: null, legbyes: null, wides: null, noballs: null, penalty: null })).toBeNull();
  });
  it("batting runs unknown until some recorded; derived total unknown while batting unknown", () => {
    expect(battingRunsTotal([{ person_id: null, batting_position: 1, runs: null, dismissal_type: "caught" }])).toBeNull();
    expect(derivedInningsTotal(null, 6)).toBeNull();
    expect(derivedInningsTotal(100, 6)).toBe(106);
    expect(derivedInningsTotal(100, null)).toBe(100);
  });
  it("counts genuine wickets (unknown_out counts; not_out/dnb/retired-not-out do not)", () => {
    const rows = [
      { person_id: "a", batting_position: 1, runs: 10, dismissal_type: "bowled" },
      { person_id: "b", batting_position: 2, runs: 50, dismissal_type: "not_out" },
      { person_id: "c", batting_position: 3, runs: null, dismissal_type: "dnb" },
      { person_id: "d", batting_position: 4, runs: 0, dismissal_type: "unknown_out" },
    ];
    expect(wicketCount(rows)).toBe(2);
  });
  it("credits bowler wickets only for bowler-credit modes with a named bowler", () => {
    const batting = [
      { dismissal_type: "caught", bowler_person_id: "x" },
      { dismissal_type: "run_out", bowler_person_id: "y" }, // run out never credits a bowler
      { dismissal_type: "lbw", bowler_person_id: null }, // ambiguous: no bowler named
    ];
    expect(creditedBowlerWickets(batting)).toBe(1);
  });
});

describe("advisory warnings (non-blocking)", () => {
  it("flags duplicates, discrepancies and wicket-count issues without throwing", () => {
    const w = inningsAdvisories({
      batting: [
        { person_id: "a", batting_position: 1, runs: 20, dismissal_type: "caught", bowler_person_id: "bowl" },
        { person_id: "a", batting_position: 1, runs: 10, dismissal_type: "bowled", bowler_person_id: "bowl" },
      ],
      bowling: [{ person_id: "bowl", wickets: 5, runs_conceded: 30 }],
      extras: { byes: 50, legbyes: null, wides: null, noballs: null, penalty: null },
      officialTotal: 10,
      officialWickets: 9,
    });
    const codes = w.map((x) => x.code);
    expect(codes).toContain("duplicate_batting_position");
    expect(codes).toContain("duplicate_batter");
    expect(codes).toContain("official_total_less_than_extras");
    expect(codes).toContain("bowling_wickets_differ_from_dismissals");
    // every warning has a human-readable message
    for (const x of w) expect(x.message.length).toBeGreaterThan(0);
  });
  it("is clean for a consistent incomplete card (unknowns tolerated)", () => {
    const w = inningsAdvisories({
      batting: [{ person_id: "a", batting_position: 1, runs: null, dismissal_type: "caught", bowler_person_id: null }],
      bowling: [],
      extras: { byes: null, legbyes: null, wides: null, noballs: null, penalty: null },
      officialTotal: null,
      officialWickets: null,
    });
    expect(w).toEqual([]);
  });
});

describe("keyboard navigation", () => {
  const dims = { rows: 3, cols: 4 };
  it("moves with arrows and clamps at edges", () => {
    expect(nextCell({ row: 1, col: 1 }, "ArrowUp", dims)).toEqual({ row: 0, col: 1 });
    expect(nextCell({ row: 0, col: 1 }, "ArrowUp", dims)).toEqual({ row: 0, col: 1 });
    expect(nextCell({ row: 2, col: 3 }, "ArrowDown", dims)).toEqual({ row: 2, col: 3 });
    expect(nextCell({ row: 0, col: 0 }, "ArrowLeft", dims)).toEqual({ row: 0, col: 0 });
    expect(nextCell({ row: 0, col: 3 }, "ArrowRight", dims)).toEqual({ row: 0, col: 3 });
  });
  it("Enter moves down; Tab flows across then wraps; Shift+Tab reverses", () => {
    expect(nextCell({ row: 0, col: 0 }, "Enter", dims)).toEqual({ row: 1, col: 0 });
    expect(nextCell({ row: 0, col: 3 }, "Tab", dims)).toEqual({ row: 1, col: 0 });
    expect(nextCell({ row: 2, col: 3 }, "Tab", dims)).toEqual({ row: 2, col: 3 }); // last cell stays
    expect(nextCell({ row: 1, col: 0 }, "ShiftTab", dims)).toEqual({ row: 0, col: 3 });
    expect(nextCell({ row: 0, col: 0 }, "ShiftTab", dims)).toEqual({ row: 0, col: 0 }); // first cell stays
  });
});

describe("draft persistence", () => {
  it("builds a stable per-match key", () => {
    expect(draftKey("w1", "m1")).toBe("onestats.scorecard.draft:w1:m1");
  });
  it("round-trips a draft and rejects junk", () => {
    const raw = serializeDraft({ notes: "partial card from The Argus" });
    const back = deserializeDraft(raw);
    expect(back?.state.notes).toBe("partial card from The Argus");
    expect(back?.savedAt).toBeTruthy();
    expect(deserializeDraft(null)).toBeNull();
    expect(deserializeDraft("not json")).toBeNull();
    expect(deserializeDraft(JSON.stringify({ v: 99 }))).toBeNull();
  });
});
