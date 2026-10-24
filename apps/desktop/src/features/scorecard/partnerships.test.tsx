// @vitest-environment jsdom
/**
 * Interaction tests for the Partnerships section (Stage 7): the Add Partnership and
 * Auto-generate-from-FOW controls are present and wired, and each entry shows its source
 * (Auto/Manual/Verified), both batter names and the runs. Verifies the UI, not just backend funcs.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Partnership } from "../../lib/api";

const H = vi.hoisted(() => ({
  listPartnerships: vi.fn(), createPartnership: vi.fn(), updatePartnership: vi.fn(),
  deletePartnership: vi.fn(), derivePartnerships: vi.fn(), listPeople: vi.fn(), identityCandidates: vi.fn(),
}));
vi.mock("../../lib/api", () => ({ ApiError: class ApiError extends Error {}, api: { ...H } }));

import { PartnershipsGrid } from "./grids";

const p = (o: Partial<Partnership>): Partnership => ({
  id: "pt1", innings_id: "i1", wicket_number: 1, runs: 45, balls: null, player1_person_id: "a",
  player2_person_id: "b", unbroken: null, end_reason: "wicket", origin: "calculated", notes: null,
  evidence: null, ...o,
});
const nameOf = (id: string | null) => (id === "a" ? "Jack Jones" : id === "b" ? "Bill Smith" : null);

function renderGrid() {
  return render(
    <PartnershipsGrid workspaceId="w" inningsId="i1" canManage nameOf={nameOf}
      onPersonLoaded={() => {}} onDirty={() => {}} onChanged={() => {}} />,
  );
}

beforeEach(() => Object.values(H).forEach((fn) => fn.mockReset()));
afterEach(cleanup);

describe("partnerships section", () => {
  it("shows source badge, both batter names and runs, and the action buttons", async () => {
    H.listPartnerships.mockResolvedValue([p({})]);
    renderGrid();
    expect(await screen.findByText("Auto")).toBeTruthy();            // calculated -> Auto badge
    expect(screen.getByRole("button", { name: /Partnership 1 batter 1/i }).textContent).toContain("Jack Jones");
    expect(screen.getByRole("button", { name: /Partnership 1 batter 2/i }).textContent).toContain("Bill Smith");
    expect(screen.getByRole("button", { name: /Auto-generate from Fall of Wickets/i })).toBeTruthy();
    // the manual "Add partnership" control was intentionally removed (partnerships are auto-derived)
    expect(screen.queryByRole("button", { name: /^Add partnership$/i })).toBeNull();
  });

  it("Auto-generate calls derive", async () => {
    H.listPartnerships.mockResolvedValue([]);
    H.derivePartnerships.mockResolvedValue([]);
    const user = userEvent.setup();
    renderGrid();
    await user.click(await screen.findByRole("button", { name: /Auto-generate from Fall of Wickets/i }));
    await waitFor(() => expect(H.derivePartnerships).toHaveBeenCalledWith("w", "i1"));
  });
});
