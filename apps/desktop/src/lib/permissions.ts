import type { User, Workspace } from "./api";

/**
 * Permission-aware UI gating. The backend is the real authority (every mutating endpoint is
 * guarded by require_permission and returns 403), so this only decides whether to *show*
 * management controls. The Phase 4 manage permissions (organisation.manage, venue.manage,
 * competition.manage) are all granted to the Super and Workspace Administrator roles, so a
 * single capability check is sufficient for the management UI.
 */
const MANAGER_ROLES = new Set(["super_admin", "workspace_admin"]);

export function canManage(user: User | null, workspace: Workspace | null): boolean {
  if (!user) return false;
  if (user.is_super_admin) return true;
  return (workspace?.roles ?? []).some((r) => MANAGER_ROLES.has(r));
}
