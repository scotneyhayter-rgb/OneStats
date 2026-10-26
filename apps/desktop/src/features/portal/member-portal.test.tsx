// @vitest-environment jsdom
/**
 * Member Portal: lists public + members-only items (flagged) and, when permitted, offers an embedded
 * read-only Ask box that reuses the deterministic engine. Driven by a mocked API.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

const H = vi.hoisted(() => ({ memberPortal: vi.fn(), askOneStats: vi.fn() }));

vi.mock("../manage/_shared", () => ({
  useManage: () => ({ workspaceId: "w1" }),
  NoWorkspace: () => <div>no ws</div>,
}));
vi.mock("../../lib/api", () => ({ ApiError: class ApiError extends Error {}, api: H }));
vi.mock("../../components/layout/AppShell", () => ({
  AppShell: ({ children }: { children: import("react").ReactNode }) => <div>{children}</div>,
}));

import { MemberPortal } from "./MemberPortal";

const DATA = {
  club: "Test CC", primary: "#0b5e3b", workspace_id: "w1", public_count: 1, member_only_count: 1,
  ask: { enabled: true, endpoint: "/api/v1/workspaces/w1/ask" },
  items: [
    { title: "Leading Run Scorers", kind: "report", slug: "s1", status: "published", public: true, stale: false, path: "/api/v1/public/r/s1", snapshot_at: null },
    { title: "Draft Honours", kind: "report", slug: "s2", status: "unpublished", public: false, stale: false, path: null, snapshot_at: null },
  ],
};

afterEach(cleanup);

describe("Member Portal", () => {
  it("shows public and members-only items with the right flags", async () => {
    H.memberPortal.mockResolvedValue(DATA);
    render(<MemoryRouter><MemberPortal /></MemoryRouter>);
    await screen.findByText("Leading Run Scorers");
    expect(screen.getByText("Public")).toBeTruthy();
    expect(screen.getByText("Members only")).toBeTruthy();
    expect(screen.getByText("Draft Honours")).toBeTruthy();
  });

  it("offers Ask OneStats and queries the deterministic engine", async () => {
    H.memberPortal.mockResolvedValue(DATA);
    H.askOneStats.mockResolvedValue({ question: "x", matched: true, answer_summary: "Alice leads with 500 runs." });
    const user = userEvent.setup();
    render(<MemoryRouter><MemberPortal /></MemoryRouter>);
    await screen.findByText("Ask OneStats");
    await user.type(screen.getByPlaceholderText(/most runs/i), "most runs?");
    await user.click(screen.getByRole("button", { name: /^Ask$/i }));
    await waitFor(() => expect(H.askOneStats).toHaveBeenCalledWith("w1", "most runs?"));
    await screen.findByText(/Alice leads with 500 runs/);
  });
});
