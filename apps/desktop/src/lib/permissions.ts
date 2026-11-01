import type { User, Workspace } from "./api";

/**
 * Permission-aware UI gating. The backend is the real authority — every mutating endpoint is
 * guarded by require_permission and returns 403 — so this only decides whether to *show*
 * controls and navigation. Permissions are resolved by the server per workspace and returned in
 * `workspace.permissions`; the client never invents or escalates them. Switching which dashboard
 * you VIEW never changes these — they always come from the selected workspace's membership.
 */

/** Canonical display names for the built-in roles (the six core roles + the legacy People Manager). */
export const ROLE_LABELS: Record<string, string> = {
  super_admin: "Super Admin",
  workspace_admin: "Organisation Admin",
  researcher: "Researcher",
  scorecard_entry: "Scorecard Editor",
  reviewer: "Data Verifier",
  viewer: "Viewer / Analyst",
  people_manager: "People Manager",
};

export function roleLabel(key: string): string {
  return ROLE_LABELS[key] ?? key;
}

export function roleLabels(keys: string[] | undefined): string {
  return (keys ?? []).map(roleLabel).join(", ");
}

/** The user's effective permission set in the given workspace. */
export function workspacePermissions(user: User | null, ws: Workspace | null): Set<string> {
  if (!user || !ws) return new Set();
  return new Set(ws.permissions ?? []);
}

/** Does the user hold `perm` in this workspace? Super Admin holds everything (the server also
 * attaches the full catalogue, so this is belt-and-braces). */
export function can(user: User | null, ws: Workspace | null, perm: string): boolean {
  if (!user) return false;
  if (user.is_super_admin) return true;
  return (ws?.permissions ?? []).includes(perm);
}

/** Holds ANY of the listed permissions. */
export function canAny(user: User | null, ws: Workspace | null, perms: string[]): boolean {
  if (!user) return false;
  if (user.is_super_admin) return true;
  const held = new Set(ws?.permissions ?? []);
  return perms.some((p) => held.has(p));
}

/** Can the user manage workspace-level administration (Organisation Admin / Super Admin)? */
export function canManage(user: User | null, workspace: Workspace | null): boolean {
  return can(user, workspace, "workspace.manage");
}

/** A Super Admin operating in a workspace where they hold no ordinary role — i.e. acting purely
 * as a platform administrator ("Super Admin — Managing [Workspace]"). */
export function isActingAsSuperAdmin(user: User | null, ws: Workspace | null): boolean {
  if (!user?.is_super_admin || !ws) return false;
  const roles = ws.roles ?? [];
  return roles.length === 0 || (roles.length === 1 && roles[0] === "super_admin");
}
