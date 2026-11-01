import { ShieldAlert } from "lucide-react";
import { useLocation } from "react-router-dom";
import { useAuth } from "../../lib/auth";
import { isActingAsSuperAdmin } from "../../lib/permissions";
import { useWorkspace } from "../../lib/workspace-context";

/**
 * "Super Admin — Managing [Workspace]" banner (Part 6). Shown when a platform Super Administrator
 * is operating inside a workspace where they hold no ordinary membership — making it explicit that
 * they are acting as the platform administrator (NOT impersonating the Organisation Admin), and
 * that every action is recorded against their own identity. Hidden on the platform ("All
 * Workspaces") overview, which is not a single-workspace context.
 */
export function SuperAdminBanner() {
  const { user } = useAuth();
  const { current } = useWorkspace();
  const location = useLocation();

  if (location.pathname.startsWith("/platform")) return null;
  if (!isActingAsSuperAdmin(user, current) || !current) return null;

  return (
    <div
      role="status"
      className="flex items-center gap-2 border-b border-warning/40 bg-warning/10 px-4 py-1.5 text-xs text-warning sm:px-6"
    >
      <ShieldAlert className="h-3.5 w-3.5 shrink-0" aria-hidden />
      <span className="truncate">
        <b>Super Admin</b> — Managing <b>{current.name}</b>. Actions are recorded against your own account.
      </span>
    </div>
  );
}
