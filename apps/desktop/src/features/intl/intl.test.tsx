// @vitest-environment jsdom
/**
 * International Updates page: renders the real daily schedule, honest run history (a "no pipeline" run
 * is shown as fired-but-nothing-imported, a missed run as a late catch-up), an unknown expected total
 * shown as "unknown" (not zero), and drives Update Now against the mocked API.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

const H = vi.hoisted(() => ({
  schedulerTasks: vi.fn(), schedulerRuns: vi.fn(), schedulerRunNow: vi.fn(),
  schedulerPause: vi.fn(), schedulerEnable: vi.fn(), matchIndexSummary: vi.fn(),
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

import { InternationalUpdates } from "./InternationalUpdates";

const TASK = {
  id: "t1", name: "Daily international update", task_kind: "intl_weekly_update", enabled: true,
  paused: false, schedule_kind: "daily" as const, timezone: "Australia/Melbourne", day_of_week: null,
  hour: 4, minute: 0, catch_up: true, next_run_at: "2026-11-03T17:00:00Z",
  last_run_at: "2026-11-02T17:00:00Z", last_status: "no_pipeline", last_error: null,
};
const RUNS = [
  { id: "r1", task_id: "t1", scheduled_for: "2026-11-02T17:00:00Z", ran_at: "2026-11-02T17:00:03Z",
    was_catch_up: false, status: "no_pipeline" as const,
    detail: "daily update fired; import pipeline not yet wired", error: null, enqueued_job_id: null },
  { id: "r2", task_id: "t1", scheduled_for: "2026-10-30T17:00:00Z", ran_at: "2026-11-01T09:00:00Z",
    was_catch_up: true, status: "skipped" as const, detail: "missed while powered off", error: null, enqueued_job_id: null },
];
const EMPTY_FMT = { states: { expected: 0, indexed: 0, imported: 0, complete: 0, verified: 0 },
  candidates: 0, disputed: 0, expected: null, coverage_state: "unknown" as const };
const SUMMARY = { test: EMPTY_FMT, odi: EMPTY_FMT, t20i: EMPTY_FMT };

function setup() {
  H.schedulerTasks.mockResolvedValue([TASK]);
  H.schedulerRuns.mockResolvedValue(RUNS);
  H.matchIndexSummary.mockResolvedValue(SUMMARY);
  H.schedulerRunNow.mockResolvedValue({ task_id: "t1", status: "no_pipeline", was_catch_up: false, scheduled_for: null });
}

afterEach(cleanup);

describe("International Updates page", () => {
  it("shows the daily schedule and an honest run history", async () => {
    setup();
    render(<MemoryRouter><InternationalUpdates /></MemoryRouter>);
    await screen.findByText(/every day at 04:00 \(Australia\/Melbourne\)/);
    // a no-pipeline run is labelled truthfully, not as a success
    expect(await screen.findByText("no import pipeline yet")).toBeTruthy();
    // a missed run is flagged as a late catch-up (never shown as on-time)
    expect(screen.getByText("late catch-up")).toBeTruthy();
  });

  it("shows an unknown expected total as 'unknown', never zero", async () => {
    setup();
    render(<MemoryRouter><InternationalUpdates /></MemoryRouter>);
    await screen.findByText("Test");
    // three formats, each unknown
    expect(screen.getAllByText("unknown").length).toBeGreaterThanOrEqual(3);
  });

  it("runs Update now against the scheduler API", async () => {
    setup();
    const user = userEvent.setup();
    render(<MemoryRouter><InternationalUpdates /></MemoryRouter>);
    await user.click(await screen.findByRole("button", { name: /Update now/i }));
    await waitFor(() => expect(H.schedulerRunNow).toHaveBeenCalledWith("w1", "t1"));
  });
});
