// @vitest-environment jsdom
/**
 * API & Integrations page: lists providers with status, adds a credential, and tests the connection —
 * and never reveals a stored secret. Drives the component with a mocked API.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

const H = vi.hoisted(() => ({
  integrationProviders: vi.fn(), integrationCredentials: vi.fn(), integrationAudit: vi.fn(),
  integrationCreate: vi.fn(), integrationTest: vi.fn(), integrationRotate: vi.fn(),
  integrationRevoke: vi.fn(), integrationSetEnabled: vi.fn(),
}));

vi.mock("../manage/_shared", () => ({
  useManage: () => ({ workspaceId: "w1", canManage: true }),
  NoWorkspace: () => <div>no ws</div>,
}));
vi.mock("../../lib/api", () => ({ ApiError: class ApiError extends Error {}, api: H }));
vi.mock("../../components/layout/AppShell", () => ({
  AppShell: ({ children }: { children: import("react").ReactNode }) => <div>{children}</div>,
}));

import { Integrations } from "./Integrations";

const PLAYHQ = {
  id: "playhq", name: "PlayHQ", testable: true, custom_url: false, notes: "PlayHQ public API.",
  secret_fields: [{ key: "api_key", label: "API key (Client ID)", required: true }],
  config_fields: [{ key: "org_id", label: "Organisation ID", default: null, required: true },
                  { key: "tenant", label: "Tenant (e.g. ca)", default: "ca", required: true }],
};

function setup(creds: unknown[] = []) {
  H.integrationProviders.mockResolvedValue([PLAYHQ]);
  H.integrationCredentials.mockResolvedValue(creds);
  H.integrationAudit.mockResolvedValue([]);
  H.integrationCreate.mockResolvedValue({ id: "c1", provider: "playhq", status: "active" });
  H.integrationTest.mockResolvedValue({ id: "c1", provider: "playhq", status: "active", test_ok: true });
}

afterEach(cleanup);

describe("API & Integrations page", () => {
  it("lists a provider as not configured and reassures that secrets stay hidden", async () => {
    setup();
    render(<MemoryRouter><Integrations /></MemoryRouter>);
    await screen.findByText("PlayHQ");
    expect(screen.getByText("Not configured")).toBeTruthy();
    expect(screen.getByText(/never shown here/i)).toBeTruthy();   // security assurance
  });

  it("adds a credential with the provider's secret + config fields", async () => {
    setup();
    const user = userEvent.setup();
    render(<MemoryRouter><Integrations /></MemoryRouter>);
    await screen.findByText("PlayHQ");

    await user.click(screen.getByRole("button", { name: /Add credential/i }));
    // the secret field is a password input (never rendered as readable text)
    const secret = await screen.findByPlaceholderText(/never displayed again/i) as HTMLInputElement;
    expect(secret.type).toBe("password");
    await user.type(secret, "SECRET-KEY-123");
    await user.type(screen.getByLabelText(/Organisation ID/i), "org-99");

    await user.click(screen.getByRole("button", { name: /Save credential/i }));
    await waitFor(() => expect(H.integrationCreate).toHaveBeenCalledWith("w1", {
      provider: "playhq", label: "", secrets: { api_key: "SECRET-KEY-123" },
      config: { org_id: "org-99", tenant: "ca" },
    }));
  });

  it("shows a configured credential as Connected without revealing the secret, and tests it", async () => {
    setup([{
      id: "c1", provider: "playhq", label: "", enabled: true, status: "active",
      config: { org_id: "org-99", tenant: "ca" }, has_secret: true, last_test_ok: true,
      last_test_at: null, last_test_message: "Connected — PlayHQ returned data.", last_success_at: null, created_at: null,
    }]);
    const user = userEvent.setup();
    render(<MemoryRouter><Integrations /></MemoryRouter>);
    await screen.findByText("Connected");
    expect(screen.getByText(/Secret stored securely/i)).toBeTruthy();
    // the secret value itself is never present in the DOM
    expect(screen.queryByText(/SECRET/)).toBeNull();

    await user.click(screen.getByRole("button", { name: /Test connection/i }));
    await waitFor(() => expect(H.integrationTest).toHaveBeenCalledWith("w1", "c1"));
  });
});
