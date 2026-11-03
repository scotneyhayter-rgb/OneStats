// @vitest-environment jsdom
/** Player Profile (Phase 13): loads the composed profile and shows adaptive career cards. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

const H = vi.hoisted(() => ({
  profileFull: vi.fn(), getProfile: vi.fn(), profileMatches: vi.fn(), personPhotoUrl: vi.fn(), profilePdfUrl: vi.fn(),
}));

vi.mock("../../lib/workspace-context", () => ({ useWorkspace: () => ({ current: { id: "w1", name: "RMCC" } }) }));
vi.mock("../research/ResearchThisButton", () => ({ ResearchThisButton: () => null }));
vi.mock("../../lib/api", () => ({ ApiError: class ApiError extends Error {}, api: H }));
vi.mock("../../components/layout/AppShell", () => ({
  AppShell: ({ children }: { children: import("react").ReactNode }) => <div>{children}</div>,
}));

import { PlayerProfile } from "./PlayerProfile";

const FULL = {
  person_id: "p1",
  career: { matches: 42, batting: { runs: 1850, average: 38.5, highest_score: 134, runs_known_minimum: true,
    innings: 50, not_outs: 2, fifties: 10, hundreds: 3, ducks: 1, fours: 120, sixes: 15, strike_rate: 72.1 },
    bowling: { wickets: 60, average: 22.3 }, fielding: { catches: 25, stumpings: 0, run_outs: 5, keeper_catches: 0, keeper_dismissals: 0 },
    captaincy: { captained: 10, wins: 6 }, derived_role: "all-rounder", has_batting: true, has_bowling: true,
    has_captaincy: true, has_keeping: false },
  seasons: [
    { label: "2023/24", matches: 10, runs: 420, batting_average: 42, wickets: 15, bowling_average: 20, catches: 6, captained: 0 },
    { label: "2024/25", matches: 12, runs: 600, batting_average: 50, wickets: 20, bowling_average: 18, catches: 8, captained: 12 },
  ],
  clubs: [{ team_id: "t1", team: "1st XI", org_id: "o1", club: "Rhymney/Moyston CC" }],
  records: [{ title: "Most Career Runs", value: 1850, tied: false, known_minimum: true }],
  season_leaderships: [{ title: "Leading Run Scorer", season: "2024/25", value: 600 }],
  grand_finals: { appearances: 3, premierships: 2, batting: { runs: 180, average: 60, highest_score: 92 },
    bowling: { wickets: 8 }, fielding: { catches: 3 }, captaincy: { captained: 2, gf_wins: 2 },
    matches: [{ match_date: "2024-03-23", runs: 92, wickets: 2, catches: 1, result_type: "home_win" }],
    has_batting: true, has_bowling: true, has_captaincy: true },
  milestones: { metrics: { runs: { label: "Career runs", total: 1850, known_minimum: true,
    milestones: [{ threshold: 1000, state: "achieved_known_minimum" }], next: { threshold: 2500, to_go: 650 } } } },
  badges: { calculated: [{ label: "1000 career runs", source: "calculated", state: "achieved_known_minimum" }], awarded: [] },
  honours: [{ honour_type: "life_member", title: "Life Member", award_category: null, awarded_season: "2020/21" }],
};

afterEach(cleanup);

describe("PlayerProfile", () => {
  it("shows the player, role, record-holder badge and adaptive cards", async () => {
    H.profileFull.mockResolvedValue(FULL);
    H.getProfile.mockResolvedValue({ person: { display_name: "A G Steel" }, photos: [] });
    render(<MemoryRouter initialEntries={["/people/p1"]}>
      <Routes><Route path="/people/:personId" element={<PlayerProfile />} /></Routes>
    </MemoryRouter>);
    await screen.findByText("A G Steel");
    expect(screen.getByText("All-rounder")).toBeTruthy();   // derived role is title-cased for display
    expect(screen.getAllByText(/Most Career Runs/).length).toBeGreaterThan(0);   // specific record as a top badge
    expect(screen.getByText(/Leading Run Scorer 2024\/25/)).toBeTruthy();   // season leadership badge
    expect(screen.getByText("2× premierships")).toBeTruthy();
    expect(screen.getAllByText("1,850".replace(",", "") === "1850" ? "1850" : "1850").length).toBeGreaterThan(0);
    // known-minimum indicator present on runs
    expect(screen.getAllByText("min.").length).toBeGreaterThan(0);
  });

  it("renders career charts on the Seasons tab and the Grand Finals section", async () => {
    H.profileFull.mockResolvedValue(FULL);
    H.getProfile.mockResolvedValue({ person: { display_name: "A G Steel" }, photos: [] });
    render(<MemoryRouter initialEntries={["/people/p1"]}>
      <Routes><Route path="/people/:personId" element={<PlayerProfile />} /></Routes>
    </MemoryRouter>);
    await screen.findByText("A G Steel");

    fireEvent.click(screen.getByText("Seasons"));
    // graphical career charts (>1 season) render as accessible SVG figures
    expect(screen.getByText("Runs per season")).toBeTruthy();
    expect(screen.getByText("Batting average by season")).toBeTruthy();
    expect(screen.getByText("Cumulative runs")).toBeTruthy();

    fireEvent.click(screen.getByText("Grand Finals"));
    expect(screen.getByText("Premierships")).toBeTruthy();
    expect(screen.getByText(/recorded result, never inferred/)).toBeTruthy();
  });
});
