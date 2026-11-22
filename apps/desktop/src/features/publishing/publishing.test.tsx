// @vitest-environment jsdom
/** Website Publishing (Phase 15): lists publications and publishes a report. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const H = vi.hoisted(() => ({
  statsCatalogue: vi.fn(), publicationsList: vi.fn(), publicationCreate: vi.fn(),
  publicationSettingsGet: vi.fn(), publicationSettingsSet: vi.fn(), publicationSiteZipUrl: vi.fn(),
  publicationGithubGet: vi.fn(), publicationGithubSet: vi.fn(), publicationGithubPublish: vi.fn(),
  publicationGithubPagesStatus: vi.fn(), publicationRefreshAll: vi.fn(),
}));
vi.mock("../../lib/workspace-context", () => ({ useWorkspace: () => ({ current: { id: "w1", name: "RMCC" } }) }));
vi.mock("../../lib/auth", () => ({ useAuth: () => ({ user: { id: "u1" } }) }));
vi.mock("../../lib/permissions", () => ({ canManage: () => true }));
vi.mock("../../lib/api", () => ({ ApiError: class ApiError extends Error {}, api: H }));
vi.mock("../../components/layout/AppShell", () => ({
  AppShell: ({ children }: { children: import("react").ReactNode }) => <div>{children}</div>,
}));

import { Publishing } from "./Publishing";

afterEach(cleanup);

describe("Publishing", () => {
  it("lists a publication and publishes a report", async () => {
    H.statsCatalogue.mockResolvedValue({ count: 1, categories: [{ category: "Batting", reports: [
      { id: "bat_most_runs", name: "Most Runs", category: "Batting", description: "", filters: [], qualification: null, limitations: null, split_default: null, csv: true, pdf: true }] }] });
    H.publicationsList.mockResolvedValue([
      { id: "p1", kind: "report", report_id: "bat_most_runs", person_id: null, title: "Leading Run Scorers",
        slug: "abc123", status: "published", stale: false, public_path: "/api/v1/public/r/abc123" }]);
    H.publicationCreate.mockResolvedValue({ id: "p2", kind: "report", slug: "def456", status: "published", title: "Most Runs" });
    H.publicationSettingsGet.mockResolvedValue({ public_base_url: null });
    H.publicationGithubGet.mockResolvedValue({ repo: null, branch: "main", token_set: false });

    render(<Publishing />);
    await waitFor(() => expect(screen.getByText("Leading Run Scorers")).toBeTruthy());
    // with no public hosting address configured, the panel no longer offers the internal relative path
    // as a "URL" — it tells the user to download and host it instead.
    expect(screen.getByText(/Not publicly hosted yet/i)).toBeTruthy();
    // the "Go live" tools are present: whole-site export button + the public address field
    expect(screen.getByRole("button", { name: /Export entire site/i })).toBeTruthy();
    expect(screen.getByPlaceholderText(/github\.io/i)).toBeTruthy();
    // the direct GitHub upload is offered; "Publish to GitHub now" is disabled until a connection is saved
    expect(screen.getByText(/Publish directly to GitHub/i)).toBeTruthy();
    expect((screen.getByRole("button", { name: /Publish to GitHub now/i }) as HTMLButtonElement).disabled).toBe(true);

    fireEvent.change(screen.getByRole("combobox"), { target: { value: "bat_most_runs" } });
    // after a report is selected the Publish button is enabled
    fireEvent.click(screen.getByText("Publish"));
    await waitFor(() => expect(H.publicationCreate).toHaveBeenCalled());
  });

  it("after a GitHub publish, reports the regenerated count + skipped items and starts a Live check", async () => {
    H.statsCatalogue.mockResolvedValue({ count: 0, categories: [] });
    H.publicationsList.mockResolvedValue([]);
    H.publicationSettingsGet.mockResolvedValue({ public_base_url: "https://x.github.io/n" });
    H.publicationGithubGet.mockResolvedValue({ repo: "owner/name", branch: "main", token_set: true });
    H.publicationGithubPublish.mockResolvedValue({
      committed: true, commit: "c0ffee1234", files: 5, repo: "owner/name", branch: "main",
      pages_url: "https://x.github.io/n", refreshed: 3,
      skipped: [{ id: "b1", title: "Bad Report", reason: "RuntimeError" }],
    });
    H.publicationGithubPagesStatus.mockResolvedValue({ state: "building", commit: "c0ffee1234" });

    render(<Publishing />);
    const btn = await screen.findByRole("button", { name: /Publish to GitHub now/i });
    expect((btn as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(btn);

    // honest completion message: how many were regenerated, the commit, and which were skipped
    await screen.findByText(/Regenerated 3 published items with the current data and theme/i);
    expect(screen.getByText(/could not be refreshed: Bad Report/i)).toBeTruthy();
    expect(screen.getByText(/commit c0ffee1/i)).toBeTruthy();
    // and it begins polling for a genuine Live ✓ rather than claiming it instantly
    await screen.findByText(/Checking the GitHub Pages deploy/i);
  });

  it("surfaces items that Refresh all could not regenerate", async () => {
    H.statsCatalogue.mockResolvedValue({ count: 0, categories: [] });
    H.publicationsList.mockResolvedValue([
      { id: "p1", kind: "report", report_id: "x", person_id: null, title: "R", slug: "s",
        status: "published", stale: false, public_path: "/api/v1/public/r/s" }]);
    H.publicationSettingsGet.mockResolvedValue({ public_base_url: null });
    H.publicationGithubGet.mockResolvedValue({ repo: null, branch: "main", token_set: false });
    H.publicationRefreshAll.mockResolvedValue({ refreshed: 2, skipped: [{ id: "b", title: "Broken One", reason: "X" }] });

    render(<Publishing />);
    fireEvent.click(await screen.findByRole("button", { name: /Refresh all/i }));
    await screen.findByText(/Refreshed 2\. 1 could not be refreshed: Broken One/i);
  });
});
