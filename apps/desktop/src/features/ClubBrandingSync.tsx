import { useEffect } from "react";
import { api } from "../lib/api";
import { applyClubVars } from "../lib/branding-runtime";
import { useWorkspace } from "../lib/workspace-context";

/**
 * Applies the current workspace's saved club colours to the Club theme's CSS variables, app-wide.
 * Re-runs whenever the active workspace changes, so switching clubs loads the correct colours and
 * never carries one workspace's branding into another. Renders nothing.
 */
export function ClubBrandingSync() {
  const { current } = useWorkspace();
  const wsId = current?.id ?? null;
  useEffect(() => {
    let cancelled = false;
    if (!wsId) {
      applyClubVars(null);
      return;
    }
    void (async () => {
      try {
        const res = await api.getBranding(wsId);
        if (cancelled) return;
        const b = res.branding;
        applyClubVars(b ? {
          primary: b.primary_colour, secondary: b.secondary_colour, third: b.third_colour,
          fourth: b.fourth_colour, accent: b.accent_colour,
        } : null);
      } catch {
        if (!cancelled) applyClubVars(null);
      }
    })();
    return () => { cancelled = true; };
  }, [wsId]);
  return null;
}
