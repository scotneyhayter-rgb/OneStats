// @vitest-environment jsdom
/**
 * International Statistics page: resolves player names, renders a per-format leaderboard with the
 * engine's honesty flags (known-minimum runs shown as ≥, incomplete strike rate flagged *), switches
 * format/discipline, and shows an honest empty state when a format has no approved scorecards.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

const H = vi.hoisted(() => ({ intlLeaders: vi.fn(), listPeople: vi.fn() }));

vi.mock("../../lib/api", () => ({ ApiError: class ApiError extends Error {}, api: H }));
vi.mock("../../lib/workspace-context", () => ({
  useWorkspace: () => ({ current: { id: "w1", name: "International Men's Cricket", type: "international" } }),
}));
vi.mock("../../components/layout/AppShell", () => ({
  AppShell: ({ children }: { children: import("react").ReactNode }) => <div>{children}</div>,
}));

import { InternationalStats } from "./InternationalStats";

const PEOPLE = [{ id: "p1", display_name: "A Opener" }, { id: "p2", display_name: "B Seamer" }];
const TEST_BATTING = [
  { subject_id: "p1", matches: 50, innings: 90, runs: 4000, highest_score: 180, average: 48.1,
    strike_rate: 55.2, hundreds: 12, fifties: 20, ducks: 3, runs_known_minimum: true, balls_incomplete: true },
];

afterEach(cleanup);

describe("International Statistics page", () => {
  it("renders a format leaderboard with names and honesty flags", async () => {
    H.listPeople.mockResolvedValue(PEOPLE);
    H.intlLeaders.mockResolvedValue(TEST_BATTING);
    render(<MemoryRouter><InternationalStats /></MemoryRouter>);
    await screen.findByText("A Opener");
    // known-minimum runs render with a leading ≥ (never a bare, overstated total)
    expect(screen.getByText("≥4000")).toBeTruthy();
    // an incomplete strike rate is flagged
    expect(screen.getByText("55.2*")).toBeTruthy();
    expect(H.intlLeaders).toHaveBeenCalledWith("w1", "test", "batting", { limit: 100 });
  });

  it("switches format and discipline", async () => {
    H.listPeople.mockResolvedValue(PEOPLE);
    H.intlLeaders.mockResolvedValue([]);
    const user = userEvent.setup();
    render(<MemoryRouter><InternationalStats /></MemoryRouter>);
    await screen.findByText("No statistics yet");          // honest empty state, not a fake ranking
    await user.click(screen.getByRole("tab", { name: "ODI" }));
    await user.click(screen.getByRole("tab", { name: "Bowling" }));
    await waitFor(() => expect(H.intlLeaders).toHaveBeenCalledWith("w1", "odi", "bowling", { limit: 100 }));
  });
});
