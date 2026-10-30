/**
 * Season Completeness — the graphical overview at the heart of the Research Centre redesign.
 *
 * Each season is a horizontal bar whose segments show verified / scorecard-only / missing matches, with an
 * honest status. Fixture coverage is shown as "Coverage Unknown" until an evidence-backed assessment is
 * recorded — a season is NEVER called complete just because its entered matches have scorecards. Colours
 * come from the theme's semantic tokens (success/warning/danger/muted), so all eight OneStats themes work.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { EmptyState, ErrorState, LoadingState } from "../../components/states/States";
import { api, ApiError, type AutoSyncConnector, type SeasonCompleteness as SC, type SeasonCompletenessRow } from "../../lib/api";
import { useWorkspace } from "../../lib/workspace-context";

// Honest discovery availability per Stage 8 — never claim an archive was searched when it cannot be.
function discoveryStatus(c: AutoSyncConnector): { label: string; tone: "ok" | "warn" | "muted" } {
  if (c.status === "live") return c.auth_required ? { label: "Requires credentials", tone: "warn" } : { label: "Available", tone: "ok" };
  if (c.status === "fixture") return { label: "Available (test data)", tone: "ok" };
  return { label: "Unsupported (interface only)", tone: "muted" };
}

type Sort = "newest" | "oldest" | "most_incomplete" | "least_researched";

const STATUS_LABEL: Record<SeasonCompletenessRow["status"], string> = {
  verified: "Verified",
  needs_attention: "Needs attention",
  incomplete: "Incomplete",
  not_researched: "Not researched",
  coverage_unknown: "Coverage unknown",
  conflicting_evidence: "Conflicting evidence",
};
// theme-aware semantic colour per status (CSS variables redefined per theme; never hard-coded hex)
const STATUS_COLOR: Record<SeasonCompletenessRow["status"], string> = {
  verified: "var(--success)",
  needs_attention: "var(--warning)",
  incomplete: "var(--warning)",
  not_researched: "var(--muted-foreground)",
  coverage_unknown: "var(--muted-foreground)",
  conflicting_evidence: "var(--danger)",
};
const ASSESS_LABEL: Record<string, string> = {
  comprehensive: "Complete — every fixture accounted for",
  partial: "Mostly complete, minor gaps",
  significant_gaps: "Significant gaps remain",
  inactive: "No matches played",
  unassessed: "Not assessed",
};
const ISSUE_LABEL: Record<string, string> = {
  missing_scorecards: "Missing scorecards",
  missing_results: "Missing results",
  unverified_scorecards: "Unverified scorecards",
  fixture_coverage_unknown: "Fixture coverage unknown",
  conflicting_evidence: "Conflicting evidence",
};

export function SeasonCompleteness({ onCreateTask }: { onCreateTask?: () => void }) {
  const { current } = useWorkspace();
  const navigate = useNavigate();
  const workspaceId = current?.id;
  const [data, setData] = useState<SC | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [sort, setSort] = useState<Sort>("newest");
  const [sel, setSel] = useState<SeasonCompletenessRow | null>(null);
  const [connectors, setConnectors] = useState<AutoSyncConnector[] | null>(null);
  const [discoBusy, setDiscoBusy] = useState(false);
  // "Confirm season complete" — records an evidence-backed coverage assessment (washout/forfeit etc.).
  const [assessOpen, setAssessOpen] = useState(false);
  const [assessClass, setAssessClass] = useState<"comprehensive" | "partial" | "significant_gaps" | "inactive">("comprehensive");
  const [assessBasis, setAssessBasis] = useState("");
  const [assessBusy, setAssessBusy] = useState(false);
  const [assessErr, setAssessErr] = useState<string | null>(null);

  const load = useCallback((keepSelId?: string) => {
    if (!workspaceId) return;
    setLoading(true); setError(null);
    api.researchSeasonCompleteness(workspaceId)
      .then((d) => {
        setData(d);
        if (keepSelId) setSel(d.seasons.find((s) => s.season_id === keepSelId) ?? null);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : "Could not load season completeness."))
      .finally(() => setLoading(false));
  }, [workspaceId]);

  useEffect(() => { load(); }, [load]);

  const saveAssessment = () => {
    if (!workspaceId || !sel) return;
    if ((assessClass === "comprehensive" || assessClass === "inactive") && !assessBasis.trim()) {
      setAssessErr("Please record the evidence (e.g. the fixture source, and any washouts or forfeits).");
      return;
    }
    setAssessBusy(true); setAssessErr(null);
    api.researchSetAssessment(workspaceId, {
      season_id: sel.season_id, assessed_class: assessClass,
      competition_id: sel.competition_id, basis: assessBasis.trim() || null,
    })
      .then(() => { setAssessOpen(false); setAssessBasis(""); load(sel.season_id); })
      .catch((e) => setAssessErr(e instanceof ApiError ? e.message : "Could not save the assessment."))
      .finally(() => setAssessBusy(false));
  };

  const seasons = useMemo(() => {
    const rows = [...(data?.seasons ?? [])];
    const key = (r: SeasonCompletenessRow) => r.start_date ?? r.label;
    const incompleteness = (r: SeasonCompletenessRow) => r.missing_scorecards + r.missing_results + r.draft_matches + r.disputed_matches;
    if (sort === "newest") rows.sort((a, b) => String(key(b)).localeCompare(String(key(a))));
    else if (sort === "oldest") rows.sort((a, b) => String(key(a)).localeCompare(String(key(b))));
    else if (sort === "most_incomplete") rows.sort((a, b) => incompleteness(b) - incompleteness(a));
    else if (sort === "least_researched") rows.sort((a, b) => Number(a.research_recorded) - Number(b.research_recorded) || incompleteness(b) - incompleteness(a));
    return rows;
  }, [data, sort]);

  if (loading) return <LoadingState label="Assessing season completeness…" />;
  if (error) return <ErrorState message={error} />;
  if (!data || seasons.length === 0) {
    return <EmptyState title="No seasons yet"
      description="No historical coverage has been established yet. Create a research project or establish the known fixtures to begin." />;
  }

  if (sel) {
    const metric = (label: string, value: string | number) => (
      <div className="rounded-[var(--radius-app)] border border-border p-3">
        <div className="text-xs text-muted-foreground">{label}</div>
        <div className="text-xl font-semibold tabular-nums">{value}</div>
      </div>
    );
    return (
      <div className="flex flex-col gap-3">
        <button type="button" onClick={() => { setSel(null); setConnectors(null); setAssessOpen(false); }} className="self-start text-xs text-brand hover:underline">← All seasons</button>
        <div className="flex items-center gap-2">
          <h4 className="text-base font-semibold">{sel.label}</h4>
          <span className="flex items-center gap-1 text-xs">
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: STATUS_COLOR[sel.status] }} aria-hidden />
            {STATUS_LABEL[sel.status]}
          </span>
        </div>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {metric("Known matches", sel.known_matches)}
          {metric("With scorecard", `${sel.with_scorecard} of ${sel.known_matches}`)}
          {metric("Missing scorecards", sel.missing_scorecards)}
          {metric("Missing results", sel.missing_results)}
          {metric("Verified", `${sel.verified_matches} of ${sel.known_matches}`)}
          {metric("Awaiting / draft", sel.draft_matches)}
          {metric("Conflicting", sel.disputed_matches)}
          {metric("Fixture coverage", sel.fixture_coverage === "established" ? "Established" : "Unknown")}
        </div>
        {sel.fixture_coverage === "unknown" && (
          <p className="text-xs text-muted-foreground">
            Fixture coverage is unknown — the expected number of fixtures for this season has not been
            established, so completeness over the known matches does not mean the season is complete.
          </p>
        )}
        {sel.issues.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {sel.issues.map((iss) => (
              <span key={iss} className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">{ISSUE_LABEL[iss] ?? iss}</span>
            ))}
          </div>
        )}
        {sel.assessed_class && !assessOpen && (
          <p className="text-xs text-muted-foreground">
            Recorded assessment: <span className="font-medium text-foreground">{ASSESS_LABEL[sel.assessed_class] ?? sel.assessed_class}</span>.
          </p>
        )}
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={() => navigate("/matches")}
            className="rounded-[var(--radius-app)] border border-border px-3 py-1.5 text-sm hover:border-brand">View matches</button>
          {onCreateTask && (
            <button type="button" onClick={onCreateTask}
              className="rounded-[var(--radius-app)] border border-border px-3 py-1.5 text-sm hover:border-brand">Create research task</button>
          )}
          <button type="button" disabled={discoBusy || !workspaceId}
            onClick={() => { if (!workspaceId) return; setDiscoBusy(true); api.autosyncConnectors(workspaceId).then(setConnectors).catch(() => setConnectors([])).finally(() => setDiscoBusy(false)); }}
            className="rounded-[var(--radius-app)] border border-border px-3 py-1.5 text-sm hover:border-brand disabled:opacity-50">
            {discoBusy ? "Checking…" : "Find sources"}
          </button>
          <button type="button" onClick={() => { setAssessOpen((o) => !o); setAssessClass((sel.assessed_class as typeof assessClass) || "comprehensive"); setAssessErr(null); }}
            className="rounded-[var(--radius-app)] border border-border px-3 py-1.5 text-sm hover:border-brand">
            {sel.assessed_class ? "Update assessment" : "Confirm season complete"}
          </button>
        </div>
        {assessOpen && (
          <div className="flex flex-col gap-2 rounded-[var(--radius-app)] border border-border p-3">
            <div className="text-xs text-muted-foreground">
              Record an evidence-backed assessment of this season's fixtures. A season is only marked complete
              when every expected fixture is accounted for — including washouts, forfeits and abandoned matches
              that have no scorecard. This is the only way a season becomes "Verified"; it is never inferred
              from the matches entered.
            </div>
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-xs text-muted-foreground">Fixture coverage</span>
              <select value={assessClass} onChange={(e) => setAssessClass(e.target.value as typeof assessClass)}
                className="rounded-[var(--radius-app)] border border-border bg-background px-2 py-1.5 text-sm">
                <option value="comprehensive">Complete — every fixture accounted for</option>
                <option value="partial">Mostly complete — minor gaps remain</option>
                <option value="significant_gaps">Significant gaps remain</option>
                <option value="inactive">No matches played this season</option>
              </select>
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-xs text-muted-foreground">
                Evidence / basis{(assessClass === "comprehensive" || assessClass === "inactive") ? " (required)" : " (optional)"}
              </span>
              <textarea value={assessBasis} onChange={(e) => setAssessBasis(e.target.value)} rows={3}
                placeholder="e.g. 14 fixtures confirmed from the ADCA handbook; Round 12 washed out (no play) and Round 7 was a forfeit, so no scorecards exist."
                className="rounded-[var(--radius-app)] border border-border bg-background px-2 py-1.5 text-sm" />
            </label>
            {assessErr && <p className="text-xs text-danger">{assessErr}</p>}
            <div className="flex gap-2">
              <button type="button" disabled={assessBusy} onClick={saveAssessment}
                className="rounded-[var(--radius-app)] bg-brand px-3 py-1.5 text-sm font-medium text-brand-foreground hover:opacity-90 disabled:opacity-50">
                {assessBusy ? "Saving…" : "Save assessment"}
              </button>
              <button type="button" disabled={assessBusy} onClick={() => { setAssessOpen(false); setAssessErr(null); }}
                className="rounded-[var(--radius-app)] border border-border px-3 py-1.5 text-sm hover:border-brand">Cancel</button>
            </div>
          </div>
        )}
        {connectors && (
          <div className="flex flex-col gap-1 rounded-[var(--radius-app)] border border-border p-3">
            <div className="text-xs text-muted-foreground">
              Historical source discovery for {sel.label}. Nothing is searched unless a connector is live —
              interface-only connectors are listed so you know what is possible, never claimed as searched.
            </div>
            {connectors.length === 0 && <div className="text-sm text-muted-foreground">No discovery connectors configured.</div>}
            {connectors.map((c) => {
              const d = discoveryStatus(c);
              return (
                <div key={c.connector_id} className="flex items-center gap-2 border-t border-border pt-1.5 text-sm first:border-0">
                  <span className="font-medium">{c.provider}</span>
                  {c.formats.length > 0 && <span className="text-xs text-muted-foreground">{c.formats.join(", ")}</span>}
                  <span className="ml-auto text-xs" style={{ color: d.tone === "ok" ? "var(--success)" : d.tone === "warn" ? "var(--warning)" : "var(--muted-foreground)" }}>
                    {d.label}
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </div>
    );
  }

  const sortBtn = (key: Sort, label: string) => (
    <button type="button" onClick={() => setSort(key)}
      className={`rounded-[var(--radius-app)] border px-2.5 py-1 text-xs ${sort === key ? "border-brand bg-brand/10 font-medium text-brand" : "border-border text-muted-foreground hover:text-foreground"}`}>
      {label}
    </button>
  );

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-muted-foreground">Sort</span>
        {sortBtn("newest", "Newest")}
        {sortBtn("oldest", "Oldest")}
        {sortBtn("most_incomplete", "Most incomplete")}
        {sortBtn("least_researched", "Least researched")}
      </div>
      <p className="text-xs text-muted-foreground">{data.methodology.note}</p>
      <div className="flex flex-col gap-1.5">
        {seasons.map((r) => {
          const known = Math.max(r.known_matches, 1);
          const verified = (r.verified_matches / known) * 100;
          const scoredOnly = (Math.max(r.with_scorecard - r.verified_matches, 0) / known) * 100;
          const missing = (r.missing_scorecards / known) * 100;
          return (
            <button key={r.season_id} type="button" onClick={() => { setSel(r); setConnectors(null); setAssessOpen(false); }}
              className="grid grid-cols-[6rem_1fr_9rem] items-center gap-3 rounded-[var(--radius-app)] border border-border px-3 py-2 text-left hover:border-brand">
              <div>
                <div className="text-sm font-medium">{r.label}</div>
                <div className="text-[11px] text-muted-foreground">{r.known_matches} match{r.known_matches === 1 ? "" : "es"}</div>
              </div>
              <div>
                <div className="flex h-3 overflow-hidden rounded-full bg-muted" role="img"
                  aria-label={`${r.verified_matches} verified, ${r.with_scorecard - r.verified_matches} scored, ${r.missing_scorecards} missing scorecards`}>
                  <div style={{ width: `${verified}%`, background: "var(--success)" }} />
                  <div style={{ width: `${scoredOnly}%`, background: "var(--warning)" }} />
                  <div style={{ width: `${missing}%`, background: "var(--danger)" }} />
                </div>
                {r.issues.length > 0 && (
                  <div className="mt-1 flex flex-wrap gap-1">
                    {r.issues.map((iss) => (
                      <span key={iss} className="rounded-full bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                        {ISSUE_LABEL[iss] ?? iss}
                      </span>
                    ))}
                  </div>
                )}
              </div>
              <div className="flex items-center justify-end gap-1.5 text-xs">
                <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: STATUS_COLOR[r.status] }} aria-hidden />
                <span className="font-medium">{STATUS_LABEL[r.status]}</span>
              </div>
            </button>
          );
        })}
      </div>
      <div className="flex flex-wrap gap-3 text-[11px] text-muted-foreground">
        <Legend color="var(--success)" label="Verified" />
        <Legend color="var(--warning)" label="Scored, unverified" />
        <Legend color="var(--danger)" label="Missing scorecard" />
      </div>
    </div>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1">
      <span className="h-2 w-3 rounded-sm" style={{ background: color }} aria-hidden /> {label}
    </span>
  );
}
