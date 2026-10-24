# 41. Responsive Desktop Design Standard

**Deliverable 41.** The reusable visual + responsive standard for the OneStats desktop app,
established during the Phase 6 Stage 7 scorecard review. It is applied in full to the scorecard
editor now; other screens adopt it incrementally at their own phases (no working functionality is
rebuilt to satisfy it).

## 41.1 Principles
- **Design to the application window width, not the monitor.** Layouts respond to the Vite/Tauri
  window via Tailwind breakpoints (`sm` 640, `md` 768, `lg` 1024, `xl` 1280, `2xl` 1536), never to
  physical resolution or OS scaling. Users never change Windows scaling or app zoom to work.
- **No hardcoded colours.** All colour comes from the design tokens in `index.css`
  (`--brand` is workspace-overridable; neutrals are `--card`/`--muted`/`--border`). Brand tints use
  alpha (`bg-brand/5`, `bg-brand/10`) so they follow each workspace's branding and stay accessible
  in light and dark. Saved branding is never modified by presentation code.
- **Unknown stays visible, never zero.** Presentation preserves the data model's distinction
  (blank/`—` for unknown).

## 41.2 Typography & hierarchy (consistent scale)
| Role | Class | Notes |
|---|---|---|
| Screen title (AppShell header) | `text-lg font-semibold` | one per screen |
| Section heading (`SectionCard`) | `text-base font-semibold` | with a leading icon tile |
| Sub-panel heading (`SubPanel`) | `text-sm font-semibold` | collapsible areas |
| Field label (`Field`) | `text-sm font-medium` | |
| Help / secondary text | `text-xs text-muted-foreground` | |
| Data controls | `h-8`/`h-9`, `text-sm`, `tabular-nums` for numbers | min 32px tall for touch/scaling |

Headings are distinctive **without** large vertical cost (icon tile + one line + optional one-line
description). This scale holds at Windows scaling 100–200% because sizes are rem/px tokens, not
viewport units.

## 41.3 Reusable components (`features/scorecard/ui.tsx`, `lib/layout.tsx`)
- **`SectionCard`** — major section: icon tile, bold heading, optional description + header action,
  subtle brand-tinted header strip, `border` + `shadow-sm`, consistent `p-4` body.
- **`SubPanel`** — collapsible sub-area (Batting/Bowling/…): icon, strong label, light `bg-muted/50`
  header, chevron; `aria-expanded`.
- **`TeamPanel`** — a clearly-defined home/away panel: small uppercase `HOME`/`AWAY` chip + prominent
  team name, then its controls.
- **`SubtleBar`** — a restrained neutral strip for inline summaries/legends.
- **`LayoutProvider` / `useLayout`** — app-wide collapsible-sidebar state (persisted per viewer);
  drives the header toggle and scorecard Focus Mode.

## 41.4 Layout rules
- **Columns:** forms use `grid gap-3 sm:grid-cols-2 lg:grid-cols-3` (or `-cols-4` for compact
  fields); home/away use `sm:grid-cols-2`. One column on narrow windows, more as width allows.
- **No unnecessary stretch:** inputs sit in grid cells (bounded width), not full-bleed; large
  windows gain columns rather than ultra-wide fields.
- **Tables scroll within themselves:** entry grids use `overflow-x-auto` with a sensible
  `min-w-[...]`, so a wide batting/bowling table scrolls horizontally **inside its panel** — the
  whole app never gets a horizontal scrollbar.
- **Sidebar:** collapsible to a 64px icon rail (`w-16`) from `w-60`; labels become `sr-only` with
  `title` tooltips, so navigation stays reachable when narrow.
- **Padding scales:** shell uses `p-4 sm:p-6`.

## 41.5 Panels & dialogues
- Modals (`components/ui/dialog.tsx`) are centred with a `p-4` viewport inset, `max-w-lg`, and a
  `max-h-[70vh] overflow-auto` body so they always fit the window and scroll without hiding the
  footer actions. Long forms keep their primary action visible in the footer.

## 41.6 Accessibility
- Focus-visible outlines (`:focus-visible` 2px ring) are global; interactive controls keep them.
- Icon-only controls carry `aria-label` + `title`; toggles expose `aria-pressed`/`aria-expanded`.
- Contrast: foreground/brand tokens are AA-targeted on their surfaces in both themes.
- Keyboard: grids keep arrow/Enter/Tab navigation; Focus Mode exits on `Esc` (unless a modal needs it).

## 41.7 Primary vs secondary actions
- One **primary** (`Button` default = brand) per context (e.g. Save toss, Save official, Save
  result). Everything else is `outline`/`ghost`. Destructive uses `text-danger`. This keeps a clear
  focal action without every button competing.

## 41.8 Responsive checklist (per screen)
- [ ] One-column on narrow (<640), two-column by `sm`, three/four by `lg`/`xl`.
- [ ] No horizontal scroll on the app; wide tables scroll within their own panel.
- [ ] Inputs don't stretch unboundedly on ultrawide; big windows add columns.
- [ ] Sidebar collapses to the icon rail and back; navigation reachable collapsed.
- [ ] Modals fit and scroll; footer actions always visible.
- [ ] Typography uses the §41.2 scale; headings compact.
- [ ] Brand tints via tokens only; AA contrast in light and dark.
- [ ] All controls keyboard-reachable with visible focus; icon-only controls labelled.
- [ ] Verified at 1024×768, 1280×720, 1366×768, 1536×864, 1920×1080, 2560×1440, and at Windows
  scaling 100/125/150/200%.

## 41.9 Adoption
Scorecard editor: **done** (Stage 7). Match list, People, Manage, Dashboard, Settings, onboarding:
adopt `SectionCard`/grid rules as each is next revised — the shell (collapsible sidebar, responsive
padding, modal rules) already applies app-wide. Future phases follow this document.
