// @vitest-environment jsdom
/**
 * Interaction tests for the Partnerships section (Phase 7.2): partnerships generate automatically
 * (no Auto-generate button and no manual Add button), and each entry shows its source
 * (Auto/Manual/Verified), both batter names and the runs. Verifies the UI, not just backend funcs.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
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
  it("shows source badge, both batter names and runs", async () => {
    H.listPartnerships.mockResolvedValue([p({})]);
    renderGrid();
    expect(await screen.findByText("Auto")).toBeTruthy();            // calculated -> Auto badge
    expect(screen.getByRole("button", { name: /Partnership 1 batter 1/i }).textContent).toContain("Jack Jones");
    expect(screen.getByRole("button", { name: /Partnership 1 batter 2/i }).textContent).toContain("Bill Smith");
  });

  it("has no manual Auto-generate or Add button — partnerships are automatic", async () => {
    H.listPartnerships.mockResolvedValue([p({})]);
    renderGrid();
    await screen.findByText("Auto");
    expect(screen.queryByRole("button", { name: /Auto-generate from Fall of Wickets/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /^Add partnership$/i })).toBeNull();
    expect(H.derivePartnerships).not.toHaveBeenCalled();  // no client-triggered derive
  });
});
