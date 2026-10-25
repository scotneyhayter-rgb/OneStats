// @vitest-environment jsdom
/**
 * Interaction regression test for the scorecard dropdown-selection bug (Stage 7). Drives the shared
 * PlayerSelect the way a user does — open, search, click an option — through a stateful parent that
 * mirrors how the grids/officials bind it (value + onChange). Guards that a selection immediately
 * populates the field, stores the correct ID, and survives a re-render. Real interaction, not just
 * rendering.
 */
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const { listPeople, identityCandidates } = vi.hoisted(() => ({
  listPeople: vi.fn(),
  identityCandidates: vi.fn(),
}));

vi.mock("../../lib/api", () => ({
  ApiError: class ApiError extends Error {},
  api: { listPeople, identityCandidates, createPerson: vi.fn() },
}));

import { PlayerSelect } from "./PlayerSelect";

const frank = {
  id: "p1", display_name: "Frank Frederick", status: "active", is_junior: false,
  privacy_protected: false, dob: null, dob_precision: "unknown", notes: null, merged_into_id: null,
};
const NAMES: Record<string, string> = { p1: "Frank Frederick" };

function Harness({ onChange }: { onChange: (id: string | null) => void }) {
  const [value, setValue] = useState<string | null>(null);
  return (
    <PlayerSelect
      workspaceId="w"
      value={value}
      nameOf={(id) => (id ? NAMES[id] ?? null : null)}
      onChange={(id) => { setValue(id); onChange(id); }}
      onPersonLoaded={() => {}}
      aria-label="Batter 1"
    />
  );
}

afterEach(cleanup);

describe("player dropdown selection", () => {
  it("populates the field with the selected player and stores the correct id", async () => {
    listPeople.mockResolvedValue([frank]);
    identityCandidates.mockResolvedValue([]);
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<Harness onChange={onChange} />);

    // starts unknown
    const trigger = screen.getByRole("button", { name: "Batter 1" });
    expect(trigger.textContent).toMatch(/Unknown/i);

    // open, search, select
    await user.click(trigger);
    const searchbox = await screen.findByPlaceholderText(/Search player/i);
    await user.type(searchbox, "Frank");
    const option = await screen.findByText("Frank Frederick");
    await user.click(option);

    // correct id stored
    expect(onChange).toHaveBeenCalledWith("p1");
    // field now shows the selected player (value bound -> nameOf), and no longer "Unknown"
    await waitFor(() => {
      const t = screen.getByRole("button", { name: "Batter 1" });
      expect(t.textContent).toContain("Frank Frederick");
      expect(t.textContent).not.toMatch(/Unknown/i);
    });
  });

  it("offers a priority player (this innings' batter) even when the club-scoped search excludes them", async () => {
    // David batted as a fill-in; the club-scoped search returns nobody, but he must stay selectable
    listPeople.mockResolvedValue([]);
    identityCandidates.mockResolvedValue([]);
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <PlayerSelect
        workspaceId="w"
        value={null}
        nameOf={(id) => (id === "pd" ? "David Padley" : null)}
        onChange={onChange}
        onPersonLoaded={() => {}}
        organisationId="club-pomonal"
        scopeLabel="Pomonal"
        priorityPeople={[{ id: "pd", display_name: "David Padley" }]}
        aria-label="Batter out 1"
      />,
    );
    await user.click(screen.getByRole("button", { name: "Batter out 1" }));
    // shown despite the club scope and empty search results, and selectable
    const option = await screen.findByText("David Padley");
    await user.click(option);
    expect(onChange).toHaveBeenCalledWith("pd");
  });

  it("can be cleared back to unknown", async () => {
    listPeople.mockResolvedValue([frank]);
    identityCandidates.mockResolvedValue([]);
    const user = userEvent.setup();
    render(<Harness onChange={() => {}} />);
    await user.click(screen.getByRole("button", { name: "Batter 1" }));
    await user.type(await screen.findByPlaceholderText(/Search player/i), "Frank");
    await user.click(await screen.findByText("Frank Frederick"));
    await waitFor(() => expect(screen.getByRole("button", { name: "Batter 1" }).textContent).toContain("Frank Frederick"));
    await user.click(screen.getByRole("button", { name: "Clear player" }));
    expect(screen.getByRole("button", { name: "Batter 1" }).textContent).toMatch(/Unknown/i);
  });
});
