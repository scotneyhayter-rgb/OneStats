// @vitest-environment jsdom
/** Report Catalogue (Phase 12 expansion): lists categorised reports, searches, and opens a report. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const H = vi.hoisted(() => ({ statsCatalogue: vi.fn(), statsReport: vi.fn() }));

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
        filters: ["season", "split"], qualification: null, limitations: null, split_default: null, csv: true, pdf: true },
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

afterEach(cleanup);

describe("ReportCatalogue", () => {
  it("lists categorised reports, searches, and opens one", async () => {
    H.statsCatalogue.mockResolvedValue(CAT);
    H.statsReport.mockResolvedValue({ report: "bat_most_runs", title: "Most Runs",
      columns: [{ key: "player", label: "Player", align: "left", decimals: null },
                { key: "runs", label: "Runs", align: "right", decimals: null }],
      rows: [{ player: "A G Steel", runs: 1850 }] });

    render(<ReportCatalogue />);
    await screen.findByText("Most Runs");
    expect(screen.getByText("Most Consecutive Wins as Captain")).toBeTruthy();

    // search filters the list
    fireEvent.change(screen.getByPlaceholderText("Search reports…"), { target: { value: "consecutive" } });
    expect(screen.queryByText("Most Runs")).toBeNull();
    expect(screen.getByText("Most Consecutive Wins as Captain")).toBeTruthy();

    // clear + open a report shows its table
    fireEvent.change(screen.getByPlaceholderText("Search reports…"), { target: { value: "" } });
    fireEvent.click(screen.getAllByText("View report")[0]);
    await waitFor(() => expect(screen.getByText("A G Steel")).toBeTruthy());
  });
});
