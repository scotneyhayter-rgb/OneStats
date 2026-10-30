/**
 * Newspaper Search — find digitised historical newspaper articles (via Trove, the National Library of
 * Australia) and save the relevant ones into the research Source Library. Discovery ends at the article
 * link: nothing here creates match data. Transcribing a scorecard from an article stays a human step in
 * the reconstruction workflow.
 */
import { ExternalLink, Newspaper, Search } from "lucide-react";
import { useState } from "react";
import { EmptyState } from "../../components/states/States";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { api, ApiError, type NewspaperArticle, type NewspaperSearchResult } from "../../lib/api";

export function NewspaperSearch({ workspaceId, onSaved }: { workspaceId: string; onSaved?: (msg: string) => void }) {
  const [q, setQ] = useState("");
  const [yearFrom, setYearFrom] = useState("");
  const [yearTo, setYearTo] = useState("");
  const [paper, setPaper] = useState("");
  const [data, setData] = useState<NewspaperSearchResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<Set<string>>(new Set());
  const [savingId, setSavingId] = useState<string | null>(null);

  const search = async () => {
    if (!q.trim()) return;
    setBusy(true); setError(null); setData(null); setSaved(new Set());
    try {
      const yf = yearFrom.trim() ? Number(yearFrom) : undefined;
      const yt = yearTo.trim() ? Number(yearTo) : undefined;
      setData(await api.researchNewspaperSearch(workspaceId, {
        q: q.trim(), year_from: yf, year_to: yt, newspaper_title: paper.trim() || undefined,
      }));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Search failed.");
    } finally {
      setBusy(false);
    }
  };

  const saveAsSource = async (a: NewspaperArticle) => {
    setSavingId(a.id); setError(null);
    try {
      await api.researchCreateSource(workspaceId, {
        title: a.heading,
        source_type: "newspaper_article",
        publication: a.newspaper ?? null,
        publication_date: a.date ?? null,
        publication_date_precision: a.date ? "exact" : null,
        original_url: a.url ?? null,
        copyright_status: "public_domain",   // Trove's digitised historical papers are out of copyright
      });
      setSaved((s) => new Set(s).add(a.id));
      onSaved?.("Saved to the Source Library.");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not save the source.");
    } finally {
      setSavingId(null);
    }
  };

  return (
    <div className="flex flex-col gap-3">
      <p className="text-xs text-muted-foreground">
        Search digitised historical newspapers (Trove, National Library of Australia). Save a useful
        article to your Source Library, then open it to read and transcribe the scorecard — nothing is
        imported automatically.
      </p>
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">
          Search terms
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder='e.g. Rhymney cricket'
            className="w-56" onKeyDown={(e) => { if (e.key === "Enter") void search(); }} />
        </label>
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">
          Year from
          <Input value={yearFrom} onChange={(e) => setYearFrom(e.target.value)} placeholder="1890" inputMode="numeric" className="w-20" />
        </label>
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">
          Year to
          <Input value={yearTo} onChange={(e) => setYearTo(e.target.value)} placeholder="1910" inputMode="numeric" className="w-20" />
        </label>
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">
          Newspaper (optional)
          <Input value={paper} onChange={(e) => setPaper(e.target.value)} placeholder="Ararat Advertiser" className="w-44" />
        </label>
        <Button disabled={busy || !q.trim()} onClick={() => void search()}>
          <Search className="h-4 w-4" aria-hidden /> {busy ? "Searching…" : "Search"}
        </Button>
      </div>

      {error && <p className="rounded-[var(--radius-app)] border border-danger/40 bg-danger/5 px-3 py-2 text-sm text-danger">{error}</p>}

      {data && (
        <>
          <p className="text-xs text-muted-foreground">
            {data.total.toLocaleString()} article{data.total === 1 ? "" : "s"} found · showing {data.results.length} · {data.source}
          </p>
          {data.results.length === 0 && (
            <EmptyState icon={<Newspaper className="h-8 w-8" aria-hidden />} title="No articles"
              description="Try broader terms or a wider year range." />
          )}
          <div className="flex flex-col gap-2">
            {data.results.map((a) => (
              <div key={a.id} className="flex flex-col gap-1 rounded-[var(--radius-app)] border border-border p-3">
                <div className="flex items-start gap-2">
                  <Newspaper className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium">{a.heading}</div>
                    <div className="text-xs text-muted-foreground">
                      {[a.newspaper, a.date, a.page ? `p.${a.page}` : null].filter(Boolean).join(" · ")}
                    </div>
                  </div>
                </div>
                {a.snippet && <p className="text-xs text-muted-foreground">{a.snippet}</p>}
                <div className="mt-0.5 flex flex-wrap gap-2">
                  {a.url && (
                    <a href={a.url} target="_blank" rel="noreferrer"
                      className="inline-flex items-center gap-1 rounded-[var(--radius-app)] border border-border px-2.5 py-1 text-xs hover:border-brand">
                      <ExternalLink className="h-3.5 w-3.5" aria-hidden /> Read on Trove
                    </a>
                  )}
                  <Button size="sm" variant="outline" disabled={savingId === a.id || saved.has(a.id)}
                    onClick={() => void saveAsSource(a)}>
                    {saved.has(a.id) ? "Saved ✓" : savingId === a.id ? "Saving…" : "Save as source"}
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
