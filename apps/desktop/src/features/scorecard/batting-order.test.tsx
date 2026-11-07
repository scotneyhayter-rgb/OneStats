// @vitest-environment jsdom
/**
 * Interaction tests for batting-order management (Stage 7): the drag handle, up/down controls and
 * remove-with-confirmation are present and wired. Verifies the controls are actually in the DOM
 * (not just that backend functions exist) and that moving/removing call the reorder/delete APIs
 * with the correct order — guarding that whole records move and remaining rows renumber.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { BattingEntry } from "../../lib/api";

const H = vi.hoisted(() => ({
  listBatting: vi.fn(), updateBatting: vi.fn(), deleteBatting: vi.fn(), reorderBatting: vi.fn(),
  createBatting: vi.fn(), listPeople: vi.fn(), identityCandidates: vi.fn(),
}));
vi.mock("../../lib/api", () => ({ ApiError: class ApiError extends Error {}, api: { ...H } }));

import { BattingGrid } from "./grids";

const mkRow = (o: Partial<BattingEntry>): BattingEntry => ({
  id: "x", innings_id: "i1", person_id: null, batting_position: 1, runs: null, balls_faced: null,
  fours: null, sixes: null, minutes: null, dismissal_type: null, dismissal_source_code: null,
  bowler_person_id: null, fielder_person_id: null, notes: null, evidence: null, ...o,
});
const r1 = mkRow({ id: "be1", batting_position: 1, person_id: "p1", runs: 10 });
const r2 = mkRow({ id: "be2", batting_position: 2, person_id: "p2", runs: 20 });
const nameOf = (id: string | null) => (id === "p1" ? "First" : id === "p2" ? "Second" : null);

function renderGrid() {
  return render(
    <BattingGrid workspaceId="w" inningsId="i1" canManage nameOf={nameOf}
      onPersonLoaded={() => {}} onDirty={() => {}} onChanged={() => {}} />,
  );
}

beforeEach(() => Object.values(H).forEach((fn) => fn.mockReset()));
afterEach(cleanup);

describe("batting-order controls", () => {
  it("renders drag handles and up/down controls for each row", async () => {
    H.listBatting.mockResolvedValue([r1, r2]);
    renderGrid();
    // controls are visibly present
    expect(await screen.findByRole("button", { name: /Drag batter 1/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Move batter 1 up/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Move batter 1 down/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Remove batter 1/i })).toBeTruthy();
    // first row's Up is disabled; last row's Down is disabled
    expect((screen.getByRole("button", { name: /Move batter 1 up/i }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: /Move batter 2 down/i }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("moving a batter down sends the reordered ids", async () => {
    H.listBatting.mockResolvedValue([r1, r2]);
    H.reorderBatting.mockResolvedValue([]);
    const user = userEvent.setup();
    renderGrid();
    await screen.findByRole("button", { name: /Move batter 1 down/i });
    await user.click(screen.getByRole("button", { name: /Move batter 1 down/i }));
    await waitFor(() => expect(H.reorderBatting).toHaveBeenCalledWith("w", "i1", ["be2", "be1"]));
  });

  it("removing an entry with statistics asks for confirmation, then deletes and renumbers", async () => {
    H.listBatting.mockResolvedValue([r1, r2]);
    H.deleteBatting.mockResolvedValue(undefined);
    H.reorderBatting.mockResolvedValue([]);
    const user = userEvent.setup();
    renderGrid();
    await user.click(await screen.findByRole("button", { name: /Remove batter 1/i }));
    // confirmation dialog appears (entry has stats)
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/Remove this batter/i)).toBeTruthy();
    expect(H.deleteBatting).not.toHaveBeenCalled(); // not yet
    await user.click(within(dialog).getByRole("button", { name: /^Remove$/i }));
    await waitFor(() => expect(H.deleteBatting).toHaveBeenCalledWith("w", "i1", "be1"));
    // remaining entry is renumbered via reorder
    await waitFor(() => expect(H.reorderBatting).toHaveBeenCalledWith("w", "i1", ["be2"]));
  });

  it("cancelling removal does not delete", async () => {
    H.listBatting.mockResolvedValue([r1, r2]);
    H.deleteBatting.mockResolvedValue(undefined);
    const user = userEvent.setup();
    renderGrid();
    await user.click(await screen.findByRole("button", { name: /Remove batter 1/i }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /Cancel/i }));
    expect(H.deleteBatting).not.toHaveBeenCalled();
  });
});

describe("fresh-card seeding and the fielder box", () => {
  it("opens a full XI (11 positions) when the batting card is empty", async () => {
    H.listBatting.mockResolvedValue([]);
    H.createBatting.mockResolvedValue({});
    renderGrid();
    await waitFor(() => expect(H.createBatting).toHaveBeenCalledTimes(11));
    expect(H.createBatting).toHaveBeenNthCalledWith(1, "w", "i1", { batting_position: 1 });
    expect(H.createBatting).toHaveBeenNthCalledWith(11, "w", "i1", { batting_position: 11 });
  });

  it("does not seed when the card already has batters", async () => {
    H.listBatting.mockResolvedValue([r1, r2]);
    renderGrid();
    await screen.findByRole("button", { name: /Remove batter 1/i });
    expect(H.createBatting).not.toHaveBeenCalled();
  });

  it("hides the Fielder box for a bowler-only dismissal and shows it for a catch", async () => {
    const bowled = mkRow({ id: "b1", batting_position: 1, person_id: "p1", dismissal_type: "bowled" });
    const caught = mkRow({ id: "c1", batting_position: 2, person_id: "p2", dismissal_type: "caught" });
    H.listBatting.mockResolvedValue([bowled, caught]);
    H.listPeople.mockResolvedValue([]);
    renderGrid();
    await screen.findByRole("button", { name: /^Batter 1$/i });
    expect(screen.queryByRole("button", { name: /Fielder for batter 1/i })).toBeNull();   // bowled: hidden
    expect(screen.getByRole("button", { name: /Fielder for batter 2/i })).toBeTruthy();    // caught: shown
  });

  it("clears a stale fielder when the dismissal becomes bowler-only", async () => {
    const caught = mkRow({ id: "c1", batting_position: 1, person_id: "p1", dismissal_type: "caught", fielder_person_id: "f1" });
    H.listBatting.mockResolvedValue([caught]);
    H.updateBatting.mockResolvedValue({});
    H.listPeople.mockResolvedValue([]);
    const user = userEvent.setup();
    renderGrid();
    const sel = await screen.findByLabelText(/How out 1/i);
    await user.selectOptions(sel, "bowled");
    await waitFor(() =>
      expect(H.updateBatting).toHaveBeenCalledWith("w", "i1", "c1", { dismissal_type: "bowled", fielder_person_id: null }));
  });
});
