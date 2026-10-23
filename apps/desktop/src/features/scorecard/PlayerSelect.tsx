/**
 * Inline, searchable player selector used directly inside batting/bowling rows (Stage 7, §4).
 *
 * No need to preselect a team. Supports: searching existing players, creating a new player during
 * entry, and a non-blocking duplicate-identity warning (never auto-merges). Unidentified players
 * are fine — leaving the field blank means "unknown", not a fabricated player.
 */

import { AlertTriangle, Check, Plus, Search, UserPlus, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Badge } from "../../components/ui/badge";
import { api, ApiError, type Person, type PersonDuplicateCandidate } from "../../lib/api";

export interface PlayerSelectProps {
  workspaceId: string;
  value: string | null;
  nameOf: (id: string | null) => string | null;
  onChange: (personId: string | null) => void;
  onPersonLoaded: (p: Person) => void;
  disabled?: boolean;
  placeholder?: string;
  "aria-label"?: string;
}

export function PlayerSelect({
  workspaceId,
  value,
  nameOf,
  onChange,
  onPersonLoaded,
  disabled,
  placeholder = "Search player…",
  ...rest
}: PlayerSelectProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Person[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<PersonDuplicateCandidate[]>([]);
  const boxRef = useRef<HTMLDivElement>(null);

  const label = nameOf(value);

  // search (debounced)
  useEffect(() => {
    if (!open) return;
    const t = setTimeout(async () => {
      setBusy(true);
      setErr(null);
      try {
        setResults(await api.listPeople(workspaceId, { search: query || undefined }));
      } catch (e) {
        setErr(e instanceof ApiError ? e.message : "Search failed");
      } finally {
        setBusy(false);
      }
    }, 200);
    return () => clearTimeout(t);
  }, [open, query, workspaceId]);

  // close on outside click
  useEffect(() => {
    if (!open) return;
    const h = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, [open]);

  const checkDuplicates = useCallback(
    async (personId: string) => {
      try {
        setCandidates(await api.identityCandidates(workspaceId, personId));
      } catch {
        setCandidates([]);
      }
    },
    [workspaceId],
  );

  const pick = (p: Person) => {
    onPersonLoaded(p);
    onChange(p.id);
    setOpen(false);
    setQuery("");
    void checkDuplicates(p.id);
  };

  const createNew = async () => {
    const name = query.trim();
    if (!name) return;
    setBusy(true);
    setErr(null);
    try {
      const created = (await api.createPerson(workspaceId, { display_name: name })) as { id: string };
      const person: Person = {
        id: created.id, display_name: name, status: "active", is_junior: false,
        privacy_protected: false, dob: null, dob_precision: "unknown", notes: null, merged_into_id: null,
      };
      pick(person);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Could not create player");
      setBusy(false);
    }
  };

  return (
    <div ref={boxRef} className="relative">
      <div className="flex items-center gap-1">
        <button
          type="button"
          disabled={disabled}
          onClick={() => setOpen((v) => !v)}
          aria-label={rest["aria-label"] ?? "Select player"}
          className="flex h-8 min-w-0 flex-1 items-center gap-1 rounded-[var(--radius-app)] border border-border bg-card px-2 text-left text-sm hover:bg-muted disabled:opacity-50"
        >
          <Search className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden />
          <span className={`truncate ${label ? "" : "italic text-muted-foreground"}`}>
            {label ?? "Unknown"}
          </span>
        </button>
        {value && !disabled && (
          <button
            type="button"
            aria-label="Clear player"
            onClick={() => {
              onChange(null);
              setCandidates([]);
            }}
            className="rounded-[var(--radius-app)] p-1 text-muted-foreground hover:bg-muted"
          >
            <X className="h-3.5 w-3.5" aria-hidden />
          </button>
        )}
      </div>

      {candidates.length > 0 && (
        <div className="mt-1 flex items-center gap-1 text-[11px] text-warning" title={candidates.map((c) => c.display_name).join(", ")}>
          <AlertTriangle className="h-3 w-3" aria-hidden />
          Possible duplicate identity — review in People (not merged automatically).
        </div>
      )}

      {open && (
        <div className="absolute left-0 top-full z-20 mt-1 w-72 rounded-[var(--radius-app)] border border-border bg-card p-2 shadow-lg">
          <input
            autoFocus
            value={query}
            placeholder={placeholder}
            onChange={(e) => setQuery(e.target.value)}
            className="mb-2 h-8 w-full rounded-[var(--radius-app)] border border-border bg-background px-2 text-sm focus-visible:outline-2 focus-visible:outline-[var(--ring)]"
          />
          {err && <p className="px-1 pb-1 text-xs text-danger">{err}</p>}
          <div className="max-h-56 overflow-auto">
            {busy && <p className="px-1 py-2 text-xs text-muted-foreground">Searching…</p>}
            {!busy && results.length === 0 && (
              <p className="px-1 py-2 text-xs text-muted-foreground">No matches.</p>
            )}
            <ul>
              {results.map((p) => (
                <li key={p.id}>
                  <button
                    type="button"
                    onClick={() => pick(p)}
                    className="flex w-full items-center gap-2 rounded-[var(--radius-app)] px-2 py-1.5 text-left text-sm hover:bg-muted"
                  >
                    {value === p.id ? <Check className="h-3.5 w-3.5 text-brand" aria-hidden /> : <span className="w-3.5" />}
                    <span className="truncate">{p.display_name}</span>
                    {p.is_junior && <Badge variant="warning">junior</Badge>}
                  </button>
                </li>
              ))}
            </ul>
          </div>
          {query.trim() && (
            <button
              type="button"
              onClick={() => void createNew()}
              disabled={busy}
              className="mt-1 flex w-full items-center gap-2 rounded-[var(--radius-app)] border border-dashed border-border px-2 py-1.5 text-left text-sm text-brand hover:bg-muted"
            >
              <UserPlus className="h-3.5 w-3.5" aria-hidden />
              Create new player “{query.trim()}”
              <Plus className="ml-auto h-3.5 w-3.5" aria-hidden />
            </button>
          )}
        </div>
      )}
    </div>
  );
}
