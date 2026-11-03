// @vitest-environment jsdom
/** Contextual "Search the Internet" button: permission gating + start-then-open behaviour. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const navigate = vi.fn();
const H = vi.hoisted(() => ({ researchStartInternetSearch: vi.fn() }));

const AUTH = vi.hoisted(() => ({ user: { id: "u1", is_super_admin: false } as { id: string; is_super_admin: boolean } }));
const WS = vi.hoisted(() => ({ current: { id: "w1", name: "RMCC", permissions: ["research.manage"] } as { id: string; name: string; permissions: string[] } | null }));

vi.mock("react-router-dom", () => ({ useNavigate: () => navigate }));
vi.mock("../../lib/auth", () => ({ useAuth: () => AUTH }));
vi.mock("../../lib/workspace-context", () => ({ useWorkspace: () => WS }));
vi.mock("../../lib/api", () => ({ ApiError: class ApiError extends Error {}, api: H }));

import { ResearchThisButton } from "./ResearchThisButton";

afterEach(() => { cleanup(); navigate.mockReset(); H.researchStartInternetSearch.mockReset(); });

describe("ResearchThisButton", () => {
  it("starts a job with context then opens Discover Records", async () => {
    AUTH.user = { id: "u1", is_super_admin: false };
    WS.current = { id: "w1", name: "RMCC", permissions: ["research.manage"] };
    H.researchStartInternetSearch.mockResolvedValue({ id: "j1" });
    const user = userEvent.setup();
    render(<ResearchThisButton query="Rhymney v Moyston 1905" context={{ club: "Rhymney" }} />);
    await user.click(screen.getByRole("button", { name: /Search the Internet/i }));
    await waitFor(() => expect(H.researchStartInternetSearch).toHaveBeenCalledWith(
      "w1", { query: "Rhymney v Moyston 1905", context: { club: "Rhymney" }, depth: "standard" }));
    expect(navigate).toHaveBeenCalledWith("/manage/research?discover=1");
  });

  it("renders nothing without research.manage", () => {
    AUTH.user = { id: "u1", is_super_admin: false };
    WS.current = { id: "w1", name: "RMCC", permissions: [] };
    const { container } = render(<ResearchThisButton query="x" />);
    expect(container.firstChild).toBeNull();
  });
});
