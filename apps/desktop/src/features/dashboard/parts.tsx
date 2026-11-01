/**
 * Reusable building blocks for the ONE shared dashboard architecture (Part 14). The role-specific
 * dashboards (Organisation Admin, Researcher, Scorecard Editor, Data Verifier, Viewer/Analyst) are
 * all composed from these same pieces — never six separate UIs. Presentational only: no data
 * fetching, theme-token styling (works across all 8 themes + workspace branding), accessible, and
 * with explicit empty states.
 */
import type { ReactNode } from "react";
import { CheckCircle2 } from "lucide-react";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import type { DashboardTask } from "./tasks";

export function SectionCard({ title, icon, children }: { title: string; icon?: ReactNode; children: ReactNode }) {
  return (
    <Card><CardContent className="flex flex-col gap-2">
      <h3 className="flex items-center gap-2 text-sm font-semibold">{icon}{title}</h3>
      {children}
    </CardContent></Card>
  );
}

export function StatTile({ label, value, icon, onClick }: {
  label: string; value: number | undefined; icon?: ReactNode; onClick?: () => void;
}) {
  return (
    <button
      type="button"
      disabled={!onClick}
      onClick={onClick}
      className={`flex flex-col gap-1 rounded-[var(--radius-app)] border border-border p-3 text-left ${onClick ? "hover:border-brand" : ""}`}
    >
      <div className="flex items-center gap-2 text-xs text-muted-foreground">{icon}{label}</div>
      <div className="text-2xl font-semibold tabular-nums">{value ?? "—"}</div>
    </button>
  );
}

export function StatGrid({ children }: { children: ReactNode }) {
  return <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">{children}</div>;
}

/** The unified "My Tasks" list — role-filtered actionable items, or a clear done/empty state. */
export function MyTasks({ tasks, onOpen }: { tasks: DashboardTask[]; onOpen: (to: string) => void }) {
  const actionable = tasks.filter((t) => t.count > 0);
  if (tasks.length === 0) {
    return <p className="text-xs text-muted-foreground">No tasks are assigned to your role in this workspace.</p>;
  }
  if (actionable.length === 0) {
    return (
      <p className="flex items-center gap-2 text-xs text-muted-foreground">
        <CheckCircle2 className="h-4 w-4 text-success" aria-hidden /> You're all caught up — nothing needs your attention.
      </p>
    );
  }
  return (
    <>
      {actionable.map((t) => (
        <button
          key={t.key}
          type="button"
          onClick={() => onOpen(t.to)}
          className="flex items-center gap-2 rounded-[var(--radius-app)] border border-border px-2 py-1.5 text-left text-sm hover:border-brand"
        >
          <Badge variant={t.tone}>{t.count}</Badge>
          <span>{t.label}</span>
        </button>
      ))}
    </>
  );
}

export interface QuickAction { label: string; icon: ReactNode; to: string; perm?: string }

/** A row of quick actions, each shown only if the user holds its permission. */
export function QuickActionBar({ actions, has, onOpen }: {
  actions: QuickAction[]; has: (perm: string) => boolean; onOpen: (to: string) => void;
}) {
  const visible = actions.filter((a) => !a.perm || has(a.perm));
  if (visible.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-2">
      {visible.map((a) => (
        <Button key={a.label} size="sm" variant="outline" onClick={() => onOpen(a.to)}>{a.icon}{a.label}</Button>
      ))}
    </div>
  );
}

export function ActivityList({ items }: { items: { action: string; category: string; at: string | null }[] }) {
  if (items.length === 0) return <p className="text-xs text-muted-foreground">No activity yet.</p>;
  return (
    <>
      {items.map((a, i) => (
        <div key={i} className="flex items-center gap-2 text-sm">
          <Badge variant="muted">{a.category}</Badge>
          <span className="text-muted-foreground">{a.action}</span>
          <span className="ml-auto text-xs text-muted-foreground">{a.at ? new Date(a.at).toLocaleString() : ""}</span>
        </div>
      ))}
    </>
  );
}
