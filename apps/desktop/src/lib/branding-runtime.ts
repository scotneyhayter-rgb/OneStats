/**
 * Runtime application of a workspace's club branding to the Club theme.
 *
 * The Club theme's CSS tokens (themes.css) read `--club-*` custom properties with safe neutral
 * fallbacks. Here we turn a workspace's saved brand colours into those custom properties — including
 * accessible derived shades for sidebar, hover and dark-mode variants — and set/remove them on
 * <html>. Only the Club theme consumes these; every other theme (including the protected OneStats
 * theme) ignores them, so club colours never override another theme's identity.
 *
 * Workspace isolation: this reflects whatever branding the current workspace returns. Switching
 * workspace re-applies that workspace's colours (or clears them), never mixing the two.
 */
import { bestForeground, darken, isValidHex, lighten } from "./color";

export interface ClubColours {
  primary?: string | null;
  secondary?: string | null;
  third?: string | null;
  fourth?: string | null;
  accent?: string | null;
}

const VAR_NAMES = [
  "--club-primary", "--club-primary-dark", "--club-primary-foreground",
  "--club-accent", "--club-accent-dark",
  "--club-secondary", "--club-third", "--club-fourth",
  "--club-sidebar", "--club-sidebar-dark", "--club-sidebar-foreground",
  "--club-sidebar-active", "--club-sidebar-active-dark",
] as const;

/** Derive the full set of Club-theme CSS variables from a workspace's brand colours. */
export function deriveClubVars(c: ClubColours): Record<string, string> {
  const out: Record<string, string> = {};
  const primary = c.primary && isValidHex(c.primary) ? c.primary : null;
  const accent = c.accent && isValidHex(c.accent) ? c.accent : (c.secondary && isValidHex(c.secondary) ? c.secondary : null);
  if (primary) {
    out["--club-primary"] = primary;
    out["--club-primary-dark"] = lighten(primary, 0.22);      // brighter for dark surfaces
    out["--club-primary-foreground"] = bestForeground(primary);
    out["--club-sidebar"] = darken(primary, 0.45);            // deep club navy-equivalent
    out["--club-sidebar-dark"] = darken(primary, 0.68);
    out["--club-sidebar-foreground"] = lighten(primary, 0.85);
    out["--club-sidebar-active"] = darken(primary, 0.32);
    out["--club-sidebar-active-dark"] = darken(primary, 0.55);
  }
  if (accent) {
    out["--club-accent"] = accent;
    out["--club-accent-dark"] = lighten(accent, 0.18);
  }
  if (c.secondary && isValidHex(c.secondary)) out["--club-secondary"] = c.secondary;
  if (c.third && isValidHex(c.third)) out["--club-third"] = c.third;
  if (c.fourth && isValidHex(c.fourth)) out["--club-fourth"] = c.fourth;
  return out;
}

/** Apply (or, with null, clear) the Club-theme variables on the document root. */
export function applyClubVars(colours: ClubColours | null): void {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  // Clear any previous club vars first so a workspace switch never leaks colours.
  for (const name of VAR_NAMES) root.style.removeProperty(name);
  if (!colours) return;
  const vars = deriveClubVars(colours);
  for (const [name, value] of Object.entries(vars)) root.style.setProperty(name, value);
}
