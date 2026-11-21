import { describe, expect, it } from "vitest";
import { matchScorecardPath, rowMatchId } from "./utils";

describe("rowMatchId", () => {
  it("returns the match id for a match-level report row", () => {
    expect(rowMatchId({ player: "A", figures: "5-20", match_id: "abc-123" })).toBe("abc-123");
  });

  it("returns null for aggregate/career rows that carry no match_id", () => {
    expect(rowMatchId({ player: "A", wickets: 300 })).toBeNull();
  });

  it("treats an empty or non-string match_id as not clickable", () => {
    expect(rowMatchId({ match_id: "" })).toBeNull();
    expect(rowMatchId({ match_id: null })).toBeNull();
    expect(rowMatchId({ match_id: 42 })).toBeNull();
  });
});

describe("matchScorecardPath", () => {
  it("builds the Matches deep-link that opens a scorecard", () => {
    expect(matchScorecardPath("abc-123")).toBe("/matches?open=abc-123");
  });

  it("url-encodes the match id", () => {
    expect(matchScorecardPath("a b/c")).toBe("/matches?open=a%20b%2Fc");
  });
});
