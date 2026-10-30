/**
 * Date display formatting. The stored style is a per-device preference (the OneStats clients on a main
 * PC and a laptop may differ), applied through formatDate so every date on screen reads the same way.
 * Day/month/year is the default (Australian/most-of-the-world); month/day/year is the US style.
 */
import { useEffect, useState } from "react";

export type DateStyle = "dmy" | "mdy";
const KEY = "onestats-date-style";
const EVENT = "onestats-date-style-changed";

export function getDateStyle(): DateStyle {
  try {
    const v = localStorage.getItem(KEY);
    if (v === "mdy" || v === "dmy") return v;
  } catch { /* storage unavailable */ }
  return "dmy";
}

export function setDateStyle(style: DateStyle): void {
  try { localStorage.setItem(KEY, style); } catch { /* storage unavailable */ }
  window.dispatchEvent(new Event(EVENT));   // let any mounted component re-render immediately
}

/** Format a date-only (or ISO) string per the chosen style. Returns "" for empty, the raw value if unparseable.
 *  Uses UTC parts so a plain "YYYY-MM-DD" is never shifted a day by the local timezone. */
export function formatDate(value: string | null | undefined, style: DateStyle = getDateStyle()): string {
  if (!value) return "";
  const t = Date.parse(value);
  if (Number.isNaN(t)) return String(value);
  const d = new Date(value);
  const dd = String(d.getUTCDate()).padStart(2, "0");
  const mm = String(d.getUTCMonth() + 1).padStart(2, "0");
  const yyyy = d.getUTCFullYear();
  return style === "mdy" ? `${mm}/${dd}/${yyyy}` : `${dd}/${mm}/${yyyy}`;
}

/** Subscribe to the current date style so a component re-renders when the preference changes. */
export function useDateStyle(): DateStyle {
  const [style, setStyle] = useState<DateStyle>(getDateStyle);
  useEffect(() => {
    const handler = () => setStyle(getDateStyle());
    window.addEventListener(EVENT, handler);
    window.addEventListener("storage", handler);   // changed in another tab/window
    return () => { window.removeEventListener(EVENT, handler); window.removeEventListener("storage", handler); };
  }, []);
  return style;
}
