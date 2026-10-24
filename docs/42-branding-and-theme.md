# 42. OneStats Branding & Application Theme

**Deliverable 42.** How the official OneStats branding and the application colour theme are used in
the desktop app, and how they stay distinct from per-workspace branding. Established during the
Phase 6 Stage 7 review.

## 42.1 Official assets (supplied artwork — used unmodified)
| Asset | Source | Bundled as | Used for |
|---|---|---|---|
| Full horizontal logo (wordmark + tagline + Discover/Understand/Celebrate) | supplied PNG, 1774×887 | `apps/desktop/src/assets/onestats-logo.png` | Login/welcome screen, About dialog |
| Circular icon (stat bars, blue swoosh, red ball) | supplied PNG, 1254×1254 | `apps/desktop/src/assets/onestats-icon.png` | Sidebar header, favicon, Windows app icon, compact locations |

The artwork is **never recoloured, redrawn or cropped**. Icon sizes are produced by plain
high-quality (LANCZOS) **resize only** from the square source (`src-tauri/icons/*` — 32/128/
128@2x/512, the Square*/StoreLogo set, and a multi-resolution `icon.ico`) and the favicon
(`public/onestats-icon.png`, 256px).

### Transparency limitation (reported, not silently changed)
Both supplied images are **opaque RGB with a white background** (no alpha). So:
- On coloured surfaces (the dark navy sidebar, dark-theme cards) the artwork is placed on a small
  **white plate** so the white backdrop looks intentional and the logo stays readable in light and
  dark. The artwork itself is untouched.
- `icon.ico`/PNG app icons keep the white square background (normal for app icons).
- `src-tauri/icons/icon.icns` (macOS) was **left unchanged** — Pillow cannot author `.icns`;
  regenerate it on macOS from the circular icon if a Mac build is needed.
- For seamless placement directly on coloured surfaces, a **transparent-background** version of each
  logo would be required; supply those and they can replace the plates.

## 42.2 Application colour theme (design tokens, `src/index.css`)
The theme is inspired by the logos and expressed **only as tokens** (no scattered hardcoded
colours), with light and dark values and AA-targeted contrast:
| Role | Token | Light | Dark |
|---|---|---|---|
| Deep navy — headings, primary navigation surface | `--sidebar` / `--foreground` | `#0f172a` | `#070c17` / `#e6eaf2` |
| Royal blue — primary actions, selected controls | `--brand` | `#2563eb` | `#3b82f6` |
| Electric blue — highlights, interactive accents | `--accent` | `#0ea5e9` | `#38bdf8` |
| Silver / cool grey — secondary surfaces, borders | `--muted` / `--border` | `#eef1f5` / `#e2e6ec` | `#16213a` / `#233049` |
| Cricket-ball red — limited decorative accents only | `--ball-red` | `#c81e1e` | `#ef4444` |

Presentation stays restrained — no heavy gradients, glossy effects or bright colour on every
component; red is reserved for small accents (never primary actions).

## 42.3 Application branding vs workspace branding (kept separate)
- **Application branding** = the OneStats logo, circular icon and the default theme tokens above.
  It is fixed and identifies the product.
- **Workspace branding** (deliverable 9) overrides `--brand`/`--accent` **at runtime** for a club or
  association, and workspace logos appear in workspace areas. This review did **not** change the
  workspace-branding mechanism or any saved workspace theme — user-configured themes still override
  the app defaults, and brand tints throughout the UI (`bg-brand/*`) therefore follow the active
  workspace.

## 42.4 Responsive use
- The **full logo** appears only where there is room (login, About) and never on data-entry screens;
  it is width-capped so it doesn't consume vertical space.
- The **circular icon** (or the compact wordmark) is used in tight spots (sidebar header, favicon,
  collapsed rail), so branding scales from small laptops to large monitors.
