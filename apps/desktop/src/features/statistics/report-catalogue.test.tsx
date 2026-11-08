// @vitest-environment jsdom
/** Report Catalogue (Phase 12 expansion): lists categorised reports, searches, opens one in a focused
 *  view, and scopes it to a club (the filter the report declares is passed through to the engine). */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const H = vi.hoisted(() => ({
  statsCatalogue: vi.fn(), statsReport: vi.fn(), statsUsedFormats: vi.fn(),
  listCompetitions: vi.fn(), listOrganisations: vi.fn(), listTeams: vi.fn(), listVenues: vi.fn(),
  statsPrimaryClub: vi.fn(), getCompetition: vi.fn(),
}));

vi.mock("../../lib/workspace-context", () => ({ useWorkspace: () => ({ current: { id: "w1", name: "RMCC" } }) }));
vi.mock("../../lib/api", () => ({ ApiError: class ApiError extends Error {}, api: H }));
vi.mock("../../components/layout/AppShell", () => ({
  AppShell: ({ children }: { children: import("react").ReactNode }) => <div>{children}</div>,
}));

import { ReportCatalogue } from "./ReportCatalogue";

const CAT = {
  count: 3,
  categories: [
    { category: "Batting", reports: [
      { id: "bat_most_runs", name: "Most Runs", category: "Batting", description: "Leading run scorers.",
        filters: ["organisation", "team", "season", "split"], qualification: null, limitations: null, split_default: null, csv: true, pdf: true },
      { id: "bat_highest_average", name: "Highest Batting Average", category: "Batting",
        description: "Best average among qualified batters.", filters: ["season"], qualification: "min 500 runs",
        limitations: null, split_default: null, csv: true, pdf: true },
    ] },
    { category: "Captaincy", reports: [
      { id: "capt_consec_wins", name: "Most Consecutive Wins as Captain", category: "Captaincy",
        description: "Longest run of wins as captain.", filters: ["split"], qualification: null,
        limitations: "Unknown breaks the known sequence.", split_default: null, csv: true, pdf: true },
    ] },
  ],
};

function setup() {
  H.statsCatalogue.mockResolvedValue(CAT);
  H.statsUsedFormats.mockResolvedValue([]);
  H.listCompetitions.mockResolvedValue([]);
  H.listOrganisations.mockResolvedValue([{ id: "o1", name: "Rhymney Moyston CC" }, { id: "o2", name: "Ararat CC" }]);
  H.listTeams.mockResolvedValue([]);
  H.listVenues.mockResolvedValue([]);
  H.statsPrimaryClub.mockResolvedValue({});   // no auto-default club, so the test is deterministic
  H.getCompetition.mockResolvedValue({ grades: [], seasons: [] });
  H.statsReport.mockResolvedValue({ report: "bat_most_runs", title: "Most Runs",
    columns: [{ key: "player", label: "Player", align: "left", decimals: null },
              { key: "runs", label: "Runs", align: "right", decimals: null }],
    rows: [{ player: "A G Steel", runs: 1850 }] });
}

afterEach(() => {
  cleanup();
  Object.values(H).forEach((fn) => fn.mockReset());
  try { localStorage.clear(); } catch { /* jsdom storage */ }   // recent/favourites must not leak between tests
});

describe("ReportCatalogue", () => {
  it("lists categorised reports, searches, and opens one in a focused view", async () => {
    setup();
    render(<ReportCatalogue />);
    await screen.findByText("Most Runs");
    expect(screen.getByText("Most Consecutive Wins as Captain")).toBeTruthy();

    // search filters the list
    fireEvent.change(screen.getByPlaceholderText("Search reports…"), { target: { value: "consecutive" } });
    expect(screen.queryByText("Most Runs")).toBeNull();
    expect(screen.getByText("Most Consecutive Wins as Captain")).toBeTruthy();

    // clear + open a report shows its table in a focused view (the catalogue list is hidden)
    fireEvent.change(screen.getByPlaceholderText("Search reports…"), { target: { value: "" } });
    fireEvent.click(screen.getAllByText("View report")[0]);
    await waitFor(() => expect(screen.getByText("A G Steel")).toBeTruthy());
    expect(screen.getByText("← All reports")).toBeTruthy();
    // focused: the other category's card is no longer listed while a report is open
    expect(screen.queryByText("Most Consecutive Wins as Captain")).toBeNull();
  });

  it("scopes an opened report to a club and passes the filter to the engine", async () => {
    setup();
    render(<ReportCatalogue />);
    await screen.findByText("Most Runs");
    fireEvent.click(screen.getAllByText("View report")[0]);
    await waitFor(() => expect(screen.getByText("A G Steel")).toBeTruthy());

    // The report declares "organisation", so a Club selector is offered.
    const clubSelect = screen.getByText("Club").closest("label")!.querySelector("select")!;
    fireEvent.change(clubSelect, { target: { value: "o1" } });

    await waitFor(() =>
      expect(H.statsReport).toHaveBeenLastCalledWith("w1", "bat_most_runs",
        expect.objectContaining({ organisation_id: "o1" })));
  });
});
