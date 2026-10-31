/**
 * Data Quality — scorer-error "linting" over the entered scorecards (audit P3; the OneStats answer to
 * CricketStatz's data-quality reports). Each check lists the offending matches with a click-through to
 * open and fix them. Nothing is auto-corrected; historical imports may show expected gaps, flagged
 * honestly rather than hidden.
 */
import { AlertTriangle, CheckCircle2, ChevronDown, ChevronRight, Info } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ErrorState, LoadingState } from "../../components/states/States";
import { api, ApiError, type DataQualityScan } from "../../lib/api";

export function DataQuality({ workspaceId }: { workspaceId: string }) {
  const navigate = useNavigate();
  const [data, setData] = useState<DataQualityScan | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<Record<string, boolean>>({});

  const load = useCallback(() => {
    setLoading(true); setError(null);
    api.statsDataQuality(workspaceId)
      .then(setData)
      .catch((e) => setError(e instanceof ApiError ? e.message : "Could not run the data-quality checks."))
      .finally(() => setLoading(false));
  }, [workspaceId]);
  useEffect(() => { load(); }, [load]);

  if (loading) return <LoadingState label="Checking the scorecards…" />;
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!data) return null;

  return (
    <div className="flex flex-col gap-3">
      <p className="text-xs text-muted-foreground">{data.note}</p>
      {data.ok ? (
        <div className="flex items-center gap-2 rounded-[var(--radius-app)] border border-success/40 bg-success/5 p-3 text-sm">
          <CheckCircle2 className="h-5 w-5 text-success" aria-hidden /> No scorer-error issues found.
        </div>
      ) : (
        <p className="text-sm">
          <span className="font-semibold">{data.total_issues.toLocaleString()}</span> issue{data.total_issues === 1 ? "" : "s"} across {data.checks.filter((c) => c.count > 0).length} check{data.checks.filter((c) => c.count > 0).length === 1 ? "" : "s"}.
        </p>
      )}
      <div className="flex flex-col gap-2">
        {data.checks.map((c) => {
          const isOpen = open[c.key];
          const tone = c.severity === "warning" ? "text-warning" : "text-muted-foreground";
          return (
            <div key={c.key} className="rounded-[var(--radius-app)] border border-border">
              <button type="button" onClick={() => setOpen((o) => ({ ...o, [c.key]: !o[c.key] }))}
                className="flex w-full items-center gap-2 p-3 text-left">
                {c.count > 0 ? (isOpen ? <ChevronDown className="h-4 w-4" aria-hidden /> : <ChevronRight className="h-4 w-4" aria-hidden />) : <span className="w-4" />}
                {c.severity === "warning"
                  ? <AlertTriangle className={`h-4 w-4 shrink-0 ${tone}`} aria-hidden />
                  : <Info className={`h-4 w-4 shrink-0 ${tone}`} aria-hidden />}
                <span className="flex-1">
                  <span className="text-sm font-medium">{c.title}</span>
                  <span className="block text-xs text-muted-foreground">{c.description}</span>
                </span>
                <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold tabular-nums ${c.count > 0 ? "bg-warning/10 text-warning" : "bg-success/10 text-success"}`}>
                  {c.count}
                </span>
              </button>
              {isOpen && c.count > 0 && (
                <div className="border-t border-border p-2">
                  <div className="flex flex-col gap-1">
                    {c.sample.map((s, i) => (
                      <button key={`${s.match_id}-${i}`} type="button"
                        onClick={() => navigate(`/matches?open=${s.match_id}`)}
                        className="flex items-center justify-between gap-2 rounded-[var(--radius-app)] border border-border px-2 py-1 text-left text-xs hover:border-brand">
                        <span>{s.detail}</span>
                        <span className="text-muted-foreground">{s.match_date ?? "date unknown"} →</span>
                      </button>
                    ))}
                  </div>
                  {c.count > c.sample.length && (
                    <p className="mt-1 text-xs text-muted-foreground">Showing {c.sample.length} of {c.count}.</p>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
