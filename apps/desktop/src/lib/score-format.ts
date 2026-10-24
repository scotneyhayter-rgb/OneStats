/**
 * Score display format resolution (Phase 7.7). The effective format is the viewer's own preference
 * where set, otherwise the workspace default (Australian wickets/runs by default). This is display
 * formatting only — it never changes stored runs or wickets. The per-viewer preference lives in
 * localStorage and is applied reactively across the app via a custom event.
 */
import { useEffect, useState } from "react";
import type { ScoreFormat } from "../features/scorecard/scorecard-logic";
import { useWorkspace } from "./workspace-context";

const KEY = "onestats.score_format";
const EVENT = "onestats:score_format";

export function getUserScoreFormat(): ScoreFormat | null {
  try {
    const v = localStorage.getItem(KEY);
    return v === "au" || v === "en" ? v : null;
  } catch {
    return null;
  }
}

/** Set (or clear, with null) the viewer's own preference and notify listeners. */
export function setUserScoreFormat(v: ScoreFormat | null): void {
  try {
    if (v) localStorage.setItem(KEY, v);
    else localStorage.removeItem(KEY);
  } catch { /* private mode / blocked storage — ignore */ }
  try { window.dispatchEvent(new Event(EVENT)); } catch { /* no window */ }
}

/** The effective score format for the current viewer and workspace. */
export function useScoreFormat(): ScoreFormat {
  const { current } = useWorkspace();
  const [user, setUser] = useState<ScoreFormat | null>(getUserScoreFormat());
  useEffect(() => {
    const h = () => setUser(getUserScoreFormat());
    window.addEventListener(EVENT, h);
    window.addEventListener("storage", h);  // other tabs
    return () => { window.removeEventListener(EVENT, h); window.removeEventListener("storage", h); };
  }, []);
  return user ?? ((current?.score_format as ScoreFormat | undefined) ?? "au");
}
