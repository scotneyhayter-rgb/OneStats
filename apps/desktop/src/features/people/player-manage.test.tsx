// @vitest-environment jsdom
/** Player management page: the new "Affiliate this player to a club" form posts a createAffiliation
 *  with the chosen club and role. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const H = vi.hoisted(() => ({
  getProfile: vi.fn(), listOrganisations: vi.fn(), identityCandidates: vi.fn(),
  createAffiliation: vi.fn(), personPhotoUrl: vi.fn(), listPeople: vi.fn(),
}));

vi.mock("react-router-dom", () => ({ useParams: () => ({ personId: "p1" }), useNavigate: () => vi.fn() }));
vi.mock("../manage/_shared", () => ({
  useManage: () => ({ workspaceId: "w1", canManage: true }),
  NoWorkspace: () => <div>no ws</div>,
  Detail: ({ children }: { children: import("react").ReactNode }) => <div>{children}</div>,
  Unknown: ({ value }: { value: unknown }) => <>{value ?? "unknown"}</>,
  humanise: (s: string) => s,
}));
vi.mock("./PeopleManagement", () => ({ AttrAdder: () => null }));
vi.mock("../../components/layout/AppShell", () => ({
  AppShell: ({ children }: { children: import("react").ReactNode }) => <div>{children}</div>,
}));
vi.mock("../../lib/api", () => ({ ApiError: class ApiError extends Error {}, api: H }));

import { PlayerManage } from "./PlayerManage";

afterEach(() => { cleanup(); Object.values(H).forEach((fn) => fn.mockReset()); });

describe("PlayerManage", () => {
  it("affiliates the player to a chosen club", async () => {
    H.getProfile.mockResolvedValue({
      person: { display_name: "Daniel Taylor", status: "active", roles: ["player"], dob: null },
      profile: null, affiliations: [], photos: [], numbers: [], leadership: [], recognition: [],
      played_for_clubs: [], person_source_identities: [],
    });
    H.listOrganisations.mockResolvedValue([{ id: "o1", name: "Rhymney Moyston CC" }, { id: "o2", name: "Ararat CC" }]);
    H.identityCandidates.mockResolvedValue([]);
    H.createAffiliation.mockResolvedValue({ id: "a1" });
    H.listPeople.mockResolvedValue([]);

    render(<PlayerManage />);
    await screen.findByText("Daniel Taylor");

    // The affiliation form offers a club picker (the only select with this placeholder option).
    const clubSelect = screen.getByText("— choose club —").closest("select")!;
    fireEvent.change(clubSelect, { target: { value: "o1" } });
    fireEvent.click(screen.getByText("Add affiliation"));

    await waitFor(() => expect(H.createAffiliation).toHaveBeenCalledWith("w1",
      expect.objectContaining({ person_id: "p1", organisation_id: "o1", role: "player" })));
  });
});
