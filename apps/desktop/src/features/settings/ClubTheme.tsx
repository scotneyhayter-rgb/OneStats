import { ImageUp, Loader2, RotateCcw, Sparkles, Trash2, Wand2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import { api, ApiError, type BrandingRecord } from "../../lib/api";
import { bestForeground, contrastRatio, isValidHex } from "../../lib/color";
import { applyClubVars } from "../../lib/branding-runtime";
import { suggestPaletteFromLogo, type SuggestedPalette } from "../../lib/palette";
import { compressImage } from "../../lib/utils";
import { useWorkspace } from "../../lib/workspace-context";
import { ThemeMock } from "./Appearance";

type Field = "primary_colour" | "secondary_colour" | "third_colour" | "fourth_colour" | "accent_colour";
const FIELDS: { key: Field; label: string; hint: string }[] = [
  { key: "primary_colour", label: "Primary", hint: "Main brand colour — buttons, highlights, headers" },
  { key: "secondary_colour", label: "Secondary", hint: "Supporting colour" },
  { key: "third_colour", label: "Third", hint: "Additional supporting colour" },
  { key: "fourth_colour", label: "Fourth", hint: "Additional supporting colour" },
  { key: "accent_colour", label: "Accent", hint: "Charts, links and small highlights" },
];

type Draft = Record<Field, string>;
const EMPTY: Draft = { primary_colour: "", secondary_colour: "", third_colour: "", fourth_colour: "", accent_colour: "" };

function toDraft(b: BrandingRecord | null): Draft {
  return {
    primary_colour: b?.primary_colour ?? "",
    secondary_colour: b?.secondary_colour ?? "",
    third_colour: b?.third_colour ?? "",
    fourth_colour: b?.fourth_colour ?? "",
    accent_colour: b?.accent_colour ?? "",
  };
}

/**
 * The Club Theme Editor (Settings → Workspace Branding). Authorised admins set the workspace's club
 * palette and logo; the colours drive the "Club" theme across the app (within theme boundaries).
 * Non-admins see the approved palette read-only. Changes are staged and only persisted on Save.
 */
export function ClubThemeEditor({ admin }: { admin: boolean }) {
  const { current } = useWorkspace();
  const wsId = current?.id ?? null;
  const [saved, setSaved] = useState<Draft>(EMPTY);
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [logoUrl, setLogoUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [suggesting, setSuggesting] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    if (!wsId) return;
    setLoading(true); setErr(null);
    try {
      const res = await api.getBranding(wsId);
      const d = toDraft(res.branding);
      setSaved(d); setDraft(d);
      const url = await api.brandingLogoObjectUrl(wsId);
      setLogoUrl((prev) => { if (prev) URL.revokeObjectURL(prev); return url; });
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Could not load club branding.");
    } finally {
      setLoading(false);
    }
  }, [wsId]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => () => { if (logoUrl) URL.revokeObjectURL(logoUrl); }, [logoUrl]);

  const set = (k: Field, v: string) => { setDraft((d) => ({ ...d, [k]: v })); setMsg(null); };

  const invalid = useMemo(
    () => FIELDS.filter((f) => draft[f.key] && !isValidHex(draft[f.key])).map((f) => f.key),
    [draft],
  );
  const warnings = useMemo(() => {
    const w: string[] = [];
    for (const f of FIELDS) {
      const v = draft[f.key];
      if (v && isValidHex(v) && contrastRatio(v, bestForeground(v)) < 4.5) {
        w.push(`${f.label} (${v}) may be hard to read with text on it.`);
      }
    }
    return w;
  }, [draft]);
  const dirty = useMemo(() => FIELDS.some((f) => draft[f.key] !== saved[f.key]), [draft, saved]);

  const applyDraftLive = useCallback((d: Draft) => {
    applyClubVars({
      primary: d.primary_colour || null, secondary: d.secondary_colour || null,
      third: d.third_colour || null, fourth: d.fourth_colour || null, accent: d.accent_colour || null,
    });
  }, []);

  const save = async () => {
    if (!wsId || invalid.length) return;
    setBusy(true); setErr(null); setMsg(null);
    try {
      const body = Object.fromEntries(FIELDS.map((f) => [f.key, draft[f.key] || null])) as Record<Field, string | null>;
      const res = await api.setBranding(wsId, body);
      const d = toDraft(res.branding);
      setSaved(d); setDraft(d);
      applyDraftLive(d);
      setMsg("Club theme saved.");
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Could not save the club theme.");
    } finally {
      setBusy(false);
    }
  };

  const onUploadLogo = async (file: File) => {
    if (!wsId) return;
    setBusy(true); setErr(null); setMsg(null);
    try {
      const compressed = await compressImage(file, 512, 0.9);
      await api.uploadBrandingLogo(wsId, compressed);
      const url = await api.brandingLogoObjectUrl(wsId);
      setLogoUrl((prev) => { if (prev) URL.revokeObjectURL(prev); return url; });
      setMsg("Logo updated. Use “Regenerate from logo” to suggest colours.");
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Could not upload the logo.");
    } finally {
      setBusy(false);
    }
  };

  const removeLogo = async () => {
    if (!wsId) return;
    setBusy(true); setErr(null);
    try {
      await api.deleteBrandingLogo(wsId);
      setLogoUrl((prev) => { if (prev) URL.revokeObjectURL(prev); return null; });
      setMsg("Logo removed.");
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Could not remove the logo.");
    } finally {
      setBusy(false);
    }
  };

  const regenerate = async () => {
    if (!logoUrl) { setErr("Upload a club logo first to suggest colours."); return; }
    setSuggesting(true); setErr(null); setMsg(null);
    try {
      const p: SuggestedPalette = await suggestPaletteFromLogo(logoUrl);
      setDraft({
        primary_colour: p.primary, secondary_colour: p.secondary, third_colour: p.third,
        fourth_colour: p.fourth, accent_colour: p.accent,
      });
      setMsg("Suggested colours from your logo — review and edit, then Save.");
    } catch {
      setErr("Could not read colours from the logo. Set them manually.");
    } finally {
      setSuggesting(false);
    }
  };

  const resetSaved = () => { setDraft(saved); setMsg(null); setErr(null); };

  // Live preview of the Club theme using the current draft colours (scoped, does not persist).
  const previewVars = useMemo(() => {
    const d = draft;
    const v: Record<string, string> = {};
    const p = d.primary_colour; const a = d.accent_colour || d.secondary_colour;
    if (p && isValidHex(p)) {
      v["--club-primary"] = p;
      v["--club-primary-foreground"] = bestForeground(p);
      v["--club-sidebar"] = mixHex(p, "#000000", 0.45);
      v["--club-sidebar-foreground"] = mixHex(p, "#ffffff", 0.85);
      v["--club-sidebar-active"] = mixHex(p, "#000000", 0.32);
    }
    if (a && isValidHex(a)) v["--club-accent"] = a;
    return v;
  }, [draft]);

  if (!wsId) return <p className="text-xs text-muted-foreground">Select a workspace to manage its club theme.</p>;

  return (
    <Card>
      <CardContent className="flex flex-col gap-4">
        <div>
          <h3 className="flex items-center gap-2 text-sm font-semibold"><Sparkles className="h-4 w-4 text-brand" /> Club Theme Editor</h3>
          <p className="text-xs text-muted-foreground">
            {admin
              ? "Set your club's colours and logo. These power the “Club” theme and club accents across OneStats. Colours are saved per workspace and never affect another club."
              : "Your club's approved colours (view only). Ask a workspace administrator to change them."}
          </p>
        </div>
        {loading ? (
          <p className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> Loading…</p>
        ) : (
          <>
            {msg && <p className="text-xs text-success">{msg}</p>}
            {err && <p className="text-xs text-danger">{err}</p>}

            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              {/* Colours */}
              <div className="flex flex-col gap-2.5">
                {FIELDS.map((f) => {
                  const v = draft[f.key];
                  const bad = !!v && !isValidHex(v);
                  return (
                    <div key={f.key} className="flex items-center gap-2">
                      <input type="color" aria-label={`${f.label} colour`} disabled={!admin}
                        value={isValidHex(v) ? v : "#ffffff"}
                        onChange={(e) => set(f.key, e.target.value)}
                        className="h-9 w-10 shrink-0 cursor-pointer rounded-[var(--radius-app)] border border-border bg-card disabled:cursor-not-allowed" />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-medium">{f.label}</span>
                          <input type="text" disabled={!admin} placeholder="#RRGGBB"
                            value={v} onChange={(e) => set(f.key, e.target.value)}
                            className={`w-24 rounded-[var(--radius-app)] border bg-card px-2 py-0.5 text-xs ${bad ? "border-danger" : "border-border"}`} />
                        </div>
                        <div className="truncate text-[10px] text-muted-foreground">{f.hint}</div>
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Logo + live preview */}
              <div className="flex flex-col gap-3">
                <div className="flex items-center gap-3 rounded-[var(--radius-app)] border border-border bg-muted/40 p-2">
                  <div className="flex h-14 w-14 shrink-0 items-center justify-center overflow-hidden rounded-[var(--radius-app)] border border-border bg-white">
                    {logoUrl ? <img src={logoUrl} alt="Club logo" className="h-full w-full object-contain" /> : <ImageUp className="h-5 w-5 text-muted-foreground" />}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="text-xs font-medium">Club logo</div>
                    <div className="text-[10px] text-muted-foreground">{logoUrl ? "Used in the Club theme & suggestions." : "No logo yet — upload one to auto-suggest colours."}</div>
                    {admin && (
                      <div className="mt-1 flex gap-1.5">
                        <Button size="sm" variant="outline" onClick={() => fileRef.current?.click()} disabled={busy}><ImageUp className="h-3.5 w-3.5" /> Upload</Button>
                        {logoUrl && <Button size="sm" variant="ghost" onClick={() => void removeLogo()} disabled={busy}><Trash2 className="h-3.5 w-3.5" /></Button>}
                      </div>
                    )}
                    <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" className="hidden"
                      onChange={(e) => { const f = e.target.files?.[0]; if (f) void onUploadLogo(f); e.target.value = ""; }} />
                  </div>
                </div>
                <div style={previewVars as CSSProperties}>
                  <div className="mb-1 text-[10px] text-muted-foreground">Live preview (Club theme)</div>
                  <ThemeMock themeId="club" mode="light" />
                </div>
              </div>
            </div>

            {warnings.length > 0 && (
              <div className="rounded-[var(--radius-app)] border border-warning/40 bg-warning/10 p-2 text-[11px] text-warning">
                {warnings.map((w) => <div key={w}>⚠ {w}</div>)}
              </div>
            )}
            {invalid.length > 0 && <p className="text-xs text-danger">Enter valid #RRGGBB values before saving.</p>}

            {admin && (
              <div className="flex flex-wrap items-center gap-2 border-t border-border pt-3">
                <Button onClick={() => void save()} disabled={busy || !dirty || invalid.length > 0}>
                  {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null} Save club theme
                </Button>
                <Button variant="outline" onClick={() => void regenerate()} disabled={suggesting || !logoUrl}>
                  {suggesting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wand2 className="h-4 w-4" />} Regenerate from logo
                </Button>
                <Button variant="ghost" onClick={resetSaved} disabled={!dirty}><RotateCcw className="h-4 w-4" /> Restore last saved</Button>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

// Local mix helper for the scoped preview (keeps this component self-contained for preview-only vars).
function mixHex(a: string, b: string, t: number): string {
  const pa = a.replace("#", ""), pb = b.replace("#", "");
  const ra = parseInt(pa.slice(0, 2), 16), ga = parseInt(pa.slice(2, 4), 16), ba = parseInt(pa.slice(4, 6), 16);
  const rb = parseInt(pb.slice(0, 2), 16), gb = parseInt(pb.slice(2, 4), 16), bb = parseInt(pb.slice(4, 6), 16);
  const h = (n: number) => Math.round(n).toString(16).padStart(2, "0");
  return `#${h(ra + (rb - ra) * t)}${h(ga + (gb - ga) * t)}${h(ba + (bb - ba) * t)}`;
}
