// @vitest-environment jsdom
/** Updates & Version screen: shows versions, compatibility and a working manual check. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";

const api = vi.hoisted(() => ({
  capability: vi.fn(async () => ({
    server_version: "1.0.0-beta.1", api_version: 1, channel: "stable",
    database: { current_head: "0058_update_system", current_level: 58, expected_head: "0058_update_system", expected_level: 58, up_to_date: true, migration_pending: false },
    min_desktop_version: "1.0.0-beta.1", max_desktop_version: null, min_server_for_desktop: "1.0.0-beta.1",
    maintenance: { mode: false, message: null },
  })),
  updatesCompatibility: vi.fn(async () => ({ status: "ok", can_operate: true, required_action: "none", message: "Compatible.", server_version: "1.0.0-beta.1", api_version: 1 })),
  systemUpdateCheck: vi.fn(async () => ({ configured: false, manifest_url: null, channel: "stable", server_version: "1.0.0-beta.1", note: "No update service is configured on this server." })),
}));
vi.mock("../../lib/api", () => ({ api, ApiError: class extends Error {} }));
vi.mock("../../lib/auth", () => ({ useAuth: () => ({ user: { is_super_admin: false, username: "u" } }) }));

import { UpdatesVersion } from "./UpdatesVersion";

afterEach(cleanup);

describe("UpdatesVersion", () => {
  it("shows the installed versions and a no-service status after checking", async () => {
    render(<UpdatesVersion />);
    await waitFor(() => expect(api.capability).toHaveBeenCalled());
    // Desktop + server versions rendered.
    await waitFor(() => expect(screen.getAllByText("1.0.0-beta.1").length).toBeGreaterThanOrEqual(2));
    // Honest "no automatic update service" status (dev environment).
    await waitFor(() => expect(screen.getByText(/No update service is configured/i)).toBeTruthy());
  });

  it("surfaces a compatibility warning when the client is too old", async () => {
    api.updatesCompatibility.mockResolvedValueOnce({
      status: "desktop_too_old", can_operate: false, required_action: "update_desktop",
      message: "This OneStats app is older than the minimum supported version.", server_version: "1.0.0-beta.1", api_version: 1,
    });
    render(<UpdatesVersion />);
    await waitFor(() => expect(screen.getByText(/older than the minimum supported version/i)).toBeTruthy());
  });
});
