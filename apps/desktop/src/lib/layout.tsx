/**
 * App-wide layout state (Stage 7 responsive standard).
 *
 * Holds the collapsible-sidebar state so any screen can collapse/expand the primary navigation
 * (used by the header toggle and by the scorecard Focus Mode). State is kept in React (survives
 * window resizing and navigation) and mirrored to localStorage as a per-viewer convenience.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

interface LayoutState {
  sidebarCollapsed: boolean;
  setSidebarCollapsed: (v: boolean) => void;
  toggleSidebar: () => void;
}

const LayoutContext = createContext<LayoutState | null>(null);
const KEY = "onestats.sidebarCollapsed";

export function LayoutProvider({ children }: { children: ReactNode }) {
  const [sidebarCollapsed, setCollapsed] = useState<boolean>(() => {
    try {
      return localStorage.getItem(KEY) === "1";
    } catch {
      return false;
    }
  });

  const setSidebarCollapsed = useCallback((v: boolean) => {
    setCollapsed(v);
    try {
      localStorage.setItem(KEY, v ? "1" : "0");
    } catch {
      /* storage unavailable — in-memory state still works */
    }
  }, []);

  const toggleSidebar = useCallback(() => setSidebarCollapsed(!sidebarCollapsed), [sidebarCollapsed, setSidebarCollapsed]);

  // Keep the state when the window resizes (no automatic collapse that would surprise the user).
  useEffect(() => {
    /* intentionally empty: state is user-driven and resize-stable */
  }, []);

  const value = useMemo(
    () => ({ sidebarCollapsed, setSidebarCollapsed, toggleSidebar }),
    [sidebarCollapsed, setSidebarCollapsed, toggleSidebar],
  );
  return <LayoutContext.Provider value={value}>{children}</LayoutContext.Provider>;
}

export function useLayout(): LayoutState {
  const ctx = useContext(LayoutContext);
  if (!ctx) return { sidebarCollapsed: false, setSidebarCollapsed: () => {}, toggleSidebar: () => {} };
  return ctx;
}
