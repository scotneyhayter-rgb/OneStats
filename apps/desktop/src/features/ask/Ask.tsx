/**
 * Ask OneStats (Phase 14) — a natural-language statistics assistant. Every answer is produced by the one
 * deterministic engine: the question is mapped to a catalogue report + scope, and the numbers come from
 * that report. Nothing is fabricated — an unmappable question offers the nearest supported reports.
 */
import { MessageCircleQuestion, Search } from "lucide-react";
import { useCallback, useState } from "react";
import { AppShell } from "../../components/layout/AppShell";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import { Input } from "../../components/ui/input";
import { api, ApiError, type AskAnswer, type StatColumn } from "../../lib/api";
import { useWorkspace } from "../../lib/workspace-context";

const EXAMPLES = [
  "Who has scored the most runs?",
  "Who has the most wickets in grand finals?",
  "Which captain has the best winning percentage?",
  "What is the highest partnership?",
  "Most consecutive wins as captain?",
  "Best bowling average (min 50 wickets)?",
];

function fmt(value: unknown, col: StatColumn): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (col.decimals != null && typeof value === "number") return value.toFixed(col.decimals);
  return String(value);
}

export function Ask() {
  const { current } = useWorkspace();
  const [q, setQ] = useState("");
  const [answer, setAnswer] = useState<AskAnswer | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const askQuestion = useCallback(async (question: string) => {
    if (!current || !question.trim()) return;
    setBusy(true); setError(null);
    try {
      setAnswer(await api.askOneStats(current.id, question.trim()));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not answer that question.");
      setAnswer(null);
    } finally { setBusy(false); }
  }, [current]);

  if (!current) return <AppShell title="Ask OneStats" subtitle="Select a workspace"><div /></AppShell>;

  return (
    <AppShell title="Ask OneStats" subtitle="Natural-language statistical queries — answers from verified records only">
      <div className="mx-auto flex max-w-4xl flex-col gap-4">
        {error && <p className="rounded-[var(--radius-app)] border border-danger/40 bg-danger/5 px-3 py-2 text-sm text-danger">{error}</p>}

        <Card><CardContent className="flex flex-col gap-3">
          <form onSubmit={(e) => { e.preventDefault(); void askQuestion(q); }} className="flex flex-wrap items-center gap-2">
            <div className="relative min-w-[14rem] flex-1">
              <Search className="pointer-events-none absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
              <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask about your club's statistics…" className="pl-8" />
            </div>
            <Button size="sm" type="submit" disabled={busy || !q.trim()}>{busy ? "Thinking…" : "Ask"}</Button>
          </form>
          <div className="flex flex-wrap gap-1">
            {EXAMPLES.map((ex) => (
              <button key={ex} type="button" onClick={() => { setQ(ex); void askQuestion(ex); }}
                className="rounded-[var(--radius-app)] border border-border px-2 py-1 text-xs text-muted-foreground hover:border-brand hover:text-brand">
                {ex}
              </button>
            ))}
          </div>
          <p className="text-xs text-muted-foreground">
            Every answer comes from the deterministic statistics engine on approved scorecards only. OneStats never invents a figure.
          </p>
        </CardContent></Card>

        {answer && !answer.matched && (
          <Card><CardContent className="flex flex-col gap-2">
            <div className="flex items-center gap-2 text-sm"><MessageCircleQuestion className="h-4 w-4 text-brand" aria-hidden />{answer.message}</div>
            {answer.suggestions && answer.suggestions.length > 0 && (
              <div className="flex flex-col gap-1">
                <span className="text-xs font-medium">Closest reports:</span>
                {answer.suggestions.map((s) => (
                  <span key={s.id} className="text-sm">{s.name} <Badge variant="muted">{s.category}</Badge></span>
                ))}
              </div>
            )}
          </CardContent></Card>
        )}

        {answer && answer.matched && (
          <Card><CardContent className="flex flex-col gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-sm font-semibold">{answer.report_name}</h3>
              {answer.category && <Badge variant="muted">{answer.category}</Badge>}
              {answer.confidence && <Badge variant={answer.confidence === "high" ? "success" : "warning"}>{answer.confidence} confidence</Badge>}
            </div>
            {answer.answer_summary && <p className="text-base font-medium">{answer.answer_summary}</p>}
            <p className="text-xs text-muted-foreground">{answer.interpretation}</p>
            {answer.rows && answer.columns && answer.rows.length > 0 && (
              <div className="max-h-[28rem] overflow-auto rounded-[var(--radius-app)] border border-border">
                <table className="w-full border-collapse text-sm">
                  <thead className="sticky top-0 bg-brand text-white">
                    <tr>{answer.columns.map((col) => (
                      <th key={col.key} className={`whitespace-nowrap px-2 py-1.5 font-semibold ${col.align === "right" ? "text-right" : "text-left"}`}>{col.label}</th>
                    ))}</tr>
                  </thead>
                  <tbody>
                    {answer.rows.map((r, i) => (
                      <tr key={i} className={i % 2 ? "bg-muted/30" : ""}>
                        {answer.columns!.map((col) => (
                          <td key={col.key} className={`whitespace-nowrap px-2 py-1 tabular-nums ${col.align === "right" ? "text-right" : "text-left"}`}>
                            {fmt(r[col.key], col)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {answer.rows && answer.rows.length === 0 && <p className="text-sm text-muted-foreground">No verified data matches that question yet.</p>}
            {answer.qualifications && answer.qualifications.length > 0 && (
              <div className="flex flex-col gap-0.5 border-t border-border pt-2">
                {answer.qualifications.map((qn, i) => <p key={i} className="text-xs text-muted-foreground">• {qn}</p>)}
              </div>
            )}
          </CardContent></Card>
        )}
      </div>
    </AppShell>
  );
}
