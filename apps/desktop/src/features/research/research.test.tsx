// @vitest-environment jsdom
/**
 * Research Centre page (Phase 10, Stage 10.1): loads the real DB-backed dashboard, lists sources and
 * projects, and creates a project. Drives the component with a mocked API.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

const H = vi.hoisted(() => ({
  researchDashboard: vi.fn(),
  researchProjects: vi.fn(),
  researchSources: vi.fn(),
  researchCreateProject: vi.fn(),
  researchCreateSource: vi.fn(),
}));

vi.mock("../manage/_shared", () => ({ useManage: () => ({ workspaceId: "w1" }), NoWorkspace: () => <div>no ws</div> }));
vi.mock("../../lib/api", () => ({ ApiError: class ApiError extends Error {}, api: H }));
vi.mock("../../components/layout/AppShell", () => ({
  AppShell: ({ children }: { children: import("react").ReactNode }) => <div>{children}</div>,
}));

import { ResearchCentre } from "./ResearchCentre";

const DASH = {
  projects_active: 1, projects_total: 1, sources_total: 1,
  sources_recent: [{ id: "s1", title: "Ararat Advertiser 1931", source_type: "newspaper_article", created_at: null }],
  matches_under_investigation: 1, draft_scorecards: 3, awaiting_verification: 2, disputed: 0,
  verified: 5, conflicting_evidence: 0, open_tasks: 4, notes_total: 0,
};

function setup() {
  H.researchDashboard.mockResolvedValue(DASH);
  H.researchProjects.mockResolvedValue([
    { id: "p1", title: "RMCC 1891-1900", description: null, status: "active", scope: null, owner: "scotney",
      created_at: "2026-10-25", updated_at: "2026-10-25" },
  ]);
  H.researchSources.mockResolvedValue([
    { id: "s1", title: "Ararat Advertiser 1931", source_type: "newspaper_article", publication: "Ararat Advertiser",
      author: null, publication_date: "1931-11-06", publication_date_precision: "exact", edition: null,
      page_ref: null, original_url: null, copyright_status: "public_domain", usage_restrictions: null,
      ocr_status: "none", created_at: "2026-10-25" },
  ]);
  H.researchCreateProject.mockResolvedValue({ id: "p2", title: "x", status: "active" });
}

afterEach(cleanup);

describe("Research Centre page", () => {
  it("shows the real DB-backed dashboard", async () => {
    setup();
    render(<MemoryRouter><ResearchCentre /></MemoryRouter>);
    await screen.findByText("Active projects");
    expect(screen.getByText("Matches under investigation")).toBeTruthy();
    await screen.findByText("Ararat Advertiser 1931");   // recent source from real data
  });

  it("creates a research project", async () => {
    setup();
    const user = userEvent.setup();
    render(<MemoryRouter><ResearchCentre /></MemoryRouter>);
    await screen.findByText("Active projects");

    await user.click(screen.getByRole("button", { name: /Research Projects/i }));
    await screen.findByText("RMCC 1891-1900");
    await user.type(screen.getByPlaceholderText(/Rhymney CC/i), "Moyston early records");
    await user.click(screen.getByRole("button", { name: /Create project/i }));
    await waitFor(() =>
      expect(H.researchCreateProject).toHaveBeenCalledWith("w1", { title: "Moyston early records", description: null }),
    );
  });
});
