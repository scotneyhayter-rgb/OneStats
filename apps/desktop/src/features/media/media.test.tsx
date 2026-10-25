// @vitest-environment jsdom
/**
 * Media Archive page (Phase 11): loads the real media library + providers and shows integrity.
 * Drives the component with a mocked API.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

const H = vi.hoisted(() => ({
  mediaAssets: vi.fn(),
  mediaProviders: vi.fn(),
  mediaHeritageCollections: vi.fn(),
  mediaVerify: vi.fn(),
  mediaThumbnailObjectUrl: vi.fn(),
}));

vi.mock("../manage/_shared", () => ({ useManage: () => ({ workspaceId: "w1" }), NoWorkspace: () => <div>no ws</div> }));
vi.mock("../../lib/api", () => ({ ApiError: class ApiError extends Error {}, api: H }));
vi.mock("../../components/layout/AppShell", () => ({
  AppShell: ({ children }: { children: import("react").ReactNode }) => <div>{children}</div>,
}));

import { MediaArchive } from "./MediaArchive";

function setup() {
  H.mediaAssets.mockResolvedValue([
    { id: "a1", storage_provider: "internal", storage_locator: "m.png", original_filename: "team.png",
      content_type: "image/png", file_bytes: 2048, sha256: "x", kind: "photograph", title: "1891 team",
      description: null, copyright_status: null, licence: null, attribution: null, visibility: "workspace",
      publication_eligible: false, sensitive: false, junior_protected: false, thumbnail_ref: null,
      created_at: "2026-10-25" },
  ]);
  H.mediaProviders.mockResolvedValue([
    { name: "internal", available: true, default: true, note: "OneStats-managed storage" },
    { name: "external", available: true, default: false, note: "Reference" },
    { name: "onevault", available: false, default: false, note: "No verified OneVault API configured" },
  ]);
  H.mediaHeritageCollections.mockResolvedValue([]);
  H.mediaVerify.mockResolvedValue({ total: 1, verified_ok: 1, missing: [], mismatch: [], unverifiable: [], ok: true });
}

afterEach(cleanup);

describe("Media Archive page", () => {
  it("shows the real media library", async () => {
    setup();
    render(<MemoryRouter><MediaArchive /></MemoryRouter>);
    await screen.findByText("1891 team");
    expect(screen.getByText(/Media library/)).toBeTruthy();
  });

  it("shows storage providers incl. OneVault unavailable", async () => {
    setup();
    const user = userEvent.setup();
    render(<MemoryRouter><MediaArchive /></MemoryRouter>);
    await screen.findByText("1891 team");
    await user.click(screen.getByRole("button", { name: /Storage & Integrity/i }));
    await screen.findByText("onevault");
    expect(screen.getAllByText("unavailable").length).toBeGreaterThan(0);
  });
});
