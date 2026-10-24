/**
 * Shared visual-presentation primitives for the scorecard editor (Stage 7 refinement).
 *
 * Pure presentation — no data or behaviour. Everything uses the existing design tokens
 * (`--brand` is workspace-overridable, so brand tints follow each workspace's branding; neutral
 * surfaces are `--card`/`--muted`/`--border`). Works in light and dark mode and keeps focus-visible
 * outlines intact. Nothing here hardcodes a colour or touches saved branding.
 */

import { ChevronDown, type LucideIcon } from "lucide-react";
import { type ReactNode, useState } from "react";

/** A major editor section: bold heading with an icon, optional description and header action,
 * a subtle brand-tinted header strip, restrained border + shadow, consistent body padding. */
export function SectionCard({
  icon: Icon,
  title,
  description,
  action,
  children,
}: {
  icon: LucideIcon;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="overflow-hidden rounded-[var(--radius-app)] border border-border bg-card shadow-sm">
      <header className="flex items-center gap-3 border-b border-border bg-brand/5 px-4 py-3">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[var(--radius-app)] bg-brand/10 text-brand">
          <Icon className="h-4 w-4" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-base font-semibold leading-tight text-foreground">{title}</h2>
          {description && <p className="truncate text-xs text-muted-foreground">{description}</p>}
        </div>
        {action}
      </header>
      <div className="p-4">{children}</div>
    </section>
  );
}

/** A collapsible sub-area within a section (Batting / Bowling / …) with an icon, a strong label,
 * and a light neutral header to separate it from its body. */
export function SubPanel({
  icon: Icon,
  title,
  defaultOpen = true,
  right,
  children,
}: {
  icon: LucideIcon;
  title: string;
  defaultOpen?: boolean;
  right?: ReactNode;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="overflow-hidden rounded-[var(--radius-app)] border border-border">
      <div className="flex items-center gap-2 bg-muted/50 px-3 py-2">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          className="flex min-w-0 flex-1 items-center gap-2 text-left text-sm font-semibold text-foreground"
        >
          <ChevronDown className={`h-4 w-4 shrink-0 text-muted-foreground transition-transform ${open ? "" : "-rotate-90"}`} aria-hidden />
          <Icon className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
          <span className="truncate">{title}</span>
        </button>
        {right}
      </div>
      {open && <div className="p-3">{children}</div>}
    </div>
  );
}

/** A clearly-defined home/away team panel with a small side label and a prominent team name. */
export function TeamPanel({
  side,
  teamName,
  children,
}: {
  side: "home" | "away";
  teamName: string | null;
  children?: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-3 rounded-[var(--radius-app)] border border-border bg-card p-3">
      <div className="flex items-center gap-2">
        <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
          {side}
        </span>
        <span className="min-w-0 truncate text-base font-semibold text-foreground">
          {teamName ?? <span className="italic text-muted-foreground">Not set</span>}
        </span>
      </div>
      {children}
    </div>
  );
}

/** A small section-level status/legend chip strip wrapper (kept neutral, non-dominant). */
export function SubtleBar({ children }: { children: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-1 rounded-[var(--radius-app)] bg-muted/50 px-3 py-2 text-sm">
      {children}
    </div>
  );
}
