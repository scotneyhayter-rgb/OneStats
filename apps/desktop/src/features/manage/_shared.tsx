import { Building2 } from "lucide-react";
import type { ReactNode } from "react";
import { EmptyState } from "../../components/states/States";
import { useAuth } from "../../lib/auth";
import { canManage } from "../../lib/permissions";
import { useWorkspace } from "../../lib/workspace-context";

/** Resolved context shared by every management screen. */
export function useManage() {
  const { user } = useAuth();
  const { current } = useWorkspace();
  return {
    user,
    workspace: current,
    workspaceId: current?.id ?? null,
    canManage: canManage(user, current),
  };
}

/** Prompt shown when no workspace is selected (management is always workspace-scoped). */
export function NoWorkspace() {
  return (
    <EmptyState
      icon={<Building2 className="h-8 w-8" aria-hidden />}
      title="No workspace selected"
      description="Choose a workspace from the switcher in the sidebar, or open one from My Workspaces."
    />
  );
}

/** Labelled form field. */
export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: ReactNode;
  children: ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="font-medium">{label}</span>
      {children}
      {hint && <span className="text-xs text-muted-foreground">{hint}</span>}
    </label>
  );
}

/** A read-only key/value row for detail panels. */
export function Detail({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 py-1 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right">{children}</span>
    </div>
  );
}

/** Renders a value that may be unknown, keeping "unknown" visually explicit (never invented). */
export function Unknown({ value }: { value: ReactNode }) {
  if (value === null || value === undefined || value === "") {
    return <span className="italic text-muted-foreground">Unknown</span>;
  }
  return <>{value}</>;
}

export function humanise(s: string): string {
  return s.replace(/_/g, " ");
}
