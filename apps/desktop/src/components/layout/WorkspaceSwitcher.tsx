import { useWorkspace } from "../../lib/workspace-context";

export function WorkspaceSwitcher() {
  const { workspaces, current, setCurrent } = useWorkspace();
  if (workspaces.length === 0) return null;
  return (
    <div className="px-3 pb-2">
      <label className="mb-1 block text-[11px] uppercase tracking-wide text-sidebar-muted">
        Workspace
      </label>
      <select
        aria-label="Select workspace"
        value={current?.id ?? ""}
        onChange={(e) => setCurrent(e.target.value)}
        className="w-full rounded-[var(--radius-app)] border border-[color:var(--sidebar-active)] bg-sidebar-active px-2 py-1.5 text-sm text-sidebar-foreground"
      >
        {workspaces.map((w) => (
          <option key={w.id} value={w.id} className="bg-card text-foreground">
            {w.name}
          </option>
        ))}
      </select>
    </div>
  );
}
