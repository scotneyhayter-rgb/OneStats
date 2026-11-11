// @vitest-environment jsdom
/** Statistics genre tabs: opening a genre lists every report in that genre (not just the default
 *  leaderboard), and picking one loads that report with the current filters. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const H = vi.hoisted(() => ({
  statsReport: vi.fn(), statsCatalogue: vi.fn(), statsSavedList: vi.fn(), statsUsedFormats: vi.fn(),
  statsUsedSeasons: vi.fn(), statsPrimaryClub: vi.fn(), listCompetitions: vi.fn(), listOrganisations: vi.fn(),
  listTeams: vi.fn(), listVenues: vi.fn(), getCompetition: vi.fn(),
}));

const WS = vi.hoisted(() => ({ current: { id: "w1", name: "RMCC" } }));   // stable ref (context is stable in-app)
vi.mock("../../lib/workspace-context", () => ({ useWorkspace: () => WS }));
vi.mock("../../lib/api", () => ({ ApiError: class ApiError extends Error {}, api: H }));
vi.mock("../../components/layout/AppShell", () => ({
  AppShell: ({ children }: { children: import("react").ReactNode }) => <div>{children}</div>,
}));

import { Statistics } from "./Statistics";

const CAT = {
  count: 3,
  categories: [
    { category: "Batting", reports: [
      { id: "bat_most_runs", name: "Most Runs", category: "Batting", description: "Leading run scorers.", filters: ["organisation"], qualification: null, limitations: null, split_default: null, csv: true, pdf: true },
      { id: "bat_highest_average", name: "Highest Batting Average", category: "Batting", description: "Best average.", filters: ["organisation"], qualification: "min 500", limitations: null, split_default: null, csv: true, pdf: true },
    ] },
    { category: "Bowling", reports: [
      { id: "bowl_most_wickets", name: "Most Wickets", category: "Bowling", description: "Leading wicket takers.", filters: ["organisation"], qualification: null, limitations: null, split_default: null, csv: true, pdf: true },
    ] },
  ],
};

function setup() {
  H.statsCatalogue.mockResolvedValue(CAT);
  H.statsSavedList.mockResolvedValue([]);
  H.statsUsedFormats.mockResolvedValue([]);
  H.statsUsedSeasons.mockResolvedValue([]);
  H.statsPrimaryClub.mockResolvedValue({});
  H.listCompetitions.mockResolvedValue([]);
  H.listOrganisations.mockResolvedValue([]);
  H.listTeams.mockResolvedValue([]);
  H.listVenues.mockResolvedValue([]);
  H.getCompetition.mockResolvedValue({ grades: [], seasons: [] });
  H.statsReport.mockResolvedValue({ report: "bat_most_runs", title: "Batting — Leading Run Scorers",
    columns: [{ key: "player", label: "Player", align: "left", decimals: null }],
    rows: [{ player: "A G Steel" }] });
}

afterEach(() => { cleanup(); Object.values(H).forEach((fn) => fn.mockReset()); });

describe("Statistics genre reports", () => {
  it("lists all reports in the open genre and loads the one picked", async () => {
    setup();
    render(<Statistics />);
    // The Batting genre now surfaces every batting report, not just the default leaderboard.
    await screen.findByText("Most Runs");
    expect(screen.getByText("Highest Batting Average")).toBeTruthy();

    // Picking a report loads that specific report id.
    fireEvent.click(screen.getByText("Highest Batting Average"));
    await waitFor(() => expect(H.statsReport).toHaveBeenLastCalledWith("w1", "bat_highest_average", expect.anything()));
  });
});
