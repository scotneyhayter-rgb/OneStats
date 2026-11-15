// @vitest-environment jsdom
/**
 * BowlingGrid: the hat-tricks (HT) column records per bowler, and the innings-level
 * run-outs / unassigned-wickets box saves through onInningsPatch — mirroring CricketStatz's
 * bowling card. Drives the real grid with a mocked API and asserts the committed payloads.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const api = vi.hoisted(() => ({
  listBowling: vi.fn(),
  updateBowling: vi.fn(async () => ({})),
  createBowling: vi.fn(async () => ({})),
  deleteBowling: vi.fn(async () => undefined),
  listPeople: vi.fn(async () => []),
  identityCandidates: vi.fn(async () => []),
}));
vi.mock("../../lib/api", () => ({ ApiError: class ApiError extends Error {}, api }));

import { BowlingGrid } from "./grids";

const bowlerRow = {
  id: "b1", innings_id: "i1", person_id: null, bowling_order: 1, overs_text: "4",
  legal_balls: 24, maidens: 1, runs_conceded: 20, wickets: 2, wides: 0, noballs: 0,
  hat_tricks: null as number | null, bowling_type_raw: null, notes: null, evidence: null,
};

function ctx(onInningsPatch: (b: Record<string, unknown>) => void) {
  return {
    workspaceId: "w", inningsId: "i1", canManage: true,
    nameOf: () => null, onPersonLoaded: () => {}, onDirty: () => {}, onChanged: () => {},
    byes: 0, legbyes: 0, unassignedWickets: null, onInningsPatch,
  };
}

afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe("BowlingGrid hat-tricks and unassigned wickets", () => {
  it("records a hat-trick count for a bowler via the HT column", async () => {
    api.listBowling.mockResolvedValue([bowlerRow]);
    const user = userEvent.setup();
    render(<BowlingGrid {...ctx(() => {})} />);

    const ht = await screen.findByLabelText("Hat-tricks 1");
    await user.type(ht, "1");
    ht.blur();
    await waitFor(() => expect(api.updateBowling).toHaveBeenCalledWith("w", "i1", "b1", { hat_tricks: 1 }));
  });

  it("saves run-outs / unassigned wickets to the innings", async () => {
    api.listBowling.mockResolvedValue([bowlerRow]);
    const onInningsPatch = vi.fn();
    const user = userEvent.setup();
    render(<BowlingGrid {...ctx(onInningsPatch)} />);

    const box = await screen.findByLabelText("Run-outs / unassigned wickets");
    await user.type(box, "2");
    box.blur();
    await waitFor(() => expect(onInningsPatch).toHaveBeenCalledWith({ unassigned_wickets: 2 }));
  });
});
