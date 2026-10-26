/**
 * OneStats visual theme registry.
 *
 * The six selectable themes (defined as CSS token sets in `themes.css`). This module is the single
 * source of truth for their ids, names and descriptions, used by the theme provider (to validate and
 * apply the active theme) and by the Appearance & Themes gallery (to render preview cards).
 *
 * The actual colours live in `themes.css` keyed on `[data-theme="<id>"]` (+ `[data-mode="dark"]`);
 * the small swatch hints here are only for the gallery's quick colour chips.
 */

export type ThemeId = "traditional" | "modern" | "professional" | "test" | "oneday" | "t20" | "club" | "onestats";
export type ThemeMode = "light" | "dark" | "system";

export interface ThemeMeta {
  id: ThemeId;
  name: string;
  tagline: string;
  description: string;
  /** Representative chips for the gallery card header (purely decorative hints). */
  swatch: { brand: string; accent: string; surface: string; sidebar: string };
  /** Club theme: its palette is driven by workspace branding (editable by admins). */
  clubDriven?: boolean;
  /** Protected official OneStats theme: fixed palette, never overridden by club branding. */
  official?: boolean;
}

/** The default theme for new users (per spec: Modern), unless a saved preference exists. */
export const DEFAULT_THEME: ThemeId = "modern";

export const THEMES: ThemeMeta[] = [
  {
    id: "traditional",
    name: "Traditional",
    tagline: "Heritage country cricket",
    description:
      "Deep navy, cricket whites and leather tones with classic serif headings — an established, timeless clubroom feel for clubs with long histories.",
    swatch: { brand: "#1e3a5f", accent: "#8a5a2b", surface: "#fffdf7", sidebar: "#1b2238" },
  },
  {
    id: "modern",
    name: "Modern",
    tagline: "Contemporary & clean",
    description:
      "Spacious layouts, rounded cards and crisp blue accents. Fresh, intuitive and highly readable — the default OneStats look.",
    swatch: { brand: "#2563eb", accent: "#0ea5e9", surface: "#ffffff", sidebar: "#0f172a" },
  },
  {
    id: "professional",
    name: "Professional",
    tagline: "Broadcast analytics",
    description:
      "Sophisticated dark navy and neutral surfaces with strong typography and a premium dashboard feel — like an elite cricket association.",
    swatch: { brand: "#0b2447", accent: "#1a8fb3", surface: "#ffffff", sidebar: "#0b1324" },
  },
  {
    id: "test",
    name: "Test",
    tagline: "Test cricket heritage",
    description:
      "Ivory, rich green and restrained gold with scorebook-inspired tables. Keeps its prestigious identity even when club colours are applied.",
    swatch: { brand: "#1b5e3a", accent: "#b58b2f", surface: "#fffdf3", sidebar: "#16492d" },
  },
  {
    id: "oneday",
    name: "One Day",
    tagline: "Limited-overs energy",
    description:
      "Bold sporting blue and vivid orange, high contrast and broadcast-inspired — energetic and competitive without the clutter.",
    swatch: { brand: "#0353a4", accent: "#e8590c", surface: "#ffffff", sidebar: "#0a2d5c" },
  },
  {
    id: "t20",
    name: "T20",
    tagline: "Spectacle & impact",
    description:
      "Deep backgrounds with vibrant purple and magenta accents and high-impact cards — exciting and premium, still built for serious stats.",
    swatch: { brand: "#7b2ff7", accent: "#ff2d87", surface: "#ffffff", sidebar: "#1a1030" },
  },
  {
    id: "club",
    name: "Club",
    tagline: "Your club, your colours",
    description:
      "A fully personalised theme built from your club's own colours and logo. Admins set the palette in the Club Theme Editor; everyone can wear the club's identity.",
    swatch: { brand: "#334155", accent: "#0ea5e9", surface: "#ffffff", sidebar: "#1f2937" },
    clubDriven: true,
  },
  {
    id: "onestats",
    name: "OneStats",
    tagline: "Official brand theme",
    description:
      "The flagship OneStats identity — navy, royal and electric blue with silver and restrained cricket-red. Always consistent, in every workspace.",
    swatch: { brand: "#0755aa", accent: "#00a9eb", surface: "#ffffff", sidebar: "#071e43" },
    official: true,
  },
];

export const THEME_BY_ID: Record<ThemeId, ThemeMeta> = Object.fromEntries(
  THEMES.map((t) => [t.id, t]),
) as Record<ThemeId, ThemeMeta>;

export function isThemeId(v: unknown): v is ThemeId {
  return typeof v === "string" && v in THEME_BY_ID;
}
