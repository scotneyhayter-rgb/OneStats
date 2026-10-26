import { Check, Eye, Monitor, Moon, Palette, RotateCcw, Sun } from "lucide-react";
import { useMemo, useState } from "react";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import { Modal } from "../../components/ui/dialog";
import { cn } from "../../lib/utils";
import { useTheme } from "../../lib/theme";
import { DEFAULT_THEME, THEMES, THEME_BY_ID, type ThemeId } from "../../lib/themes";

type PreviewMode = "light" | "dark";

/**
 * A scoped mini-mock of the OneStats interface, rendered in a specific theme + mode WITHOUT changing
 * the live app. It works because the whole app is token-driven: setting `data-theme`/`data-mode` on
 * this wrapper makes every token-based utility inside resolve to that theme's colours.
 */
export function ThemeMock({ themeId, mode, size = "card" }: { themeId: ThemeId; mode: PreviewMode; size?: "card" | "full" }) {
  const small = size === "card";
  const heading = { fontFamily: "var(--font-heading)" } as const;
  return (
    <div
      data-theme={themeId}
      data-mode={mode}
      className="overflow-hidden rounded-[var(--radius-app)] border border-border bg-background text-foreground"
      style={{ colorScheme: mode }}
    >
      <div className="flex">
        {/* Sidebar */}
        <div className="shrink-0 bg-sidebar text-sidebar-foreground" style={{ width: small ? 46 : 120 }}>
          <div className="flex items-center gap-1.5 p-2">
            <div className="h-3 w-3 rounded-full bg-brand" />
            {!small && <div className="text-[11px] font-semibold">OneStats</div>}
          </div>
          <div className="space-y-1 p-2">
            {["Dashboard", "Matches", "People", "Stats"].map((l, i) => (
              <div key={l} className={cn("rounded-[var(--radius-app)] px-1.5 py-1 text-[9px] truncate",
                i === 0 ? "bg-sidebar-active text-sidebar-foreground" : "text-sidebar-muted")}>
                {small ? "—" : l}
              </div>
            ))}
          </div>
        </div>
        {/* Main */}
        <div className="min-w-0 flex-1 p-2.5">
          <div className="mb-2 text-[12px] font-semibold text-brand" style={heading}>
            {small ? "Dashboard" : "Club Dashboard"}
          </div>
          <div className="mb-2 grid grid-cols-3 gap-1.5">
            {[["Matches", "128"], ["Runs", "9,412"], ["Wkts", "377"]].map(([k, v]) => (
              <div key={k} className="rounded-[var(--radius-app)] border border-border bg-card p-1.5">
                <div className="text-[7px] text-muted-foreground">{k}</div>
                <div className="text-[12px] font-bold text-card-foreground">{v}</div>
              </div>
            ))}
          </div>
          {/* mini table */}
          <div className="overflow-hidden rounded-[var(--radius-app)] border border-border">
            <div className="flex bg-brand px-1.5 py-1 text-[8px] font-semibold text-brand-foreground">
              <span className="flex-1">Batter</span><span className="w-8 text-right">Runs</span><span className="w-8 text-right">Avg</span>
            </div>
            {[["K. Ellis", "612", "48.0"], ["T. Quick", "540", "41.5"]].map(([n, r, a], i) => (
              <div key={n} className={cn("flex px-1.5 py-1 text-[8px] text-card-foreground",
                i % 2 ? "bg-muted" : "bg-card")}>
                <span className="flex-1">{n}</span><span className="w-8 text-right">{r}</span><span className="w-8 text-right">{a}</span>
              </div>
            ))}
          </div>
          {/* chart + controls */}
          <div className="mt-2 flex items-end gap-2">
            <div className="flex h-8 flex-1 items-end gap-1">
              {[40, 70, 55, 90, 62].map((h, i) => (
                <div key={i} className="flex-1 rounded-sm" style={{ height: `${h}%`, background: "var(--accent)" }} />
              ))}
            </div>
            <div className="rounded-[var(--radius-app)] bg-brand px-2 py-1 text-[8px] font-medium text-brand-foreground">Report</div>
          </div>
          {!small && (
            <div className="mt-2 flex items-center gap-1.5">
              <span className="rounded-full bg-success/20 px-2 py-0.5 text-[8px] text-success">Won</span>
              <span className="rounded-full bg-warning/20 px-2 py-0.5 text-[8px] text-warning">Review</span>
              <span className="rounded-full px-2 py-0.5 text-[8px]" style={{ background: "color-mix(in srgb, var(--ball-red) 18%, transparent)", color: "var(--ball-red)" }}>Live</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

const MODE_OPTS: { id: "light" | "dark" | "system"; label: string; icon: typeof Sun }[] = [
  { id: "light", label: "Light", icon: Sun },
  { id: "dark", label: "Dark", icon: Moon },
  { id: "system", label: "System", icon: Monitor },
];

export function Appearance() {
  const t = useTheme();
  const [confirmReset, setConfirmReset] = useState(false);
  const [previewId, setPreviewId] = useState<ThemeId | null>(null);
  const [modalMode, setModalMode] = useState<PreviewMode>(t.resolved);

  // What the gallery should mark as "selected": the previewed theme if previewing, else the saved one.
  const selected = t.effectiveTheme;
  const mockMode: PreviewMode = t.resolved;

  const selectTheme = (id: ThemeId) => t.preview(id === t.themeName && t.mode === t.effectiveMode ? null : id, null);
  const selectMode = (m: "light" | "dark" | "system") => t.preview(t.effectiveTheme === t.themeName ? null : t.effectiveTheme, m === t.mode ? null : m);

  const restoreDefault = () => {
    t.preview(DEFAULT_THEME, "system");
    t.applyPreview();
    setConfirmReset(false);
  };

  const dirty = t.isPreviewing;
  const activeMeta = useMemo(() => THEME_BY_ID[t.themeName], [t.themeName]);

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardContent className="flex flex-col gap-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 className="flex items-center gap-2 text-sm font-semibold">
                <Palette className="h-4 w-4 text-brand" /> Appearance &amp; Themes
              </h3>
              <p className="text-xs text-muted-foreground">
                Choose a visual theme and light/dark mode for your OneStats. This is your personal
                preference — it doesn&apos;t change anyone else&apos;s view or any cricket data.
              </p>
            </div>
            <Badge variant="outline" className="whitespace-nowrap">Active: {activeMeta.name}</Badge>
          </div>

          {/* Appearance mode */}
          <div>
            <div className="mb-1.5 text-xs font-medium">Appearance mode</div>
            <div className="inline-flex rounded-[var(--radius-app)] border border-border p-0.5">
              {MODE_OPTS.map(({ id, label, icon: Icon }) => {
                const on = t.effectiveMode === id;
                return (
                  <button key={id} onClick={() => selectMode(id)}
                    className={cn("flex items-center gap-1.5 rounded-[var(--radius-app)] px-3 py-1.5 text-sm transition-colors",
                      on ? "bg-brand text-brand-foreground" : "text-muted-foreground hover:bg-muted")}>
                    <Icon className="h-3.5 w-3.5" /> {label}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Gallery */}
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
            {THEMES.map((theme) => {
              const isSel = selected === theme.id;
              return (
                <div key={theme.id}
                  className={cn("group flex flex-col rounded-[var(--radius-app)] border-2 p-2.5 transition-colors",
                    isSel ? "border-brand bg-brand/5" : "border-border hover:border-muted-foreground/40")}>
                  <button onClick={() => selectTheme(theme.id)} className="text-left" aria-pressed={isSel}>
                    <ThemeMock themeId={theme.id} mode={mockMode} />
                  </button>
                  <div className="mt-2 flex items-center justify-between gap-2">
                    <div className="flex items-center gap-1.5">
                      <span className="text-sm font-semibold">{theme.name}</span>
                      {isSel && (
                        <span className="inline-flex items-center gap-0.5 rounded-full bg-brand px-1.5 py-0.5 text-[10px] font-medium text-brand-foreground">
                          <Check className="h-3 w-3" /> {t.themeName === theme.id && !t.isPreviewing ? "Active" : "Selected"}
                        </span>
                      )}
                    </div>
                    <div className="flex gap-1">
                      {[theme.swatch.brand, theme.swatch.accent, theme.swatch.sidebar].map((c) => (
                        <span key={c} className="h-4 w-4 rounded-full border border-border" style={{ background: c }} />
                      ))}
                    </div>
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">{theme.tagline}</p>
                  <p className="mt-1 line-clamp-3 text-[11px] text-muted-foreground/90">{theme.description}</p>
                  {theme.clubDriven && (
                    <span className="mt-1 inline-flex w-fit items-center gap-1 rounded-full bg-accent/15 px-1.5 py-0.5 text-[10px] text-accent">
                      <Palette className="h-3 w-3" /> Uses your club colours
                    </span>
                  )}
                  {theme.official && (
                    <span className="mt-1 inline-flex w-fit items-center gap-1 rounded-full bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                      Protected palette
                    </span>
                  )}
                  <div className="mt-2 flex gap-2">
                    <Button size="sm" variant={isSel ? "primary" : "outline"} className="flex-1"
                      onClick={() => selectTheme(theme.id)}>
                      {isSel ? "Selected" : "Select"}
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => { setPreviewId(theme.id); setModalMode(t.resolved); }}
                      aria-label={`Preview ${theme.name}`} title="Live preview">
                      <Eye className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Apply / Cancel / Restore */}
          <div className="flex flex-wrap items-center gap-2 border-t border-border pt-3">
            <Button onClick={() => t.applyPreview()} disabled={!dirty}>Apply theme</Button>
            <Button variant="outline" onClick={() => t.cancelPreview()} disabled={!dirty}>Cancel</Button>
            {t.effectiveTheme === "club" && (
              <Button variant="outline" onClick={() => document.getElementById("club-theme-editor")?.scrollIntoView({ behavior: "smooth" })}>
                <Palette className="h-4 w-4" /> Customise club colours
              </Button>
            )}
            <Button variant="ghost" className="ml-auto text-muted-foreground" onClick={() => setConfirmReset(true)}>
              <RotateCcw className="h-4 w-4" /> Restore default
            </Button>
          </div>
          {dirty && (
            <p className="text-xs text-warning">
              Previewing <b>{THEME_BY_ID[t.effectiveTheme].name}</b> ({t.effectiveMode}). Click
              “Apply theme” to keep it, or “Cancel” to go back to {activeMeta.name}.
            </p>
          )}
        </CardContent>
      </Card>

      {/* Live preview modal */}
      <Modal open={previewId !== null} title={previewId ? `${THEME_BY_ID[previewId].name} theme — live preview` : ""}
        onClose={() => setPreviewId(null)}>
        {previewId && (
          <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between gap-2">
              <p className="text-xs text-muted-foreground">{THEME_BY_ID[previewId].description}</p>
              <div className="inline-flex rounded-[var(--radius-app)] border border-border p-0.5">
                {(["light", "dark"] as PreviewMode[]).map((m) => (
                  <button key={m} onClick={() => setModalMode(m)}
                    className={cn("rounded-[var(--radius-app)] px-2.5 py-1 text-xs capitalize",
                      modalMode === m ? "bg-brand text-brand-foreground" : "text-muted-foreground hover:bg-muted")}>
                    {m}
                  </button>
                ))}
              </div>
            </div>
            <div className="scale-[1] [&_*]:!transition-none">
              <ThemeMock themeId={previewId} mode={modalMode} size="full" />
            </div>
            <div className="flex gap-2">
              <Button onClick={() => { t.preview(previewId, modalMode); setPreviewId(null); }}>Preview in app</Button>
              <Button variant="outline" onClick={() => { t.preview(previewId, modalMode); t.applyPreview(); setPreviewId(null); }}>
                Apply this theme
              </Button>
              <Button variant="ghost" className="ml-auto" onClick={() => setPreviewId(null)}>Close</Button>
            </div>
          </div>
        )}
      </Modal>

      {/* Restore-default confirm */}
      <Modal open={confirmReset} title="Restore default appearance" onClose={() => setConfirmReset(false)}>
        <div className="flex flex-col gap-4">
          <p className="text-sm text-muted-foreground">
            This resets your personal appearance to the default <b>Modern</b> theme and <b>System</b> mode.
            It doesn&apos;t affect workspace branding or anyone else&apos;s settings.
          </p>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setConfirmReset(false)}>Cancel</Button>
            <Button onClick={restoreDefault}>Restore default</Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
