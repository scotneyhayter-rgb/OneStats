import { PanelLeft, PanelLeftClose } from "lucide-react";
import type { ReactNode } from "react";
import { useLayout } from "../../lib/layout";
import { ThemeToggle } from "./ThemeToggle";
import { Sidebar } from "./Sidebar";

export function AppShell({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
}) {
  const { sidebarCollapsed, toggleSidebar } = useLayout();
  return (
    <div className="flex h-screen w-screen overflow-hidden bg-background text-foreground">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between gap-3 border-b border-border px-4 py-3 sm:px-6">
          <div className="flex min-w-0 items-center gap-2">
            <button
              type="button"
              onClick={toggleSidebar}
              aria-label={sidebarCollapsed ? "Expand navigation sidebar" : "Collapse navigation sidebar"}
              aria-pressed={sidebarCollapsed}
              title={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
              className="shrink-0 rounded-[var(--radius-app)] p-2 text-muted-foreground hover:bg-muted hover:text-foreground"
            >
              {sidebarCollapsed ? <PanelLeft className="h-4 w-4" aria-hidden /> : <PanelLeftClose className="h-4 w-4" aria-hidden />}
            </button>
            <div className="min-w-0">
              <h1 className="truncate text-lg font-semibold">{title}</h1>
              {subtitle && (
                <p className="truncate text-sm text-muted-foreground">{subtitle}</p>
              )}
            </div>
          </div>
          <div className="flex items-center gap-1">
            <ThemeToggle />
          </div>
        </header>
        <main className="min-h-0 flex-1 overflow-auto p-4 sm:p-6">{children}</main>
      </div>
    </div>
  );
}
