import { Building2, Info, LogOut } from "lucide-react";
import { useState } from "react";
import { NavLink } from "react-router-dom";
import { MANAGEMENT_SECTIONS, NAV_SECTIONS, type NavSection } from "../../app/navigation";
import onestatsIcon from "../../assets/onestats-icon.png";
import onestatsLogo from "../../assets/onestats-logo.png";
import { useAuth } from "../../lib/auth";
import { useLayout } from "../../lib/layout";
import { APP_VERSION, PHASE } from "../../lib/version";
import { can } from "../../lib/permissions";
import { useWorkspace } from "../../lib/workspace-context";
import { cn } from "../../lib/utils";
import { Modal } from "../ui/dialog";
import { WorkspaceSwitcher } from "./WorkspaceSwitcher";

export function Sidebar() {
  const { user, logout } = useAuth();
  const { current } = useWorkspace();
  const { sidebarCollapsed } = useLayout();
  const collapsed = sidebarCollapsed;
  const [aboutOpen, setAboutOpen] = useState(false);

  // Role-based nav gating: a section with a `perm` shows only when the user holds it in the
  // selected workspace (Super Admin holds all). Sections without a `perm` are always visible.
  // The backend independently enforces every action — hiding a link is convenience, not security.
  const visible = (s: NavSection) => !s.perm || can(user, current, s.perm);

  const navItem = (s: { path: string; label: string; icon: NavSection["icon"] }) => {
    const Icon = s.icon;
    return (
      <li key={s.path}>
        <NavLink
          to={s.path}
          title={collapsed ? s.label : undefined}
          className={({ isActive }) =>
            cn(
              "flex items-center gap-3 rounded-[var(--radius-app)] py-2 text-sm transition-colors",
              collapsed ? "justify-center px-0" : "px-3",
              isActive
                ? "bg-sidebar-active text-sidebar-foreground"
                : "text-sidebar-muted hover:bg-sidebar-active hover:text-sidebar-foreground",
            )
          }
        >
          <Icon className="h-4 w-4 shrink-0" aria-hidden />
          {!collapsed && <span className="truncate">{s.label}</span>}
          {collapsed && <span className="sr-only">{s.label}</span>}
        </NavLink>
      </li>
    );
  };

  return (
    <nav
      aria-label="Primary"
      className={cn(
        "flex h-full shrink-0 flex-col bg-sidebar text-sidebar-foreground transition-[width] duration-150",
        collapsed ? "w-16" : "w-60",
      )}
    >
      <div className={cn("flex items-center gap-2 py-5", collapsed ? "justify-center px-0" : "px-5")}>
        {/* Official OneStats circular icon (supplied artwork, unmodified). It has a white
            background, so it sits on a white plate to read clearly on the dark sidebar. */}
        <img
          src={onestatsIcon}
          alt="OneStats"
          className="h-8 w-8 shrink-0 rounded-[var(--radius-app)] bg-white object-contain p-0.5"
        />
        {!collapsed && (
          <div className="leading-tight">
            <div className="text-sm font-semibold">OneStats</div>
            <div className="text-[11px] text-sidebar-muted">Cricket Statistics</div>
          </div>
        )}
      </div>

      {!collapsed && <WorkspaceSwitcher />}

      <ul className="min-h-0 flex-1 space-y-1 overflow-y-auto px-3 sidebar-scroll">
        {navItem({ path: "/workspaces", label: "My Workspaces", icon: Building2 })}
        {NAV_SECTIONS.filter(visible).map(navItem)}

        {MANAGEMENT_SECTIONS.some(visible) && (
          <>
            {!collapsed && (
              <li className="px-3 pb-1 pt-4 text-[11px] font-medium uppercase tracking-wide text-sidebar-muted">
                Club Management
              </li>
            )}
            {collapsed && <li className="my-2 border-t border-[color:var(--sidebar-active)]" aria-hidden />}
            {MANAGEMENT_SECTIONS.filter(visible).map(navItem)}
          </>
        )}
      </ul>

      {user && (
        <div className="border-t border-[color:var(--sidebar-active)] px-3 py-3">
          <div className={cn("flex items-center gap-2", collapsed ? "justify-center" : "justify-between")}>
            {!collapsed && (
              <div className="min-w-0">
                <div className="truncate text-sm">{user.display_name ?? user.username}</div>
                <div className="truncate text-[11px] text-sidebar-muted">
                  {user.is_super_admin ? "Super Administrator" : user.username}
                </div>
              </div>
            )}
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

      <div className={cn("py-3", collapsed ? "flex justify-center px-0" : "px-5")}>
        <button
          onClick={() => setAboutOpen(true)}
          title="About OneStats"
          aria-label="About OneStats"
          className={cn(
            "flex items-center gap-2 rounded-[var(--radius-app)] text-[11px] text-sidebar-muted hover:text-sidebar-foreground",
            collapsed ? "justify-center p-2 hover:bg-sidebar-active" : "",
          )}
        >
          <Info className="h-3.5 w-3.5 shrink-0" aria-hidden />
          {!collapsed && <span>About · v{APP_VERSION} · {PHASE}</span>}
        </button>
      </div>

      <Modal open={aboutOpen} title="About OneStats" onClose={() => setAboutOpen(false)}>
        <div className="flex flex-col items-center gap-4 text-center">
          <div className="w-full rounded-[var(--radius-app)] border border-border bg-white p-4">
            <img src={onestatsLogo} alt="OneStats — Cricket Statistics Made Simple" className="mx-auto h-auto w-full max-w-[360px]" />
          </div>
          <p className="text-sm text-muted-foreground">
            Discover the history · Understand the numbers · Celebrate the achievements.
          </p>
          <div className="text-xs text-muted-foreground">
            <div>Version {APP_VERSION}</div>
            <div>{PHASE}</div>
          </div>
        </div>
      </Modal>
    </nav>
  );
}
