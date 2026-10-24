/**
 * Unit tests for the Import Wizard's controlled-slice builder — it must send the backend ONLY the
 * records the selected matches need (clubs/teams/venues/grades referenced, the nested scorecard
 * collections, and the referenced players/officials), so a small approved import never drags in the
 * whole dataset. This is the requirement "import selected matches rather than the entire dataset".
 */
import { describe, expect, it } from "vitest";
import { buildSlice } from "./ImportWizard";

const FILE = {
  clubs: [{ ClubID: 1, Name: "Alpha" }, { ClubID: 2, Name: "Beta" }, { ClubID: 3, Name: "Unused" }],
  teams: [{ TeamID: 100, Name: "Alpha 1", ClubID: 1 }, { TeamID: 200, Name: "Beta 1", ClubID: 2 },
          { TeamID: 300, Name: "Other", ClubID: 3 }],
  venues: [{ GroundID: 10, Name: "Oval" }, { GroundID: 11, Name: "Unused Park" }],
  divisions: [{ GradeID: 50, Name: "A Grade" }, { GradeID: 51, Name: "Unused Grade" }],
  players: [{ PlayerID: 1001 }, { PlayerID: 1002 }, { PlayerID: 1003 }, { PlayerID: 9999 }],
  officials: [{ PlayerID: 7001 }, { PlayerID: 7002 }],
  matches: [
    { MatchID: 500, HomeTeam: 100, AwayTeam: 200, Grade: 50, Ground: 10, official1: 7001 },
    { MatchID: 501, HomeTeam: 300, AwayTeam: 100, Grade: 51, Ground: 11, official1: 7002 },
  ],
  innings: [{ MatchID: 500, cricket_Innings: [{ InningsID: 700, battingteam: 100, bowlingteam: 200 }] }],
  batting: [{ MatchID: 500, cricket_Innings: [{ InningsID: 700, cricket_batting: [
    { Batpos: 1, BatsmanID: 1001, Bowler: 1002, Fielder: 1003 },
    { Batpos: 2, BatsmanID: 0 },  // padding — contributes no person
  ] }] }],
  bowling: [{ MatchID: 500, cricket_Innings: [{ InningsID: 700, cricket_bowling: [{ bowlerID: 1002 }] }] }],
};

describe("buildSlice (controlled import scoping)", () => {
  it("includes only the entities the selected match references", () => {
    const { data } = buildSlice(FILE, new Set([500]));
    expect(data.matches.map((m) => m.MatchID)).toEqual([500]);           // only the selected match
    expect(data.teams.map((t) => t.TeamID).sort()).toEqual([100, 200]);  // its two sides only
    expect(data.clubs.map((c) => c.ClubID).sort()).toEqual([1, 2]);      // only those teams' clubs
    expect(data.venues.map((v) => v.GroundID)).toEqual([10]);            // its venue only
    expect(data.divisions.map((d) => d.GradeID)).toEqual([50]);          // its grade only
    // nested scorecard collections carried for the selected match
    expect(data.innings).toHaveLength(1);
    expect(data.batting).toHaveLength(1);
    expect(data.bowling).toHaveLength(1);
  });

  it("includes only the people referenced by the selected match (padding excluded)", () => {
    const { people } = buildSlice(FILE, new Set([500]));
    expect(people.players.map((p) => p.PlayerID).sort()).toEqual([1001, 1002, 1003]); // not 9999
    expect(people.officials.map((o) => o.PlayerID)).toEqual([7001]);                  // official1 of match 500
  });

  it("scopes differently for a different match (no leakage of unused records)", () => {
    const { data } = buildSlice(FILE, new Set([501]));
    expect(data.teams.map((t) => t.TeamID).sort()).toEqual([100, 300]);
    expect(data.clubs.map((c) => c.ClubID).sort()).toEqual([1, 3]);
    expect(data.innings).toHaveLength(0);  // match 501 has no scorecard in the fixture
  });
});
