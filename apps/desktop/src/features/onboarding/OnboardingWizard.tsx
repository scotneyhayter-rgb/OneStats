import { Check, ChevronLeft, ChevronRight, Rocket } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AppShell } from "../../components/layout/AppShell";
import { ErrorState } from "../../components/states/States";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import { ApiError, api } from "../../lib/api";
import { bestForeground, contrastRatio, isValidHex } from "../../lib/color";
import { useWorkspace } from "../../lib/workspace-context";

const DRAFT_KEY = "onestats.onboarding.draft";
const STEPS = ["Organisation", "Branding", "Programs", "Review"];
const PROGRAMS = ["Seniors", "Juniors", "Women's", "Girls'", "All Abilities", "Veterans/Masters"];
const COLOURS = [
  ["primary", "Primary"],
  ["secondary", "Secondary"],
  ["third", "Third"],
  ["fourth", "Fourth"],
  ["accent", "Accent"],
] as const;

type State = {
  organisation: { name: string; short_name: string; type: string; tagline: string };
  branding: Record<string, string>;
  programs: string[];
};

const EMPTY: State = {
  organisation: { name: "", short_name: "", type: "club", tagline: "" },
  branding: { primary: "#2563eb", accent: "#0ea5e9", theme_mode: "system" },
  programs: ["Seniors"],
};

const input =
  "w-full rounded-[var(--radius-app)] border border-border bg-card px-3 py-2 text-sm focus-visible:outline-2 focus-visible:outline-[var(--ring)]";

export function OnboardingWizard() {
  const nav = useNavigate();
  const { reload, setCurrent } = useWorkspace();
  const [draftId, setDraftId] = useState<string | null>(null);
  const [step, setStep] = useState(0);
  const [state, setState] = useState<State>(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const stored = localStorage.getItem(DRAFT_KEY);
        if (stored) {
          const d = await api.getDraft(stored);
          if (d.status === "in_progress") {
            setDraftId(d.id);
            setState({ ...EMPTY, ...(d.state as Partial<State>) });
            setStep(Math.min((d.current_step ?? 1) - 1, STEPS.length - 1));
            return;
          }
        }
      } catch {
        /* stale draft; start fresh */
      }
      try {
        const d = await api.startDraft("club");
        setDraftId(d.id);
        localStorage.setItem(DRAFT_KEY, d.id);
      } catch (e) {
        setError(e instanceof ApiError ? e.message : "Could not start onboarding");
      }
    })();
  }, []);

  const org = state.organisation;
  const canNext = step !== 0 || (org.name.trim() !== "" && org.short_name.trim() !== "");

  async function save(next: number) {
    if (!draftId) return;
    setBusy(true);
    setError(null);
    try {
      await api.saveDraft(draftId, state as unknown as Record<string, unknown>, next + 1);
      setStep(next);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }

  async function activate() {
    if (!draftId) return;
    setBusy(true);
    setError(null);
    try {
      await api.saveDraft(draftId, state as unknown as Record<string, unknown>, STEPS.length);
      const res = await api.activateDraft(draftId);
      localStorage.removeItem(DRAFT_KEY);
      await reload();
      setCurrent(res.workspace_id);
      nav("/dashboard");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Activation failed");
    } finally {
      setBusy(false);
    }
  }

  const primary = isValidHex(state.branding.primary) ? state.branding.primary : "#2563eb";
  const fg = bestForeground(primary);
  const ratio = useMemo(() => contrastRatio(primary, fg).toFixed(2), [primary, fg]);

  return (
    <AppShell title="Create a workspace" subtitle="Set up a new cricket organisation">
      <ol className="mb-6 flex flex-wrap gap-2 text-sm" aria-label="Progress">
        {STEPS.map((label, i) => (
          <li
            key={label}
            className={`flex items-center gap-2 rounded-full px-3 py-1 ${
              i === step ? "bg-brand text-brand-foreground" : i < step ? "bg-muted text-foreground" : "bg-muted text-muted-foreground"
            }`}
          >
            {i < step ? <Check className="h-3.5 w-3.5" aria-hidden /> : <span>{i + 1}</span>}
            {label}
          </li>
        ))}
      </ol>

      <Card>
        <CardContent className="py-6">
          {step === 0 && (
            <div className="grid gap-4 md:max-w-lg">
              <label className="text-sm">
                <span className="mb-1 block text-muted-foreground">Organisation name *</span>
                <input className={input} value={org.name}
                  onChange={(e) => setState((s) => ({ ...s, organisation: { ...s.organisation, name: e.target.value } }))} />
              </label>
              <label className="text-sm">
                <span className="mb-1 block text-muted-foreground">Unique identifier (short name) *</span>
                <input className={input} value={org.short_name} placeholder="e.g. rmcc"
                  onChange={(e) => setState((s) => ({ ...s, organisation: { ...s.organisation, short_name: e.target.value } }))} />
              </label>
              <label className="text-sm">
                <span className="mb-1 block text-muted-foreground">Type</span>
                <select className={input} value={org.type}
                  onChange={(e) => setState((s) => ({ ...s, organisation: { ...s.organisation, type: e.target.value } }))}>
                  <option value="club">Club</option>
                  <option value="association">Association</option>
                  <option value="international">International</option>
                  <option value="custom">Custom</option>
                </select>
              </label>
              <label className="text-sm">
                <span className="mb-1 block text-muted-foreground">Tagline (optional)</span>
                <input className={input} value={org.tagline}
                  onChange={(e) => setState((s) => ({ ...s, organisation: { ...s.organisation, tagline: e.target.value } }))} />
              </label>
            </div>
          )}

          {step === 1 && (
            <div className="grid gap-6 md:grid-cols-2">
              <div className="space-y-3">
                {COLOURS.map(([key, label]) => (
                  <label key={key} className="flex items-center gap-3 text-sm">
                    <input type="color" value={state.branding[key] ?? "#000000"}
                      onChange={(e) => setState((s) => ({ ...s, branding: { ...s.branding, [key]: e.target.value } }))}
                      className="h-8 w-10 rounded border border-border" aria-label={label} />
                    <span className="w-24 text-muted-foreground">{label}</span>
                    <input className={input} value={state.branding[key] ?? ""}
                      onChange={(e) => setState((s) => ({ ...s, branding: { ...s.branding, [key]: e.target.value } }))} />
                  </label>
                ))}
              </div>
              <div>
                <p className="mb-2 text-sm text-muted-foreground">Live preview</p>
                <div className="rounded-[var(--radius-app)] p-6" style={{ background: primary, color: fg }}>
                  <div className="text-lg font-semibold">{org.name || "Your organisation"}</div>
                  <div className="text-sm opacity-90">{org.tagline || "Cricket Statistics Made Simple"}</div>
                </div>
                <p className={`mt-2 text-xs ${Number(ratio) >= 4.5 ? "text-success" : "text-warning"}`}>
                  Contrast {ratio}:1 — {Number(ratio) >= 4.5 ? "meets WCAG AA" : "below WCAG AA (4.5:1)"}
                </p>
              </div>
            </div>
          )}

          {step === 2 && (
            <div className="grid gap-2 md:max-w-md">
              <p className="text-sm text-muted-foreground">Which cricket programs does this organisation run?</p>
              {PROGRAMS.map((p) => (
                <label key={p} className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={state.programs.includes(p)}
                    onChange={(e) =>
                      setState((s) => ({
                        ...s,
                        programs: e.target.checked ? [...s.programs, p] : s.programs.filter((x) => x !== p),
                      }))
                    } />
                  {p}
                </label>
              ))}
            </div>
          )}

          {step === 3 && (
            <div className="space-y-2 text-sm">
              <p className="font-medium">Review &amp; activate</p>
              <div className="text-muted-foreground">
                <div><b className="text-foreground">{org.name}</b> ({org.short_name}) · {org.type}</div>
                {org.tagline && <div>{org.tagline}</div>}
                <div>Programs: {state.programs.join(", ") || "—"}</div>
                <div>Primary colour: {primary}</div>
              </div>
              <p className="pt-2 text-muted-foreground">
                Activating creates the workspace, its branding, and makes you a Super
                Administrator of it. You can refine everything afterwards.
              </p>
            </div>
          )}

          {error && <div className="mt-4"><ErrorState message={error} /></div>}

          <div className="mt-6 flex items-center justify-between">
            <Button variant="ghost" disabled={step === 0 || busy} onClick={() => setStep((s) => s - 1)}>
              <ChevronLeft className="h-4 w-4" aria-hidden /> Back
            </Button>
            {step < STEPS.length - 1 ? (
              <Button disabled={!canNext || busy} onClick={() => void save(step + 1)}>
                {busy ? "Saving..." : "Next"} <ChevronRight className="h-4 w-4" aria-hidden />
              </Button>
            ) : (
              <Button disabled={busy} onClick={() => void activate()}>
                <Rocket className="h-4 w-4" aria-hidden /> {busy ? "Activating..." : "Activate workspace"}
              </Button>
            )}
          </div>
        </CardContent>
      </Card>
    </AppShell>
  );
}
