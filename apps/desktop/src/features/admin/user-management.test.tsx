// @vitest-environment jsdom
/** User Management (Super Admin): gated, lists users, creates with a one-time temp password. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const H = vi.hoisted(() => ({ usersList: vi.fn(), invitationsList: vi.fn(), userCreate: vi.fn() }));
const AUTH = vi.hoisted(() => ({ user: { is_super_admin: true } as { is_super_admin: boolean } }));
vi.mock("../../lib/auth", () => ({ useAuth: () => AUTH }));
vi.mock("../../lib/api", () => ({ ApiError: class ApiError extends Error {}, api: H }));
vi.mock("../../components/layout/AppShell", () => ({
  AppShell: ({ children }: { children: import("react").ReactNode }) => <div>{children}</div>,
}));

import { UserManagement } from "./UserManagement";

afterEach(cleanup);

describe("UserManagement", () => {
  it("gates non-super-admins", () => {
    AUTH.user = { is_super_admin: false };
    render(<UserManagement />);
    expect(screen.getByText(/System \(Super\) Administrators/)).toBeTruthy();
    AUTH.user = { is_super_admin: true };
  });

  it("lists users and creates one with a one-time temp password", async () => {
    AUTH.user = { is_super_admin: true };
    H.usersList.mockResolvedValue([
      { id: "u1", username: "root", display_name: "Root", status: "active", is_super_admin: true, must_change_password: false, last_login_at: null, created_at: null }]);
    H.invitationsList.mockResolvedValue([]);
    H.userCreate.mockResolvedValue({ user_id: "u2", username: "newbie", temp_password: "Temp123abcd", temp_password_expires_at: "2026-10-29" });

    render(<UserManagement />);
    await waitFor(() => expect(screen.getByText("root")).toBeTruthy());

    fireEvent.change(screen.getByPlaceholderText("newuser"), { target: { value: "newbie" } });
    fireEvent.click(screen.getByText("Create with temp password"));
    await waitFor(() => expect(screen.getByText(/Temp123abcd/)).toBeTruthy());
    expect(screen.getByText(/shown once/)).toBeTruthy();
  });
});
