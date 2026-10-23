import { Building2, LogOut } from "lucide-react";
import { NavLink } from "react-router-dom";
import { NAV_SECTIONS } from "../../app/navigation";
import { useAuth } from "../../lib/auth";
import { APP_VERSION, PHASE } from "../../lib/version";
import { cn } from "../../lib/utils";
import { WorkspaceSwitcher } from "./WorkspaceSwitcher";

export function Sidebar() {
  const { user, logout } = useAuth();
  return (
    <nav
      aria-label="Primary"
      className="flex h-full w-60 shrink-0 flex-col bg-sidebar text-sidebar-foreground"
    >
      <div className="flex items-center gap-2 px-5 py-5">
        <div
          aria-hidden
          className="flex h-8 w-8 items-center justify-center rounded-[var(--radius-app)] bg-brand font-bold text-brand-foreground"
        >
          1
        </div>
        <div className="leading-tight">
          <div className="text-sm font-semibold">OneStats</div>
          <div className="text-[11px] text-sidebar-muted">Cricket Statistics</div>
        </div>
      </div>

      <WorkspaceSwitcher />

      <ul className="flex-1 space-y-1 px-3">
        <li>
          <NavLink
            to="/workspaces"
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 rounded-[var(--radius-app)] px-3 py-2 text-sm transition-colors",
                isActive
                  ? "bg-sidebar-active text-sidebar-foreground"
                  : "text-sidebar-muted hover:bg-sidebar-active hover:text-sidebar-foreground",
              )
            }
          >
            <Building2 className="h-4 w-4 shrink-0" aria-hidden />
            <span>My Workspaces</span>
          </NavLink>
        </li>
        {NAV_SECTIONS.map((s) => {
          const Icon = s.icon;
          return (
            <li key={s.key}>
              <NavLink
                to={s.path}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-3 rounded-[var(--radius-app)] px-3 py-2 text-sm transition-colors",
                    isActive
                      ? "bg-sidebar-active text-sidebar-foreground"
                      : "text-sidebar-muted hover:bg-sidebar-active hover:text-sidebar-foreground",
                  )
                }
              >
                <Icon className="h-4 w-4 shrink-0" aria-hidden />
                <span>{s.label}</span>
              </NavLink>
            </li>
          );
        })}
      </ul>

      {user && (
        <div className="border-t border-[color:var(--sidebar-active)] px-3 py-3">
          <div className="flex items-center justify-between gap-2">
            <div className="min-w-0">
              <div className="truncate text-sm">{user.display_name ?? user.username}</div>
              <div className="truncate text-[11px] text-sidebar-muted">
                {user.is_super_admin ? "Super Administrator" : user.username}
              </div>
            </div>
            <button
              onClick={() => void logout()}
              aria-label="Sign out"
              title="Sign out"
              className="rounded-[var(--radius-app)] p-2 text-sidebar-muted hover:bg-sidebar-active hover:text-sidebar-foreground"
            >
              <LogOut className="h-4 w-4" aria-hidden />
            </button>
          </div>
        </div>
      )}

      <div className="px-5 py-3 text-[11px] text-sidebar-muted">
        <div>v{APP_VERSION}</div>
        <div>{PHASE}</div>
      </div>
    </nav>
  );
}
