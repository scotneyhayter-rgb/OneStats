// @vitest-environment jsdom
/**
 * "Search the Internet" — the Search again control. A finished research job can be re-run with its
 * original subject/depth/context, so it picks up sources that were added since (e.g. a Trove key).
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const H = vi.hoisted(() => ({
  researchJobs: vi.fn(),
  researchJobFindings: vi.fn(),
  researchStartInternetSearch: vi.fn(),
  researchPauseJob: vi.fn(),
  researchResumeJob: vi.fn(),
  researchCancelJob: vi.fn(),
  researchReviewFinding: vi.fn(),
}));
vi.mock("../../lib/api", () => ({ ApiError: class ApiError extends Error {}, api: H }));

import { InternetSearch } from "./InternetSearch";

const finishedJob = {
  id: "j1", query: "Moyston v Ararat 1864", depth: "deep", status: "succeeded",
  context: { year: 1864 }, progress: { phase: "complete", sources_examined: 0, findings: 0 },
  last_error: null, created_by: "u1", created_at: "2026-11-01", started_at: null,
  finished_at: null, finding_counts: {},
};

afterEach(cleanup);

describe("InternetSearch — Search again", () => {
  it("re-runs a finished job with its original query, depth and context", async () => {
    H.researchJobs.mockResolvedValue([finishedJob]);
    H.researchStartInternetSearch.mockResolvedValue({ id: "j2" });

    render(<InternetSearch workspaceId="w1" />);
    const again = await screen.findByRole("button", { name: /Search again/i });
    fireEvent.click(again);

    await waitFor(() =>
      expect(H.researchStartInternetSearch).toHaveBeenCalledWith("w1", {
        query: "Moyston v Ararat 1864", depth: "deep", context: { year: 1864 },
      }),
    );
  });

  it("does not offer Search again while a job is still running", async () => {
    H.researchJobs.mockResolvedValue([
      { ...finishedJob, status: "running", context: null, progress: { phase: "searching" } },
    ]);
    render(<InternetSearch workspaceId="w1" />);
    await screen.findByText("Moyston v Ararat 1864");
    expect(screen.queryByRole("button", { name: /Search again/i })).toBeNull();
  });
});
