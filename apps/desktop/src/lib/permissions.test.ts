import { describe, expect, it } from "vitest";
import type { User, Workspace } from "./api";
import { canManage } from "./permissions";

const sa: User = { id: "1", username: "sa", display_name: null, is_super_admin: true };
const plain: User = { id: "2", username: "u", display_name: null, is_super_admin: false };

function ws(roles: string[]): Workspace {
  return { id: "w", name: "W", short_name: null, type: "club", status: "active", roles };
}

describe("canManage", () => {
  it("is false with no user", () => {
    expect(canManage(null, ws(["workspace_admin"]))).toBe(false);
  });
  it("is true for the super administrator regardless of workspace", () => {
    expect(canManage(sa, null)).toBe(true);
  });
  it("is true for a workspace administrator", () => {
    expect(canManage(plain, ws(["workspace_admin"]))).toBe(true);
  });
  it("is false for a viewer", () => {
    expect(canManage(plain, ws(["viewer"]))).toBe(false);
  });
  it("is false when no workspace is selected for a non-super user", () => {
    expect(canManage(plain, null)).toBe(false);
  });
});
