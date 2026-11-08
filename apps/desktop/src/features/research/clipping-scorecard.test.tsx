// @vitest-environment jsdom
/**
 * Create scorecard from clipping (Stage 10.17). The contract under test: parsing + match suggestions are
 * read-only, and NO player is created and NO scorecard written until the researcher clicks "Create draft
 * scorecard" — at which point a new player is created only for a row the researcher left as "create new",
 * never for one matched to an existing player, and unknown figures are sent as null (never 0).
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const H = vi.hoisted(() => ({
  researchParseClipping: vi.fn(),
  createPerson: vi.fn(),
  researchStartReconstruction: vi.fn(),
  createInnings: vi.fn(),
  createBatting: vi.fn(),
}));
vi.mock("../../lib/api", () => ({ ApiError: class ApiError extends Error {}, api: H }));

import { ClippingScorecard } from "./ClippingScorecard";

const PARSED = {
  batters: [
    {
      position: 1, name: "J Smith", runs: 42, balls: null, dismissal_kind: "caught",
      dismissal_text: "c Jones b Brown", bowler_name: "Brown", fielder_name: "Jones", raw: "J Smith c Jones b Brown 42",
      candidates: [{ person_id: "p-smith", display_name: "J Smith", exact: true }],
    },
    {
      position: 2, name: "A Allen", runs: null, balls: null, dismissal_kind: "not_out",
      dismissal_text: "not out", bowler_name: null, fielder_name: null, raw: "A Allen not out",
      candidates: [],
    },
  ],
  bowlers: [],
  unparsed_lines: [],
  disclaimer: "…confirm…",
};

afterEach(() => {
  cleanup();
  Object.values(H).forEach((fn) => fn.mockReset());
});

describe("ClippingScorecard", () => {
  it("parses read-only and creates nothing until confirm, then creates only the new player", async () => {
    H.researchParseClipping.mockResolvedValue(PARSED);
    H.createPerson.mockResolvedValue({ id: "p-allen" });
    H.researchStartReconstruction.mockResolvedValue({ id: "m1" });
    H.createInnings.mockResolvedValue({ id: "i1" });
    H.createBatting.mockResolvedValue({ id: "be" });

    render(<ClippingScorecard workspaceId="w1" initialText="J Smith c Jones b Brown 42\nA Allen not out" onClose={() => {}} />);

    // The draft table renders both batters.
    await waitFor(() => expect(screen.getByText("J Smith")).toBeTruthy());
    expect(screen.getByText("A Allen")).toBeTruthy();
    // "unknown" is shown for A Allen's missing score, not a zero.
    expect(screen.getByText("unknown")).toBeTruthy();

    // Nothing has been written just by parsing / reviewing.
    expect(H.createPerson).not.toHaveBeenCalled();
    expect(H.researchStartReconstruction).not.toHaveBeenCalled();
    expect(H.createInnings).not.toHaveBeenCalled();
    expect(H.createBatting).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Create draft scorecard" }));

    await waitFor(() => expect(H.researchStartReconstruction).toHaveBeenCalledTimes(1));
    // A new player is created ONLY for the unmatched row (A Allen), never for the matched J Smith.
    expect(H.createPerson).toHaveBeenCalledTimes(1);
    expect(H.createPerson).toHaveBeenCalledWith("w1", { display_name: "A Allen", roles: ["player"] });
    expect(H.createInnings).toHaveBeenCalledTimes(1);
    expect(H.createBatting).toHaveBeenCalledTimes(2);

    // J Smith is linked to the existing person; A Allen's unknown score is sent as null, not 0.
    const smithCall = H.createBatting.mock.calls.find((c) => c[2].person_id === "p-smith");
    const allenCall = H.createBatting.mock.calls.find((c) => c[2].person_id === "p-allen");
    expect(smithCall?.[2].runs).toBe(42);
    expect(smithCall?.[2].dismissal_type).toBe("caught");
    expect(allenCall?.[2].runs).toBeNull();

    await waitFor(() => expect(screen.getByText(/Draft scorecard created/i)).toBeTruthy());
  });
});
