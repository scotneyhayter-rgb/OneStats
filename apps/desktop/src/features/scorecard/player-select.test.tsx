// @vitest-environment jsdom
/**
 * Keyboard + ARIA for the inline player typeahead (PlayerSelect): opening the dropdown moves focus into
 * the search input, the input is a combobox whose aria-activedescendant tracks the highlighted row, and
 * ArrowDown/ArrowUp/Enter drive selection without the mouse.
 */
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const H = vi.hoisted(() => ({
  listPeople: vi.fn(), createPerson: vi.fn(), addPersonRole: vi.fn(), identityCandidates: vi.fn(),
  listOrganisations: vi.fn(), createAffiliation: vi.fn(),
}));
vi.mock("../../lib/api", () => ({ ApiError: class ApiError extends Error {}, api: { ...H } }));

import { PlayerSelect } from "./PlayerSelect";

const PEOPLE = [
  { id: "p1", display_name: "Alice Archer", status: "active", is_junior: false, privacy_protected: false, dob: null, dob_precision: "unknown", notes: null, merged_into_id: null },
  { id: "p2", display_name: "Bob Bowler", status: "active", is_junior: false, privacy_protected: false, dob: null, dob_precision: "unknown", notes: null, merged_into_id: null },
];
const NAMES: Record<string, string> = { p1: "Alice Archer", p2: "Bob Bowler" };

function Harness({ onChange }: { onChange: (id: string | null) => void }) {
  const [value, setValue] = useState<string | null>(null);
  return (
    <PlayerSelect workspaceId="w" value={value} nameOf={(id) => (id ? NAMES[id] ?? null : null)}
      onChange={(id) => { setValue(id); onChange(id); }} onPersonLoaded={() => {}} aria-label="Batter 1" />
  );
}

beforeEach(() => {
  Object.values(H).forEach((fn) => fn.mockReset());
  H.listPeople.mockResolvedValue(PEOPLE);
  H.identityCandidates.mockResolvedValue([]);
});
afterEach(cleanup);

async function open(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: "Batter 1" }));
  return (await screen.findByRole("combobox")) as HTMLInputElement;
}

describe("PlayerSelect keyboard + ARIA", () => {
  it("moves focus into the search combobox when opened", async () => {
    const user = userEvent.setup();
    render(<Harness onChange={() => {}} />);
    const input = await open(user);
    await waitFor(() => expect(document.activeElement).toBe(input));
    expect(input.getAttribute("role")).toBe("combobox");
    expect(input.getAttribute("aria-controls")).toBeTruthy();
  });

  it("aria-activedescendant tracks the highlighted option and Enter selects it", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<Harness onChange={onChange} />);
    const input = await open(user);
    // results load; first option is highlighted and marked selected
    const first = await screen.findByRole("option", { name: /Alice Archer/i });
    await waitFor(() => expect(input.getAttribute("aria-activedescendant")).toBe(first.id));
    expect(first.getAttribute("aria-selected")).toBe("true");
    // ArrowDown moves the highlight to Bob; activedescendant and aria-selected follow
    await user.keyboard("{ArrowDown}");
    const second = screen.getByRole("option", { name: /Bob Bowler/i });
    await waitFor(() => expect(input.getAttribute("aria-activedescendant")).toBe(second.id));
    expect(second.getAttribute("aria-selected")).toBe("true");
    expect(first.getAttribute("aria-selected")).toBe("false");
    // Enter selects the highlighted row (no mouse)
    await user.keyboard("{Enter}");
    await waitFor(() => expect(onChange).toHaveBeenCalledWith("p2"));
  });

  it("Escape closes the dropdown", async () => {
    const user = userEvent.setup();
    render(<Harness onChange={() => {}} />);
    await open(user);
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("combobox")).toBeNull());
  });
});
