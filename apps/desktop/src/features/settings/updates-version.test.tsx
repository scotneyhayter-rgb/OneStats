// @vitest-environment jsdom
/** Updates & Version screen: versions, compatibility, honest fallback, the real Tauri updater path,
 * and the session-expired vs server-unreachable distinction. */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const { MockApiError } = vi.hoisted(() => {
  class MockApiError extends Error {
    status?: number;
    code?: string;
    constructor(message: string, status?: number, code?: string) {
      super(message);
      this.name = "ApiError";
      this.status = status;
      this.code = code;
    }
  }
  return { MockApiError };
});

const api = vi.hoisted(() => ({
  capability: vi.fn(async () => ({
    server_version: "1.0.0-beta.3", api_version: 1, channel: "stable",
    database: { current_head: "0058_update_system", current_level: 58, expected_head: "0058_update_system", expected_level: 58, up_to_date: true, migration_pending: false },
    min_desktop_version: "1.0.0-beta.1", max_desktop_version: null, min_server_for_desktop: "1.0.0-beta.1",
    maintenance: { mode: false, message: null },
  })),
  updatesCompatibility: vi.fn(async () => ({ status: "ok", can_operate: true, required_action: "none", message: "Compatible.", server_version: "1.0.0-beta.3", api_version: 1 })),
  systemUpdateCheck: vi.fn(async () => ({ configured: false, manifest_url: null as string | null, channel: "stable", server_version: "1.0.0-beta.3", note: "No update service is configured on this server." as string | null })),
}));
vi.mock("../../lib/api", () => ({ api, ApiError: MockApiError }));
vi.mock("../../lib/auth", () => ({ useAuth: () => ({ user: { is_super_admin: false, username: "u" } }) }));

// isTauri() is mutable per test: false = browser/dev shell, true = inside the real app.
const tauri = vi.hoisted(() => ({ inApp: false }));
vi.mock("@tauri-apps/api/core", () => ({ isTauri: () => tauri.inApp }));

const updater = vi.hoisted(() => ({ check: vi.fn() }));
const proc = vi.hoisted(() => ({ relaunch: vi.fn(async () => undefined) }));
vi.mock("@tauri-apps/plugin-updater", () => ({ check: updater.check }));
vi.mock("@tauri-apps/plugin-process", () => ({ relaunch: proc.relaunch }));

import { UpdatesVersion } from "./UpdatesVersion";

beforeEach(() => {
  tauri.inApp = false;
  updater.check.mockReset();
  proc.relaunch.mockClear();
  api.capability.mockClear();
  api.systemUpdateCheck.mockClear();
});
afterEach(cleanup);

describe("UpdatesVersion", () => {
  it("shows the installed versions and a no-service status after checking", async () => {
    render(<UpdatesVersion />);
    await waitFor(() => expect(api.capability).toHaveBeenCalled());
    await waitFor(() => expect(screen.getAllByText("1.0.0-beta.3").length).toBeGreaterThanOrEqual(2));
    await waitFor(() => expect(screen.getByText(/No update service is configured/i)).toBeTruthy());
  });

  it("surfaces a compatibility warning when the client is too old", async () => {
    api.updatesCompatibility.mockResolvedValueOnce({
      status: "desktop_too_old", can_operate: false, required_action: "update_desktop",
      message: "This OneStats app is older than the minimum supported version.", server_version: "1.0.0-beta.3", api_version: 1,
    });
    render(<UpdatesVersion />);
    await waitFor(() => expect(screen.getByText(/older than the minimum supported version/i)).toBeTruthy());
  });

  it("treats a 401 as an expired session, not an unreachable server", async () => {
    api.capability.mockRejectedValueOnce(new MockApiError("Invalid or expired session", 401, "unauthorized"));
    render(<UpdatesVersion />);
    await waitFor(() => expect(screen.getByText(/session has expired/i)).toBeTruthy());
    // The server IS reachable, so it must not be reported as unavailable.
    expect(screen.queryByText("unavailable")).toBeNull();
    expect(screen.getByText(/sign in required/i)).toBeTruthy();
  });

  it("reports a genuine server outage as unreachable", async () => {
    api.capability.mockRejectedValueOnce(new MockApiError("Request failed (503)", 503));
    render(<UpdatesVersion />);
    await waitFor(() => expect(screen.getByText(/server is currently unreachable/i)).toBeTruthy());
  });

  it("drives the Tauri updater when a release service is configured and an update is available", async () => {
    tauri.inApp = true;
    api.systemUpdateCheck.mockResolvedValue({ configured: true, manifest_url: "https://example/latest.json", channel: "stable", server_version: "1.0.0-beta.3", note: null });
    const downloadAndInstall = vi.fn(async () => undefined);
    updater.check.mockResolvedValue({ version: "1.0.0-beta.4", downloadAndInstall });
    render(<UpdatesVersion />);
    await waitFor(() => expect(screen.getByText(/Version 1\.0\.0-beta\.4 is available/i)).toBeTruthy());

    await userEvent.click(screen.getByRole("button", { name: /install & restart/i }));
    await waitFor(() => expect(downloadAndInstall).toHaveBeenCalled());
    await waitFor(() => expect(proc.relaunch).toHaveBeenCalled());
  });

  it("reports up to date when a service is configured but no newer release exists", async () => {
    tauri.inApp = true;
    api.systemUpdateCheck.mockResolvedValue({ configured: true, manifest_url: "https://example/latest.json", channel: "stable", server_version: "1.0.0-beta.3", note: null });
    updater.check.mockResolvedValue(null);
    render(<UpdatesVersion />);
    await waitFor(() => expect(screen.getByText(/OneStats is up to date/i)).toBeTruthy());
  });
});
