import { NavLink } from "react-router-dom";
import { NAV_SECTIONS } from "../../app/navigation";
import { APP_VERSION, PHASE } from "../../lib/version";
import { cn } from "../../lib/utils";

export function Sidebar() {
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

      <ul className="flex-1 space-y-1 px-3">
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

      <div className="px-5 py-4 text-[11px] text-sidebar-muted">
        <div>v{APP_VERSION}</div>
        <div>{PHASE}</div>
      </div>
    </nav>
  );
}
