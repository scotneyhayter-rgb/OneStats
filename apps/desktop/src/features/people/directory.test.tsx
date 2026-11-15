// @vitest-environment jsdom
/** People Directory: searches server-side from the ?q= URL param (so aliases/initials match and the
 * place is restored on Back), and opens a profile via router navigation. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

const H = vi.hoisted(() => ({ listPeople: vi.fn() }));
vi.mock("../../lib/api", () => ({ ApiError: class ApiError extends Error {}, api: H }));
vi.mock("../manage/_shared", () => ({
  useManage: () => ({ workspaceId: "w1", canManage: true }),
  NoWorkspace: () => <div>no ws</div>,
  Field: ({ children }: { children: import("react").ReactNode }) => <div>{children}</div>,
  humanise: (s: string) => s,
}));
vi.mock("../../lib/toast", () => ({ useToast: () => ({ success: vi.fn() }) }));
vi.mock("../../components/layout/AppShell", () => ({
  AppShell: ({ children }: { children: import("react").ReactNode }) => <div>{children}</div>,
}));

import { PeopleManagement } from "./PeopleManagement";

afterEach(cleanup);

describe("People directory", () => {
  it("searches server-side from the ?q= URL param", async () => {
    H.listPeople.mockResolvedValue([
      { id: "p1", display_name: "Scotney Hayter", status: "active", is_junior: false, merged_into_id: null },
    ]);
    render(<MemoryRouter initialEntries={["/people?q=hay"]}><PeopleManagement /></MemoryRouter>);
    await waitFor(() => expect(H.listPeople).toHaveBeenCalledWith("w1", expect.objectContaining({ search: "hay" })));
    await screen.findByText("Scotney Hayter");
  });
});
