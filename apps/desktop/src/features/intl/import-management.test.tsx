// @vitest-environment jsdom
/**
 * Import Management: shows genuine import/backfill counts, starts a backfill, and renders the honest
 * empty states + source allow-list. Driven by a mocked API.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

const H = vi.hoisted(() => ({
  cricsheetSummary: vi.fn(), cricsheetImports: vi.fn(), cricsheetControl: vi.fn(),
  cricsheetIdentityReviews: vi.fn(),
}));

vi.mock("../../lib/api", () => ({ ApiError: class ApiError extends Error {}, api: H }));
vi.mock("../../lib/workspace-context", () => ({
  useWorkspace: () => ({ current: { id: "w1", name: "International Men's Cricket", type: "international" } }),
}));
vi.mock("../../lib/auth", () => ({ useAuth: () => ({ user: { id: "u1", is_super_admin: true } }) }));
vi.mock("../../lib/permissions", () => ({ canManage: () => true }));
vi.mock("../../components/layout/AppShell", () => ({
  AppShell: ({ children }: { children: import("react").ReactNode }) => <div>{children}</div>,
}));

import { ImportManagement } from "./ImportManagement";

const SUMMARY = {
  imports: { awaiting_verification: 7, skipped: 3, failed: 1, total: 11 },
  backfills: [
    { id: "b1", format: "test", status: "running", total_seen: 100, processed: 40, imported: 38,
      skipped: 2, failed: 0, last_ref: "123", last_error: null, started_at: null, finished_at: null },
  ],
};

function setup() {
  H.cricsheetSummary.mockResolvedValue(SUMMARY);
  H.cricsheetImports.mockResolvedValue([]);
  H.cricsheetIdentityReviews.mockResolvedValue([]);
  H.cricsheetControl.mockResolvedValue(SUMMARY.backfills[0]);
}

afterEach(cleanup);

describe("Import Management page", () => {
  it("shows genuine progress counts and backfill status", async () => {
    setup();
    render(<MemoryRouter><ImportManagement /></MemoryRouter>);
    await screen.findByText("Historical import (backfill)");
    expect(screen.getByText("7")).toBeTruthy();                 // awaiting review tile
    expect(screen.getByText(/40\/100 processed \(40%\)/)).toBeTruthy();
    expect(screen.getByText("running")).toBeTruthy();
  });

  it("can start a backfill and shows the source allow-list", async () => {
    setup();
    H.cricsheetSummary.mockResolvedValue({ imports: { awaiting_verification: 0, skipped: 0, failed: 0, total: 0 }, backfills: [] });
    const user = userEvent.setup();
    render(<MemoryRouter><ImportManagement /></MemoryRouter>);
    // a not-started format offers Start
    const start = (await screen.findAllByRole("button", { name: /Start/i }))[0];
    await user.click(start);
    await waitFor(() => expect(H.cricsheetControl).toHaveBeenCalledWith("w1", "test", "start"));
    // source info tab lists Cricsheet as fetched and ESPNcricinfo as a benchmark (never fetched)
    await user.click(screen.getByRole("tab", { name: /Source info/i }));
    expect(await screen.findByText("Cricsheet")).toBeTruthy();
    expect(screen.getByText(/never fetched/i)).toBeTruthy();
  });
});
