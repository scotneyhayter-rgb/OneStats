/**
 * Dashboard customisation within limits (Part 15). A user may hide/show a small set of NON-CRITICAL
 * sections; the choice is stored per user + per workspace. Critical sections — the identity header,
 * quick actions, My Tasks and any security/admin warning (e.g. the "Super Admin — Managing…" banner,
 * which lives in the AppShell) — are intentionally NOT customisable and can never be hidden. The
 * helpers enforce that invariant: only keys in CUSTOMISABLE_SECTIONS can ever end up hidden, even if
 * a stored preference blob is tampered with.
 */
export interface DashSection {
  key: string;
  label: string;
}

export const CUSTOMISABLE_SECTIONS: DashSection[] = [
  { key: "summary", label: "Summary" },
  { key: "research", label: "Historical research" },
  { key: "activity", label: "Recent activity" },
];

const ALLOWED = new Set(CUSTOMISABLE_SECTIONS.map((s) => s.key));

type Prefs = Record<string, unknown> | null | undefined;

export function hiddenSet(prefs: Prefs): Set<string> {
  const h = prefs?.["hidden"];
  const keys = Array.isArray(h) ? h.filter((x): x is string => typeof x === "string") : [];
  // only customisable sections may be hidden — this is what keeps critical sections always visible
  return new Set(keys.filter((k) => ALLOWED.has(k)));
}

export function isHidden(prefs: Prefs, key: string): boolean {
  return hiddenSet(prefs).has(key);
}

/** Toggle a section's visibility, returning the next prefs object (does not mutate the input). */
export function toggleHidden(prefs: Prefs, key: string): Record<string, unknown> {
  if (!ALLOWED.has(key)) return { ...(prefs ?? {}) }; // refuse to hide a non-customisable section
  const h = hiddenSet(prefs);
  if (h.has(key)) h.delete(key);
  else h.add(key);
  return { ...(prefs ?? {}), hidden: [...h] };
}
