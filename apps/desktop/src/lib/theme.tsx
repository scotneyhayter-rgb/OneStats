import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { DEFAULT_THEME, isThemeId, type ThemeId } from "./themes";

/** Appearance mode (light/dark/system) — distinct from the named visual theme. */
type Mode = "light" | "dark" | "system";

interface ThemeContextValue {
  /** Appearance mode preference. (Legacy name `theme` kept for existing callers.) */
  theme: Mode;
  mode: Mode;
  /** The active named visual theme (one of the six). */
  themeName: ThemeId;
  resolved: "light" | "dark";
  /** Set the appearance mode. (Legacy name `setTheme` kept for existing callers.) */
  setTheme: (t: Mode) => void;
  setMode: (t: Mode) => void;
  setThemeName: (t: ThemeId) => void;
  toggle: () => void;

  // --- Non-persisting live preview (for the Appearance gallery) ---
  /** The effective theme currently shown (preview if previewing, else the saved theme). */
  effectiveTheme: ThemeId;
  effectiveMode: Mode;
  isPreviewing: boolean;
  /** Start/replace a live preview without saving. Pass nulls to leave that axis at the saved value. */
  preview: (themeName: ThemeId | null, mode: Mode | null) => void;
  /** Persist the current preview as the user's saved preference. */
  applyPreview: () => void;
  /** Discard the preview and restore the saved preference. */
  cancelPreview: () => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);
const MODE_KEY = "onestats.theme"; // appearance mode (kept key for back-compat)
const THEME_KEY = "onestats.skin"; // named visual theme

function systemPrefersDark(): boolean {
  return (
    typeof window !== "undefined" &&
    window.matchMedia?.("(prefers-color-scheme: dark)").matches
  );
}

function readMode(): Mode {
  try {
    const v = localStorage.getItem(MODE_KEY);
    if (v === "light" || v === "dark" || v === "system") return v;
  } catch {
    /* storage may be unavailable; fall back to default */
  }
  return "system";
}

function readThemeName(): ThemeId {
  try {
    const v = localStorage.getItem(THEME_KEY);
    if (isThemeId(v)) return v;
  } catch {
    /* storage may be unavailable; fall back to default */
  }
  return DEFAULT_THEME;
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<Mode>(readMode);
  const [themeName, setThemeNameState] = useState<ThemeId>(readThemeName);
  const [systemDark, setSystemDark] = useState<boolean>(systemPrefersDark);
  const [previewTheme, setPreviewTheme] = useState<ThemeId | null>(null);
  const [previewMode, setPreviewMode] = useState<Mode | null>(null);

  useEffect(() => {
    const mq = window.matchMedia?.("(prefers-color-scheme: dark)");
    if (!mq) return;
    const onChange = () => setSystemDark(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  const effectiveTheme = previewTheme ?? themeName;
  const effectiveMode = previewMode ?? mode;
  const isPreviewing = previewTheme !== null || previewMode !== null;

  const resolved: "light" | "dark" =
    effectiveMode === "system" ? (systemDark ? "dark" : "light") : effectiveMode;

  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle("dark", resolved === "dark"); // back-compat for dark: utilities
    root.dataset.mode = resolved;
    root.dataset.theme = effectiveTheme;
    root.style.colorScheme = resolved;
  }, [resolved, effectiveTheme]);

  const setMode = useCallback((t: Mode) => {
    setModeState(t);
    try {
      localStorage.setItem(MODE_KEY, t);
    } catch {
      /* ignore persistence failure */
    }
  }, []);

  const setThemeName = useCallback((t: ThemeId) => {
    setThemeNameState(t);
    try {
      localStorage.setItem(THEME_KEY, t);
    } catch {
      /* ignore persistence failure */
    }
  }, []);

  const toggle = useCallback(
    () => setMode(resolved === "dark" ? "light" : "dark"),
    [resolved, setMode],
  );

  const preview = useCallback((t: ThemeId | null, m: Mode | null) => {
    setPreviewTheme(t);
    setPreviewMode(m);
  }, []);

  const cancelPreview = useCallback(() => {
    setPreviewTheme(null);
    setPreviewMode(null);
  }, []);

  const applyPreview = useCallback(() => {
    if (previewTheme !== null) setThemeName(previewTheme);
    if (previewMode !== null) setMode(previewMode);
    setPreviewTheme(null);
    setPreviewMode(null);
  }, [previewTheme, previewMode, setThemeName, setMode]);

  const value = useMemo(
    () => ({
      theme: mode,
      mode,
      themeName,
      resolved,
      setTheme: setMode,
      setMode,
      setThemeName,
      toggle,
      effectiveTheme,
      effectiveMode,
      isPreviewing,
      preview,
      applyPreview,
      cancelPreview,
    }),
    [mode, themeName, resolved, setMode, setThemeName, toggle, effectiveTheme, effectiveMode,
      isPreviewing, preview, applyPreview, cancelPreview],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider");
  return ctx;
}
