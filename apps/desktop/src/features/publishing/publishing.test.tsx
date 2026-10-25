// @vitest-environment jsdom
/** Website Publishing (Phase 15): lists publications and publishes a report. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const H = vi.hoisted(() => ({ statsCatalogue: vi.fn(), publicationsList: vi.fn(), publicationCreate: vi.fn() }));
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

    render(<Publishing />);
    await waitFor(() => expect(screen.getByText("Leading Run Scorers")).toBeTruthy());
    expect(screen.getByText("/api/v1/public/r/abc123")).toBeTruthy();

    fireEvent.change(screen.getByRole("combobox"), { target: { value: "bat_most_runs" } });
    // after a report is selected the Publish button is enabled
    fireEvent.click(screen.getByText("Publish"));
    await waitFor(() => expect(H.publicationCreate).toHaveBeenCalled());
  });
});
