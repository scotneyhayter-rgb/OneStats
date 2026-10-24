// @vitest-environment jsdom
/**
 * Interaction tests for the universal Create Person wizard (Stage 7): launching it from a person
 * selector's "Create New Person" action, the context title, returning the new person to the
 * originating field, reusing an existing identity (no duplicate), and cancelling without creating.
 */
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const H = vi.hoisted(() => ({
  listPeople: vi.fn(), createPerson: vi.fn(), addPersonRole: vi.fn(), identityCandidates: vi.fn(),
}));
vi.mock("../../lib/api", () => ({ ApiError: class ApiError extends Error {}, api: { ...H } }));

import { PlayerSelect } from "./PlayerSelect";

const NAMES: Record<string, string> = { new1: "Tony Cacciola", ex1: "Tony Caccia" };
function Harness({ onChange, roleLabel }: { onChange: (id: string | null) => void; roleLabel?: string }) {
  const [value, setValue] = useState<string | null>(null);
  return (
    <PlayerSelect workspaceId="w" value={value} nameOf={(id) => (id ? NAMES[id] ?? null : null)}
      onChange={(id) => { setValue(id); onChange(id); }} onPersonLoaded={() => {}}
      aria-label="Batter 1" roleLabel={roleLabel} />
  );
}

async function openCreate(user: ReturnType<typeof userEvent.setup>, typed: string) {
  await user.click(screen.getByRole("button", { name: "Batter 1" }));
  await user.type(await screen.findByPlaceholderText(/Search player/i), typed);
  await user.click(await screen.findByRole("option", { name: /Create New Person/i }));
  return screen.findByRole("dialog");
}

beforeEach(() => Object.values(H).forEach((fn) => fn.mockReset()));
afterEach(cleanup);

describe("universal Create Person wizard", () => {
  it("launches from the selector with the context title and prefilled name, and returns the new person", async () => {
    H.listPeople.mockResolvedValue([]);           // no existing matches
    H.createPerson.mockResolvedValue({ id: "new1" });
    H.identityCandidates.mockResolvedValue([]);
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<Harness onChange={onChange} roleLabel="Player" />);

    const dialog = await openCreate(user, "Tony Cacciola");
    expect(within(dialog).getByText("Create Player")).toBeTruthy();            // context title
    expect((within(dialog).getByLabelText(/Name/i) as HTMLInputElement).value).toBe("Tony Cacciola"); // prefilled

    await user.click(within(dialog).getByRole("button", { name: /Create Person/i }));
    await waitFor(() => expect(H.createPerson).toHaveBeenCalled());
    expect((H.createPerson.mock.calls[0][1] as { display_name: string }).display_name).toBe("Tony Cacciola");
    await waitFor(() => expect(onChange).toHaveBeenCalledWith("new1"));        // returned to the field
    await waitFor(() => expect(screen.getByRole("button", { name: "Batter 1" }).textContent).toContain("Tony Cacciola"));
  });

  it("offers an existing identity for reuse instead of creating a duplicate", async () => {
    // a person with a similar name already exists — the wizard must surface it for reuse
    H.listPeople.mockResolvedValue([
      { id: "ex1", display_name: "Tony Caccia", status: "active", is_junior: false, privacy_protected: false, dob: null, dob_precision: "unknown", notes: null, merged_into_id: null },
    ]);
    H.addPersonRole.mockResolvedValue({});
    H.identityCandidates.mockResolvedValue([]);
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<Harness onChange={onChange} />);
    const dialog = await openCreate(user, "Tony Cacc");
    await within(dialog).findByText(/Possible existing people/i);
    await user.click(within(dialog).getByRole("button", { name: /Use existing: Tony Caccia/i }));
    await waitFor(() => expect(onChange).toHaveBeenCalledWith("ex1"));
    expect(H.createPerson).not.toHaveBeenCalled();  // reused, not duplicated
  });

  it("cancelling creates nothing", async () => {
    H.listPeople.mockResolvedValue([]);
    const user = userEvent.setup();
    render(<Harness onChange={() => {}} />);
    const dialog = await openCreate(user, "Nobody");
    await user.click(within(dialog).getByRole("button", { name: /Cancel/i }));
    expect(H.createPerson).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });
});
