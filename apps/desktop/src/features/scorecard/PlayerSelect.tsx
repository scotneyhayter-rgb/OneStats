/**
 * Inline, searchable player selector used directly inside batting/bowling/official rows
 * (Stage 7, §4). No need to preselect a team. Supports: searching existing players, creating a new
 * player during entry, and a non-blocking duplicate-identity warning (never auto-merges).
 *
 * The results panel is rendered in a PORTAL (document.body) with fixed positioning so it is never
 * clipped by a parent's overflow and always sits above neighbouring panels/sections. It flips
 * upwards when there is little room below, scrolls internally, repositions on scroll/resize, and
 * supports full keyboard navigation (Arrow keys, Enter to select/create, Escape to dismiss) with a
 * visible highlight. It never creates duplicate records or changes player-matching behaviour.
 */

import { AlertTriangle, Check, Plus, Search, UserPlus, X } from "lucide-react";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Badge } from "../../components/ui/badge";
import { api, ApiError, type Person, type PersonDuplicateCandidate } from "../../lib/api";
import { PersonWizard } from "./PersonWizard";

export interface PlayerSelectProps {
  workspaceId: string;
  value: string | null;
  nameOf: (id: string | null) => string | null;
  onChange: (personId: string | null) => void;
  onPersonLoaded: (p: Person) => void;
  disabled?: boolean;
  placeholder?: string;
  /** Title/verb for the Create Person wizard launched from this field (e.g. "Player", "Umpire"). */
  roleLabel?: string;
  /** Role pre-ticked in the wizard for this field (default "player"). */
  defaultRole?: string;
  /** Club/organisation to scope the search to by default (Phase 7.4 player selection). Players from
   *  other clubs stay discoverable via the "Show all" toggle — never a hard restriction. */
  organisationId?: string | null;
  /** Short club name shown on the scope toggle (e.g. "Northside CC"). */
  scopeLabel?: string | null;
  "aria-label"?: string;
}

interface PanelPos {
  left: number;
  width: number;
  top?: number;
  bottom?: number;
  maxHeight: number;
}

export function PlayerSelect({
  workspaceId,
  value,
  nameOf,
  onChange,
  onPersonLoaded,
  disabled,
  placeholder = "Search player…",
  roleLabel = "Player",
  defaultRole = "player",
  organisationId = null,
  scopeLabel = null,
  ...rest
}: PlayerSelectProps) {
  const [open, setOpen] = useState(false);
  const [showAll, setShowAll] = useState(false);  // scope to the club by default; show all for fill-ins
  const [wizard, setWizard] = useState<string | null>(null); // the name to create, when the wizard is open
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Person[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<PersonDuplicateCandidate[]>([]);
  const [active, setActive] = useState(0); // highlighted option; results.length == the "create" row
  const [pos, setPos] = useState<PanelPos | null>(null);

  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const label = nameOf(value);
  const canCreate = query.trim().length > 0;
  const optionCount = results.length + (canCreate ? 1 : 0);

  // ---- positioning (portal, fixed) -----------------------------------------------------------
  const reposition = useCallback(() => {
    const el = triggerRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const width = Math.max(r.width, 288);
    const left = Math.max(8, Math.min(r.left, window.innerWidth - width - 8));
    const spaceBelow = window.innerHeight - r.bottom;
    const spaceAbove = r.top;
    const openUp = spaceBelow < 280 && spaceAbove > spaceBelow;
    if (openUp) {
      setPos({ left, width, bottom: window.innerHeight - r.top + 4, maxHeight: Math.max(160, spaceAbove - 16) });
    } else {
      setPos({ left, width, top: r.bottom + 4, maxHeight: Math.max(160, spaceBelow - 16) });
    }
  }, []);

  useLayoutEffect(() => {
    if (!open) return;
    reposition();
    const onScroll = () => reposition();
    window.addEventListener("scroll", onScroll, true); // capture: catch scrolling ancestors too
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("resize", onScroll);
    };
  }, [open, reposition]);

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 0);
  }, [open]);

  // ---- search (debounced) --------------------------------------------------------------------
  useEffect(() => {
    if (!open) return;
    const t = setTimeout(async () => {
      setBusy(true);
      setErr(null);
      try {
        // scope to the field's club by default; "Show all" (or no club set) searches everyone so
        // fill-ins, multi-club and historical players stay discoverable
        const opts: { search?: string; organisation_id?: string } = { search: query || undefined };
        if (organisationId && !showAll) opts.organisation_id = organisationId;
        setResults(await api.listPeople(workspaceId, opts));
        setActive(0);
      } catch (e) {
        setErr(e instanceof ApiError ? e.message : "Search failed");
      } finally {
        setBusy(false);
      }
    }, 200);
    return () => clearTimeout(t);
  }, [open, query, workspaceId, organisationId, showAll]);

  // ---- outside click / dismiss ---------------------------------------------------------------
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node;
      if (triggerRef.current?.contains(t) || panelRef.current?.contains(t)) return;
      setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
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

  // "Create new …" launches the shared Create Person wizard (prefilled with the search text),
  // rather than creating a bare record inline — so duplicate-matching and roles are consistent.
  const launchWizard = () => {
    const name = query.trim();
    if (!name) return;
    setOpen(false);
    setWizard(name);
  };

  const chooseActive = () => {
    if (active < results.length) pick(results[active]);
    else if (canCreate) launchWizard();
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setActive((i) => Math.min(optionCount - 1, i + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((i) => Math.max(0, i - 1)); }
    else if (e.key === "Enter") { e.preventDefault(); chooseActive(); }
    else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); setOpen(false); triggerRef.current?.focus(); }
  };

  return (
    <div className="relative">
      <div className="flex items-center gap-1">
        <button
          ref={triggerRef}
          type="button"
          disabled={disabled}
          onClick={() => setOpen((v) => !v)}
          aria-haspopup="listbox"
          aria-expanded={open}
          aria-label={rest["aria-label"] ?? "Select player"}
          className="flex h-8 min-w-0 flex-1 items-center gap-1 rounded-[var(--radius-app)] border border-border bg-card px-2 text-left text-sm hover:bg-muted disabled:opacity-50"
        >
          <Search className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden />
          <span className={`truncate ${label ? "" : "italic text-muted-foreground"}`}>{label ?? "Unknown"}</span>
        </button>
        {value && !disabled && (
          <button
            type="button"
            aria-label="Clear player"
            onClick={() => { onChange(null); setCandidates([]); }}
            className="rounded-[var(--radius-app)] p-1 text-muted-foreground hover:bg-muted"
          >
            <X className="h-3.5 w-3.5" aria-hidden />
          </button>
        )}
      </div>

      {candidates.length > 0 && (
        <div className="mt-1 flex items-center gap-1 text-[11px] text-warning" title={candidates.map((c) => c.display_name).join(", ")}>
          <AlertTriangle className="h-3 w-3 shrink-0" aria-hidden />
          Possible duplicate identity — review in People (not merged automatically).
        </div>
      )}

      {open && pos && createPortal(
        <div
          ref={panelRef}
          role="listbox"
          className="fixed z-[1000] flex flex-col rounded-[var(--radius-app)] border border-border bg-card p-2 shadow-lg"
          style={{ left: pos.left, width: pos.width, top: pos.top, bottom: pos.bottom, maxHeight: pos.maxHeight }}
        >
          <input
            ref={inputRef}
            value={query}
            placeholder={placeholder}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKeyDown}
            className="mb-2 h-8 w-full shrink-0 rounded-[var(--radius-app)] border border-border bg-background px-2 text-sm focus-visible:outline-2 focus-visible:outline-[var(--ring)]"
          />
          {organisationId && (
            <label className="mb-2 flex shrink-0 items-center gap-1.5 px-1 text-[11px] text-muted-foreground">
              <input type="checkbox" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} />
              Show all players{showAll ? "" : scopeLabel ? ` (showing ${scopeLabel} only)` : " (showing this club only)"}
            </label>
          )}
          {err && <p className="px-1 pb-1 text-xs text-danger">{err}</p>}
          <div className="min-h-0 flex-1 overflow-auto">
            {busy && <p className="px-1 py-2 text-xs text-muted-foreground">Searching…</p>}
            {!busy && results.length === 0 && <p className="px-1 py-2 text-xs text-muted-foreground">No matches.</p>}
            <ul>
              {results.map((p, i) => (
                <li key={p.id}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={value === p.id}
                    onMouseEnter={() => setActive(i)}
                    onClick={() => pick(p)}
                    className={`flex w-full items-center gap-2 rounded-[var(--radius-app)] px-2 py-1.5 text-left text-sm ${active === i ? "bg-muted" : "hover:bg-muted"}`}
                  >
                    {value === p.id ? <Check className="h-3.5 w-3.5 text-brand" aria-hidden /> : <span className="w-3.5" />}
                    <span className="truncate">{p.display_name}</span>
                    {p.is_junior && <Badge variant="warning">junior</Badge>}
                  </button>
                </li>
              ))}
            </ul>
          </div>
          {canCreate && (
            <button
              type="button"
              role="option"
              aria-selected={active === results.length}
              onMouseEnter={() => setActive(results.length)}
              onClick={launchWizard}
              disabled={busy}
              className={`mt-1 flex w-full shrink-0 items-center gap-2 rounded-[var(--radius-app)] border border-dashed border-border px-2 py-1.5 text-left text-sm text-brand ${active === results.length ? "bg-muted" : "hover:bg-muted"}`}
            >
              <UserPlus className="h-3.5 w-3.5" aria-hidden />
              Create New Person “{query.trim()}”
              <Plus className="ml-auto h-3.5 w-3.5" aria-hidden />
            </button>
          )}
        </div>,
        document.body,
      )}

      {wizard !== null && (
        <PersonWizard
          workspaceId={workspaceId}
          initialName={wizard}
          roleLabel={roleLabel}
          defaultRole={defaultRole}
          onCancel={() => setWizard(null)}
          onCreated={(p) => { setWizard(null); setQuery(""); pick(p); }}
        />
      )}
    </div>
  );
}
