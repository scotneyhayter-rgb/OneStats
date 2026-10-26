// @vitest-environment jsdom
/** Appearance gallery (theme selection + persistence) and Club Theme Editor permissions. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const api = vi.hoisted(() => ({
  getBranding: vi.fn(async () => ({ branding: { primary_colour: "#123456" }, resolved: {}, published: {} })),
  brandingLogoObjectUrl: vi.fn(async () => null),
  setBranding: vi.fn(),
  uploadBrandingLogo: vi.fn(),
  deleteBrandingLogo: vi.fn(),
}));
vi.mock("../../lib/api", () => ({ api, ApiError: class extends Error {} }));
vi.mock("../../lib/workspace-context", () => ({
  useWorkspace: () => ({ current: { id: "ws1", name: "Test Club" } }),
}));

import { ThemeProvider } from "../../lib/theme";
import { Appearance } from "./Appearance";
import { ClubThemeEditor } from "./ClubTheme";

afterEach(() => { cleanup(); try { localStorage.clear(); } catch { /* ignore */ } });

describe("Appearance gallery", () => {
  it("shows all eight themes and persists the applied choice", async () => {
    render(<ThemeProvider><Appearance /></ThemeProvider>);
    for (const name of ["Traditional", "Modern", "Professional", "Test", "One Day", "T20", "Club", "OneStats"]) {
      expect(screen.getByText(name)).toBeTruthy();
    }
    // Select OneStats (the last "Select" button) then Apply.
    const selects = screen.getAllByRole("button", { name: "Select" });
    fireEvent.click(selects[selects.length - 1]);
    const apply = screen.getByText("Apply theme") as HTMLButtonElement;
    expect(apply.disabled).toBe(false);
    fireEvent.click(apply);
    await waitFor(() => expect(localStorage.getItem("onestats.skin")).toBe("onestats"));
    expect(document.documentElement.dataset.theme).toBe("onestats");
  });
});

describe("Club Theme Editor permissions", () => {
  it("is read-only for non-admins (no save control, colour inputs disabled)", async () => {
    const { container } = render(<ClubThemeEditor admin={false} />);
    await waitFor(() => expect(api.getBranding).toHaveBeenCalled());
    await waitFor(() => expect(screen.queryByText(/Loading/)).toBeNull());
    expect(screen.queryByText("Save club theme")).toBeNull();
    const colorInput = container.querySelector('input[type="color"]') as HTMLInputElement | null;
    expect(colorInput).not.toBeNull();
    expect(colorInput?.disabled).toBe(true);
  });

  it("lets admins see the save control", async () => {
    render(<ClubThemeEditor admin={true} />);
    await waitFor(() => expect(screen.getByText("Save club theme")).toBeTruthy());
    expect(screen.getByText("Regenerate from logo")).toBeTruthy();
  });
});
