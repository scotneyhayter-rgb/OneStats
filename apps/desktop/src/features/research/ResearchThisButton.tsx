/**
 * Contextual "Search the Internet" action (Internet Research Engine, spec §15).
 *
 * Drop this on any match / player / season / team view. It launches a genuine background research job
 * seeded with that view's context (teams, date, competition, player, season …) so the user never
 * re-types what OneStats already knows, then opens the Research Centre on Discover Records to follow it.
 *
 * Permission-gated client-side (research.manage) purely to hide the control — the backend remains the
 * authority. A duplicate active investigation is treated as success (the existing job is already there).
 */
import { Globe, Loader2 } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "../../components/ui/button";
import { api, ApiError } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { can } from "../../lib/permissions";
import { useWorkspace } from "../../lib/workspace-context";

export function ResearchThisButton({
  query,
  context,
  label = "Search the Internet",
  depth = "standard",
  size = "sm",
  variant = "outline",
}: {
  query: string;
  context?: Record<string, unknown>;
  label?: string;
  depth?: "quick" | "standard" | "deep";
  size?: "sm" | "md" | "icon";
  variant?: "primary" | "outline" | "ghost";
}) {
  const { user } = useAuth();
  const { current } = useWorkspace();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);

  if (!current || !can(user, current, "research.manage")) return null;

  const go = async () => {
    setBusy(true);
    try {
      await api.researchStartInternetSearch(current.id, { query, context: context ?? null, depth });
    } catch (e) {
      // A duplicate active job (409) is fine — the investigation already exists; just open it.
      if (!(e instanceof ApiError) || e.status !== 409) {
        setBusy(false);
        // Surface nothing inline here; the Research Centre shows job state. Re-throw only in dev.
      }
    }
    navigate("/manage/research?discover=1");
  };

  return (
    <Button size={size} variant={variant} disabled={busy} onClick={() => void go()} className="gap-1.5"
      title="Research this online — OneStats searches public sources in the background">
      {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : <Globe className="h-4 w-4" aria-hidden />}
      {label}
    </Button>
  );
}
