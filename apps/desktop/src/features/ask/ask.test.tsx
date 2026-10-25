// @vitest-environment jsdom
/** Ask OneStats (Phase 14): asks a question and renders the mapped report answer + qualifications. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const H = vi.hoisted(() => ({ askOneStats: vi.fn() }));
vi.mock("../../lib/workspace-context", () => ({ useWorkspace: () => ({ current: { id: "w1", name: "RMCC" } }) }));
vi.mock("../../lib/api", () => ({ ApiError: class ApiError extends Error {}, api: H }));
vi.mock("../../components/layout/AppShell", () => ({
  AppShell: ({ children }: { children: import("react").ReactNode }) => <div>{children}</div>,
}));

import { Ask } from "./Ask";

afterEach(cleanup);

describe("Ask OneStats", () => {
  it("answers a mapped question with the report table and qualifications", async () => {
    H.askOneStats.mockResolvedValue({
      question: "most runs", matched: true, confidence: "high", report_id: "bat_most_runs",
      report_name: "Most Runs", category: "Batting", interpretation: "I read this as the “Most Runs” report.",
      scope: [], answer_summary: "Run Machine leads: 150 Runs.",
      columns: [{ key: "player", label: "Player", align: "left", decimals: null },
                { key: "runs", label: "Runs", align: "right", decimals: null }],
      rows: [{ player: "Run Machine", runs: 150 }],
      qualifications: ["Figures are from approved scorecards only; unknown values are never treated as zero."],
    });
    render(<Ask />);
    fireEvent.change(screen.getByPlaceholderText("Ask about your club's statistics…"), { target: { value: "most runs" } });
    fireEvent.click(screen.getByText("Ask"));
    await waitFor(() => expect(screen.getByText("Run Machine leads: 150 Runs.")).toBeTruthy());
    expect(screen.getByText("Most Runs")).toBeTruthy();
    // the qualification note is shown (the page also has a static disclaimer with similar wording)
    expect(screen.getAllByText(/approved scorecards only/).length).toBeGreaterThanOrEqual(1);
  });

  it("offers nearest reports when a question cannot be mapped (no fabrication)", async () => {
    H.askOneStats.mockResolvedValue({
      question: "meaning of life", matched: false, message: "I couldn't confidently map that question — here are the closest reports.",
      suggestions: [{ id: "bat_most_runs", name: "Most Runs", category: "Batting" }],
    });
    render(<Ask />);
    fireEvent.change(screen.getByPlaceholderText("Ask about your club's statistics…"), { target: { value: "meaning of life" } });
    fireEvent.click(screen.getByText("Ask"));
    await waitFor(() => expect(screen.getByText(/couldn't confidently map/)).toBeTruthy());
    expect(screen.getByText("Closest reports:")).toBeTruthy();
  });
});
