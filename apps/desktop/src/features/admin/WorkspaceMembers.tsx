/**
 * Workspace Members — manage who has access to THIS workspace and with which roles. Available to
 * Organisation Admins and Super Admins (the `user.admin` permission); the backend enforces it on
 * every action. Creating platform accounts and system Super Admins stays in System Administration
 * (Super Admin only), so an Organisation Admin adds an EXISTING account to their workspace by
 * username and assigns one of the workspace roles.
 */
import { useCallback, useEffect, useState } from "react";
import { AppShell } from "../../components/layout/AppShell";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import { Input } from "../../components/ui/input";
import { ApiError, api, type WorkspaceMember } from "../../lib/api";
import { can, roleLabel } from "../../lib/permissions";
import { NoWorkspace, useManage } from "../manage/_shared";
import { useToast } from "../../lib/toast";

/** Workspace roles an admin can assign here. `super_admin` is a platform flag, never a workspace role. */
const ASSIGNABLE_ROLES = ["workspace_admin", "researcher", "scorecard_entry", "reviewer", "viewer"];

function RoleSelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <select className="h-9 rounded-[var(--radius-app)] border border-border bg-background px-2 text-sm"
      value={value} onChange={(e) => onChange(e.target.value)}>
      {ASSIGNABLE_ROLES.map((r) => <option key={r} value={r}>{roleLabel(r)}</option>)}
    </select>
  );
}

export function WorkspaceMembers() {
  const { user, workspace, workspaceId } = useManage();
  const canAdmin = can(user, workspace, "user.admin");
  const [members, setMembers] = useState<WorkspaceMember[]>([]);
  const [error, setError] = useState<string | null>(null);
  const toast = useToast();
  const [newUser, setNewUser] = useState("");
  const [newRole, setNewRole] = useState(ASSIGNABLE_ROLES[0]);
  const [addRole, setAddRole] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!workspaceId) return;
    try { setMembers(await api.workspaceMembers(workspaceId)); setError(null); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Could not load members."); }
  }, [workspaceId]);
  useEffect(() => { if (workspaceId && canAdmin) void load(); }, [workspaceId, canAdmin, load]);

  if (!workspaceId) {
    return <AppShell title="Members" subtitle="Workspace roles and access"><NoWorkspace /></AppShell>;
  }
  if (!canAdmin) {
    return <AppShell title="Members" subtitle="Workspace roles and access">
      <p className="text-sm text-muted-foreground">Managing members requires the Organisation Admin role (or Super Admin).</p>
    </AppShell>;
  }

  const act = async (fn: () => Promise<unknown>, ok: string) => {
    setBusy(true); setError(null);
    try { await fn(); toast.success(ok); await load(); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Action failed."); }
    finally { setBusy(false); }
  };

  const ws = workspaceId;
  return (
    <AppShell title="Members" subtitle="Workspace roles and access">
      <div className="mx-auto flex max-w-3xl flex-col gap-4">
        {error && <p className="rounded-[var(--radius-app)] border border-danger/40 bg-danger/5 px-3 py-2 text-sm text-danger">{error}</p>}

        <Card><CardContent className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold">Add a member</h3>
          <p className="text-xs text-muted-foreground">
            Add an existing OneStats account to this workspace by username and give them a role. New accounts
            are created in System Administration (Super Admin).
          </p>
          <div className="flex flex-wrap items-end gap-2">
            <label className="flex flex-1 flex-col gap-1 text-xs">Username
              <Input value={newUser} onChange={(e) => setNewUser(e.target.value)} placeholder="username" /></label>
            <label className="flex flex-col gap-1 text-xs">Role
              <RoleSelect value={newRole} onChange={setNewRole} /></label>
            <Button size="sm" disabled={busy || newUser.trim().length < 1}
              onClick={() => void act(() => api.workspaceAddMember(ws, { username: newUser.trim(), role: newRole }),
                `Added ${newUser.trim()} as ${roleLabel(newRole)}.`).then(() => setNewUser(""))}>
              Add member
            </Button>
          </div>
        </CardContent></Card>

        <Card><CardContent className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold">Members</h3>
          {members.length === 0
            ? <p className="text-sm text-muted-foreground">No members yet. Add one above.</p>
            : <div className="flex flex-col divide-y divide-border">
                {members.map((m) => {
                  const pending = addRole[m.user_id] ?? ASSIGNABLE_ROLES.find((r) => !m.roles.includes(r)) ?? ASSIGNABLE_ROLES[0];
                  return (
                    <div key={m.user_id} className="flex flex-wrap items-center gap-2 py-2 text-sm">
                      <span className="font-medium">{m.username}</span>
                      {m.display_name && <span className="text-muted-foreground">{m.display_name}</span>}
                      <span className="flex flex-wrap gap-1">
                        {m.roles.map((r) => (
                          <span key={r} className="inline-flex items-center gap-1 rounded-full border border-border bg-muted px-2 py-0.5 text-xs">
                            {roleLabel(r)}
                            <button type="button" disabled={busy} className="text-danger hover:underline disabled:opacity-50"
                              aria-label={`Revoke ${roleLabel(r)} from ${m.username}`}
                              onClick={() => void act(() => api.workspaceRevokeMember(ws, m.user_id, r), `Revoked ${roleLabel(r)} from ${m.username}.`)}>×</button>
                          </span>
                        ))}
                      </span>
                      <div className="ml-auto flex items-center gap-1">
                        <RoleSelect value={pending} onChange={(v) => setAddRole((s) => ({ ...s, [m.user_id]: v }))} />
                        <Button size="sm" variant="outline" disabled={busy || m.roles.includes(pending)}
                          onClick={() => void act(() => api.workspaceAddMember(ws, { user_id: m.user_id, role: pending }), `Added ${roleLabel(pending)} to ${m.username}.`)}>
                          Add role
                        </Button>
                      </div>
                    </div>
                  );
                })}
              </div>}
        </CardContent></Card>
      </div>
    </AppShell>
  );
}
