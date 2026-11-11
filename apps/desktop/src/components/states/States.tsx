import { AlertTriangle, Inbox, Loader2 } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "../ui/button";

/** Consistent loading / empty / error states reused across the app (deliverable 10). */

export function LoadingState({ label = "Loading..." }: { label?: string }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex items-center gap-3 p-6 text-muted-foreground"
    >
      <Loader2 className="h-5 w-5 animate-spin" aria-hidden />
      <span>{label}</span>
    </div>
  );
}

export function EmptyState({
  title = "Nothing here yet",
  description,
  icon,
}: {
  title?: string;
  description?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 p-10 text-center">
      <div className="text-muted-foreground">{icon ?? <Inbox className="h-8 w-8" aria-hidden />}</div>
      <p className="font-medium">{title}</p>
      {description && (
        <p className="max-w-sm text-sm text-muted-foreground">{description}</p>
      )}
    </div>
  );
}

export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div
      role="alert"
      className="flex flex-col items-start gap-3 rounded-[var(--radius-app)] border border-danger/40 bg-danger/5 p-5"
    >
      <div className="flex items-center gap-2 font-medium text-danger">
        <AlertTriangle className="h-5 w-5" aria-hidden />
        <span>Something went wrong</span>
      </div>
      <p className="text-sm text-muted-foreground">{message}</p>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}

/** A table-shaped loading placeholder — a calmer, more "finished" load than a bare spinner for data
 * grids (leaderboards, reports, directories). Rows/cols are approximate; it only needs to feel right. */
export function TableSkeleton({ rows = 8, cols = 6 }: { rows?: number; cols?: number }) {
  return (
    <div role="status" aria-live="polite" aria-label="Loading"
      className="overflow-hidden rounded-[var(--radius-app)] border border-border">
      <div className="flex gap-3 border-b border-border bg-muted/40 px-3 py-2">
        {Array.from({ length: cols }).map((_, i) => (
          <div key={i} className={`h-3 animate-pulse rounded bg-muted ${i === 0 ? "w-8" : "flex-1"}`} />
        ))}
      </div>
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="flex items-center gap-3 border-b border-border/60 px-3 py-2 last:border-0">
          {Array.from({ length: cols }).map((_, c) => (
            <div key={c} className={`h-3 animate-pulse rounded bg-muted/70 ${c === 0 ? "w-8" : "flex-1"}`} />
          ))}
        </div>
      ))}
    </div>
  );
}
