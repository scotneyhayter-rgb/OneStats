import { describe, expect, it } from "vitest";
import type { User, Workspace } from "./api";
import { can, canAny, canManage, isActingAsSuperAdmin, roleLabel, roleLabels } from "./permissions";

const sa: User = { id: "1", username: "sa", display_name: null, is_super_admin: true };
const plain: User = { id: "2", username: "u", display_name: null, is_super_admin: false };

function ws(roles: string[], permissions: string[]): Workspace {
  return { id: "w", name: "W", short_name: null, type: "club", status: "active", roles, permissions };
}

const adminWs = ws(["workspace_admin"], ["workspace.manage", "match.view", "match.manage", "scorecard.approve"]);
const viewerWs = ws(["viewer"], ["match.view", "ask.query", "export"]);
const editorWs = ws(["scorecard_entry"], ["match.view", "match.manage", "ask.query"]);

describe("canManage", () => {
  it("is false with no user", () => expect(canManage(null, adminWs)).toBe(false));
  it("is true for the super administrator regardless of workspace", () => expect(canManage(sa, null)).toBe(true));
  it("is true for a workspace administrator", () => expect(canManage(plain, adminWs)).toBe(true));
  it("is false for a viewer", () => expect(canManage(plain, viewerWs)).toBe(false));
  it("is false when no workspace is selected for a non-super user", () => expect(canManage(plain, null)).toBe(false));
});

describe("can / canAny", () => {
  it("grants the super admin everything", () => expect(can(sa, viewerWs, "workspace.manage")).toBe(true));
  it("reflects the workspace permission set", () => {
    expect(can(plain, editorWs, "match.manage")).toBe(true);
    expect(can(plain, editorWs, "scorecard.approve")).toBe(false);
  });
  it("canAny is true when any permission is held", () => {
    expect(canAny(plain, viewerWs, ["scorecard.approve", "match.view"])).toBe(true);
    expect(canAny(plain, viewerWs, ["scorecard.approve", "research.manage"])).toBe(false);
  });
  it("never escalates from role switching — only the workspace's own permissions count", () => {
    // a viewer in this workspace cannot approve, even though they are an admin elsewhere
    expect(can(plain, viewerWs, "scorecard.approve")).toBe(false);
  });
});

describe("role labels", () => {
  it("maps built-in keys to canonical names", () => {
    expect(roleLabel("workspace_admin")).toBe("Organisation Admin");
    expect(roleLabel("scorecard_entry")).toBe("Scorecard Editor");
    expect(roleLabel("reviewer")).toBe("Data Verifier");
  });
  it("passes unknown keys through", () => expect(roleLabel("custom_x")).toBe("custom_x"));
  it("joins multiple role labels", () => expect(roleLabels(["viewer", "researcher"])).toBe("Viewer / Analyst, Researcher"));
});

describe("isActingAsSuperAdmin", () => {
  it("is true when a super admin has no ordinary role in the workspace", () =>
    expect(isActingAsSuperAdmin(sa, ws([], []))).toBe(true));
  it("is true when the only role is the synthetic super_admin tag", () =>
    expect(isActingAsSuperAdmin(sa, ws(["super_admin"], []))).toBe(true));
  it("is false when the super admin is also an ordinary member", () =>
    expect(isActingAsSuperAdmin(sa, ws(["workspace_admin"], []))).toBe(false));
  it("is false for a non-super user", () => expect(isActingAsSuperAdmin(plain, ws([], []))).toBe(false));
});
