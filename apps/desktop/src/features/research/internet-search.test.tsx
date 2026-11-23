// @vitest-environment jsdom
/**
 * "Search the Internet": the year-range filter, Search again, and deleting duplicate/irrelevant runs.
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
  researchDeleteJob: vi.fn(),
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

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("InternetSearch", () => {
  it("passes a year range as context when starting a search", async () => {
    H.researchJobs.mockResolvedValue([]);
    H.researchStartInternetSearch.mockResolvedValue({ id: "jx" });
    render(<InternetSearch workspaceId="w1" />);
    await waitFor(() => expect(H.researchJobs).toHaveBeenCalled());

    fireEvent.change(screen.getByPlaceholderText(/Find missing Rhymney/i), { target: { value: "Moyston cricket" } });
    fireEvent.change(screen.getByPlaceholderText("e.g. 1924"), { target: { value: "1924" } });
    fireEvent.change(screen.getByPlaceholderText("(optional)"), { target: { value: "1925" } });
    fireEvent.click(screen.getByRole("button", { name: /Search the Internet/i }));

    await waitFor(() => expect(H.researchStartInternetSearch).toHaveBeenCalledWith("w1", {
      query: "Moyston cricket", depth: "standard", context: { year_from: 1924, year_to: 1925 },
    }));
  });

  it("defaults year_to to year_from when only one year is given", async () => {
    H.researchJobs.mockResolvedValue([]);
    H.researchStartInternetSearch.mockResolvedValue({ id: "jx" });
    render(<InternetSearch workspaceId="w1" />);
    await waitFor(() => expect(H.researchJobs).toHaveBeenCalled());

    fireEvent.change(screen.getByPlaceholderText(/Find missing Rhymney/i), { target: { value: "Rhymney cricket" } });
    fireEvent.change(screen.getByPlaceholderText("e.g. 1924"), { target: { value: "1900" } });
    fireEvent.click(screen.getByRole("button", { name: /Search the Internet/i }));

    await waitFor(() => expect(H.researchStartInternetSearch).toHaveBeenCalledWith("w1", {
      query: "Rhymney cricket", depth: "standard", context: { year_from: 1900, year_to: 1900 },
    }));
  });

  it("re-runs a finished job with its original query, depth and context", async () => {
    H.researchJobs.mockResolvedValue([finishedJob]);
    H.researchStartInternetSearch.mockResolvedValue({ id: "j2" });
    render(<InternetSearch workspaceId="w1" />);
    fireEvent.click(await screen.findByRole("button", { name: /Search again/i }));
    await waitFor(() =>
      expect(H.researchStartInternetSearch).toHaveBeenCalledWith("w1", {
        query: "Moyston v Ararat 1864", depth: "deep", context: { year: 1864 },
      }),
    );
  });

  it("deletes a single search when confirmed", async () => {
    H.researchJobs.mockResolvedValue([finishedJob]);
    H.researchDeleteJob.mockResolvedValue({ deleted: true, id: "j1" });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<InternetSearch workspaceId="w1" />);
    fireEvent.click(await screen.findByRole("button", { name: /Delete search/i }));
    await waitFor(() => expect(H.researchDeleteJob).toHaveBeenCalledWith("w1", "j1"));
  });

  it("does not delete when the confirm is dismissed", async () => {
    H.researchJobs.mockResolvedValue([finishedJob]);
    vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<InternetSearch workspaceId="w1" />);
    fireEvent.click(await screen.findByRole("button", { name: /Delete search/i }));
    await Promise.resolve();
    expect(H.researchDeleteJob).not.toHaveBeenCalled();
  });

  it("clears all searches that found nothing", async () => {
    H.researchJobs.mockResolvedValue([finishedJob, { ...finishedJob, id: "j2" }]);
    H.researchDeleteJob.mockResolvedValue({ deleted: true, id: "x" });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<InternetSearch workspaceId="w1" />);
    fireEvent.click(await screen.findByRole("button", { name: /Clear empty \(2\)/i }));
    await waitFor(() => expect(H.researchDeleteJob).toHaveBeenCalledTimes(2));
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
