// @vitest-environment jsdom
/**
 * Universal import flow (Phase 8): choosing a file detects its format, Preview reports counts without
 * importing, and Import brings matches in as drafts. Drives the real component with mocked API.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const { importDetect, importGeneric } = vi.hoisted(() => ({ importDetect: vi.fn(), importGeneric: vi.fn() }));

vi.mock("../manage/_shared", () => ({ useManage: () => ({ workspaceId: "w1" }) }));
vi.mock("../../lib/api", () => ({
  ApiError: class ApiError extends Error {},
  api: { importDetect, importGeneric },
}));

import { UniversalImport } from "./UniversalImport";

const CSV = "Date,HomeTeam,AwayTeam,Result\n2024-01-06,Alpha CC,Beta CC,Home win\n";

afterEach(cleanup);

describe("universal import", () => {
  it("detects, previews without importing, then imports as drafts", async () => {
    importDetect.mockResolvedValue({ candidates: [{ format_id: "csv_scorecard", display_name: "CSV match summary", confidence: 0.9 }] });
    importGeneric
      .mockResolvedValueOnce({ format_id: "csv_scorecard", display_name: "CSV match summary", batch_id: "b1", counts: { matches: 1, teams: 2 }, source_system: "csv_scorecard", committed: false })
      .mockResolvedValueOnce({ format_id: "csv_scorecard", display_name: "CSV match summary", batch_id: "b2", counts: { matches: 1 }, source_system: "csv_scorecard", committed: true, created: { match: 1, team: 2 }, matched: {} });
    const user = userEvent.setup();
    render(<UniversalImport />);

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, new File([CSV], "fixtures.csv", { type: "text/csv" }));

    // detection ran and offered the CSV adapter
    await waitFor(() => expect(importDetect).toHaveBeenCalled());
    await screen.findByText(/CSV match summary \(90%\)/);

    // Preview → counts shown, commit:false, nothing imported
    await user.click(screen.getByRole("button", { name: /Preview/i }));
    await screen.findByText(/nothing imported yet/i);
    expect(importGeneric).toHaveBeenLastCalledWith("w1", expect.objectContaining({ commit: false, format_id: "csv_scorecard" }));

    // Import → commit:true, results show created matches
    await user.click(screen.getByRole("button", { name: /^Import$/i }));
    await screen.findByText(/Imported from CSV match summary/i);
    expect(importGeneric).toHaveBeenLastCalledWith("w1", expect.objectContaining({ commit: true }));
    expect(screen.getByText(/created match: 1/i)).toBeTruthy();
  });

  it("warns when no adapter recognises the file", async () => {
    importDetect.mockReset();
    importDetect.mockResolvedValue({ candidates: [] });
    const user = userEvent.setup();
    render(<UniversalImport />);
    await user.upload(document.querySelector('input[type="file"]') as HTMLInputElement,
      new File(["nonsense"], "weird.json", { type: "application/json" }));
    await waitFor(() => expect(importDetect).toHaveBeenCalled());
    await screen.findByText((t) => t.includes("No adapter recognised this file"));
  });
});
