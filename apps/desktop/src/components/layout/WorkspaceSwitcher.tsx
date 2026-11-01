import { Building2, Check, ChevronsUpDown, Globe, Search } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { cn } from "../../lib/utils";
import { useWorkspace } from "../../lib/workspace-context";

/**
 * Workspace selector. For the Super Administrator it is a permanent, searchable selector that
 * includes an "All Workspaces" entry (the platform overview) plus every workspace with its logo,
 * for fast switching. For ordinary users it lists the workspaces they belong to. The current
 * workspace is persisted by the workspace context; selecting one switches instantly.
 */
export function WorkspaceSwitcher() {
  const { workspaces, current, setCurrent } = useWorkspace();
  const { user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [logos, setLogos] = useState<Record<string, string>>({});
  const rootRef = useRef<HTMLDivElement>(null);

  const isSuper = !!user?.is_super_admin;
  const onPlatform = location.pathname.startsWith("/platform");

  // Close on outside click / Escape.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", onDown); document.removeEventListener("keydown", onKey); };
  }, [open]);

  // Lazy-load workspace logos once the list is opened; revoke object URLs on cleanup.
  useEffect(() => {
    if (!open) return;
    let revoked = false;
    const created: string[] = [];
    (async () => {
      for (const w of workspaces) {
        if (logos[w.id]) continue;
        try {
          const url = await api.brandingLogoObjectUrl(w.id);
          if (url && !revoked) { created.push(url); setLogos((m) => ({ ...m, [w.id]: url })); }
        } catch { /* ignore — fall back to the building icon */ }
      }
    })();
    return () => { revoked = true; created.forEach((u) => URL.revokeObjectURL(u)); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, workspaces]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return workspaces;
    return workspaces.filter((w) => `${w.name} ${w.short_name ?? ""}`.toLowerCase().includes(q));
  }, [workspaces, query]);

  if (workspaces.length === 0) return null;

  const label = onPlatform && isSuper ? "All Workspaces" : current?.name ?? "Select workspace";

  const chooseWorkspace = (id: string) => {
    setCurrent(id);
    setOpen(false);
    setQuery("");
    if (onPlatform) navigate("/dashboard");
  };

  const chooseAll = () => {
    setOpen(false);
    setQuery("");
    navigate("/platform");
  };

  return (
    <div ref={rootRef} className="relative px-3 pb-2">
      <label className="mb-1 block text-[11px] uppercase tracking-wide text-sidebar-muted">Workspace</label>
      <button
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 rounded-[var(--radius-app)] border border-[color:var(--sidebar-active)] bg-sidebar-active px-2 py-1.5 text-left text-sm text-sidebar-foreground"
      >
        {onPlatform && isSuper
          ? <Globe className="h-4 w-4 shrink-0" aria-hidden />
          : current && logos[current.id]
            ? <img src={logos[current.id]} alt="" className="h-4 w-4 shrink-0 rounded object-contain" />
            : <Building2 className="h-4 w-4 shrink-0" aria-hidden />}
        <span className="min-w-0 flex-1 truncate">{label}</span>
        <ChevronsUpDown className="h-3.5 w-3.5 shrink-0 opacity-70" aria-hidden />
      </button>

      {open && (
        <div
          role="listbox"
          className="absolute left-3 right-3 z-30 mt-1 max-h-[60vh] overflow-auto rounded-[var(--radius-app)] border border-border bg-card text-foreground shadow-lg"
        >
          <div className="sticky top-0 flex items-center gap-2 border-b border-border bg-card px-2 py-1.5">
            <Search className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />
            <input
              autoFocus
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search workspaces…"
              aria-label="Search workspaces"
              className="w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
            />
          </div>

          {isSuper && (
            <button
              type="button"
              role="option"
              aria-selected={onPlatform}
              onClick={chooseAll}
              className={cn(
                "flex w-full items-center gap-2 border-b border-border px-2 py-2 text-left text-sm hover:bg-muted/50",
                onPlatform && "bg-muted/40",
              )}
            >
              <Globe className="h-4 w-4 shrink-0" aria-hidden />
              <span className="flex-1 truncate font-medium">All Workspaces</span>
              {onPlatform && <Check className="h-4 w-4" aria-hidden />}
            </button>
          )}

          {filtered.length === 0 ? (
            <p className="px-2 py-3 text-center text-xs text-muted-foreground">No workspaces match “{query}”.</p>
          ) : (
            filtered.map((w) => {
              const selected = !onPlatform && current?.id === w.id;
              return (
                <button
                  key={w.id}
                  type="button"
                  role="option"
                  aria-selected={selected}
                  onClick={() => chooseWorkspace(w.id)}
                  className={cn("flex w-full items-center gap-2 px-2 py-2 text-left text-sm hover:bg-muted/50", selected && "bg-muted/40")}
                >
                  {logos[w.id]
                    ? <img src={logos[w.id]} alt="" className="h-5 w-5 shrink-0 rounded object-contain" />
                    : <Building2 className="h-5 w-5 shrink-0 text-muted-foreground" aria-hidden />}
                  <span className="min-w-0 flex-1 truncate">{w.name}</span>
                  {selected && <Check className="h-4 w-4 shrink-0" aria-hidden />}
                </button>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}
