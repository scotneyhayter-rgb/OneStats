// @vitest-environment jsdom
/**
 * AutoSync page (Phase 9): loads real dashboard status, runs Sync Now, and accepts a review item.
 * Drives the component with a mocked API.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

const H = vi.hoisted(() => ({
  autosyncDashboard: vi.fn(), autosyncSources: vi.fn(), autosyncConnectors: vi.fn(),
  autosyncReview: vi.fn(), autosyncCoverage: vi.fn(), autosyncSyncNow: vi.fn(),
  autosyncAccept: vi.fn(), autosyncReject: vi.fn(), autosyncBulk: vi.fn(),
  autosyncAddSource: vi.fn(), autosyncSetSourceEnabled: vi.fn(),
}));

vi.mock("../manage/_shared", () => ({ useManage: () => ({ workspaceId: "w1" }), NoWorkspace: () => <div>no ws</div> }));
vi.mock("../../lib/api", () => ({ ApiError: class ApiError extends Error {}, api: H }));
vi.mock("../../components/layout/AppShell", () => ({
  AppShell: ({ children }: { children: import("react").ReactNode }) => <div>{children}</div>,
}));

import { AutoSync } from "./AutoSync";

const DASH = {
  sources: 1, pending_review: 2, new_matches: 2, possible_duplicates: 0, updated_scorecards: 0,
  jobs_running: 0, jobs_failed: 0, coverage: { searched: 1 }, last_success_at: null,
};
const ITEM = {
  id: "i1", source_system: "svc_feed", source_ref: "r1", kind: "new_match", classification: "new",
  status: "pending_review", confidence: null, match_id: null,
  candidate: { match: { match_date: "2024-01-06" }, home_team_name: "Alpha CC", away_team_name: "Beta CC" },
  proposed_changes: null,
};

function setup() {
  H.autosyncDashboard.mockResolvedValue(DASH);
  H.autosyncSources.mockResolvedValue([{ id: "s1", connector_id: "svc_feed", name: "svc_feed", provider: "F",
    access_method: "fixture", reliability: "ok", enabled: true, last_success_at: null, auth_required: false }]);
  H.autosyncConnectors.mockResolvedValue([{ connector_id: "svc_feed", provider: "Fixture", status: "fixture",
    access_method: "fixture", countries: [], formats: [], coverage: null, auth_required: false, version: "0.1", notes: null }]);
  H.autosyncReview.mockResolvedValue([ITEM]);
  H.autosyncCoverage.mockResolvedValue([{ id: "c1", scope_key: "new", status: "searched", matches_found: 2, searched_at: null }]);
  H.autosyncSyncNow.mockResolvedValue({ ran: true, job: { id: "j1", status: "succeeded" } });
  H.autosyncAccept.mockResolvedValue({ ...ITEM, status: "accepted" });
}

afterEach(cleanup);

describe("AutoSync page", () => {
  it("shows real dashboard status and the review queue", async () => {
    setup();
    render(<MemoryRouter><AutoSync /></MemoryRouter>);
    await screen.findByText("Awaiting review");
    // the count comes from the dashboard, not a fabricated number
    expect(screen.getAllByText("2").length).toBeGreaterThan(0);
    await screen.findByText(/Alpha CC v Beta CC/);
    expect(screen.getByText("new")).toBeTruthy();   // classification badge
  });

  it("runs Sync Now and accepts a review item", async () => {
    setup();
    const user = userEvent.setup();
    render(<MemoryRouter><AutoSync /></MemoryRouter>);
    await screen.findByText(/Alpha CC v Beta CC/);

    await user.click(screen.getByRole("button", { name: /Sync Now/i }));
    await waitFor(() => expect(H.autosyncSyncNow).toHaveBeenCalledWith("w1", { source_system: "svc_feed", kind: "manual" }));

    await user.click(screen.getByRole("button", { name: /^Accept$/i }));
    await waitFor(() => expect(H.autosyncAccept).toHaveBeenCalledWith("w1", "i1"));
  });
});
