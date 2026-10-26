/**
 * System Administration → User Management (Super Admin only). Create/edit/suspend accounts, issue
 * temporary single-use passwords, send time-limited invitations (and revoke them), and promote/demote
 * system Super Admins. The backend enforces all of this; this screen is the Super Admin UI.
 */
import { useCallback, useEffect, useState } from "react";
import { AppShell } from "../../components/layout/AppShell";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import { Input } from "../../components/ui/input";
import { api, ApiError, type ManagedUser, type UserInvitation } from "../../lib/api";
import { useAuth } from "../../lib/auth";

export function UserManagement() {
  const { user } = useAuth();
  const [usersList, setUsers] = useState<ManagedUser[]>([]);
  const [invites, setInvites] = useState<UserInvitation[]>([]);
  const [newName, setNewName] = useState("");
  const [newDisplay, setNewDisplay] = useState("");
  const [secret, setSecret] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [u, i] = await Promise.all([api.usersList(), api.invitationsList()]);
      setUsers(u); setInvites(i);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load users.");
    }
  }, []);
  useEffect(() => { if (user?.is_super_admin) void load(); }, [user, load]);

  const act = useCallback(async (fn: () => Promise<unknown>, onSecret?: (s: string) => void) => {
    setError(null); setSecret(null);
    try { const r = await fn() as { temp_password?: string; token?: string }; if (onSecret && (r?.temp_password || r?.token)) onSecret((r.temp_password || r.token)!); await load(); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Action failed."); }
  }, [load]);

  if (!user?.is_super_admin) {
    return <AppShell title="User Management" subtitle="System Administration">
      <p className="text-sm text-muted-foreground">User management is available to System (Super) Administrators.</p>
    </AppShell>;
  }

  const statusBadge = (s: string) => s === "active" ? <Badge variant="success">active</Badge>
    : s === "invited" ? <Badge variant="muted">invited</Badge> : <Badge variant="danger">suspended</Badge>;

  return (
    <AppShell title="User Management" subtitle="System Administration">
      <div className="mx-auto flex max-w-4xl flex-col gap-4">
        {error && <p className="rounded-[var(--radius-app)] border border-danger/40 bg-danger/5 px-3 py-2 text-sm text-danger">{error}</p>}
        {secret && (
          <div className="rounded-[var(--radius-app)] border border-brand/40 bg-brand/5 px-3 py-2 text-sm">
            <span className="font-medium">Give this to the user now — it is shown once:</span>
            <code className="ml-2 select-all rounded bg-muted px-1.5 py-0.5">{secret}</code>
          </div>
        )}

        <Card><CardContent className="flex flex-wrap items-end gap-2">
          <label className="flex flex-col gap-1 text-xs">Username
            <Input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="newuser" /></label>
          <label className="flex flex-1 flex-col gap-1 text-xs">Display name (optional)
            <Input value={newDisplay} onChange={(e) => setNewDisplay(e.target.value)} placeholder="New User" /></label>
          <Button size="sm" disabled={newName.trim().length < 3}
            onClick={() => void act(() => api.userCreate({ username: newName.trim(), display_name: newDisplay.trim() || undefined }), (s) => { setSecret(`temporary password: ${s}`); setNewName(""); setNewDisplay(""); })}>
            Create with temp password
          </Button>
          <Button size="sm" variant="outline" disabled={newName.trim().length < 3}
            onClick={() => void act(() => api.invitationCreate({ username: newName.trim(), display_name: newDisplay.trim() || undefined }), (s) => { setSecret(`invitation token: ${s}`); setNewName(""); setNewDisplay(""); })}>
            Invite instead
          </Button>
        </CardContent></Card>

        <Card><CardContent className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold">Users</h3>
          <div className="flex flex-col divide-y divide-border">
            {usersList.map((u) => (
              <div key={u.id} className="flex flex-wrap items-center gap-2 py-2 text-sm">
                <span className="font-medium">{u.username}</span>
                {u.display_name && <span className="text-muted-foreground">{u.display_name}</span>}
                {statusBadge(u.status)}
                {u.is_super_admin && <Badge variant="warning">super admin</Badge>}
                {u.must_change_password && <Badge variant="muted">temp password</Badge>}
                <span className="text-xs text-muted-foreground">last login {u.last_login_at ? new Date(u.last_login_at).toLocaleDateString() : "—"}</span>
                <div className="ml-auto flex flex-wrap gap-1">
                  <Button size="sm" variant="ghost" onClick={() => void act(() => api.userResetPassword(u.id), (s) => setSecret(`temporary password: ${s}`))}>Reset password</Button>
                  {u.status === "suspended"
                    ? <Button size="sm" variant="ghost" onClick={() => void act(() => api.userUpdate(u.id, { status: "active" }))}>Reactivate</Button>
                    : <Button size="sm" variant="ghost" onClick={() => void act(() => api.userUpdate(u.id, { status: "suspended" }))}>Suspend</Button>}
                  {u.is_super_admin
                    ? <Button size="sm" variant="ghost" onClick={() => void act(() => api.userUpdate(u.id, { is_super_admin: false }))}>Revoke admin</Button>
                    : <Button size="sm" variant="ghost" onClick={() => void act(() => api.userUpdate(u.id, { is_super_admin: true }))}>Make admin</Button>}
                </div>
              </div>
            ))}
          </div>
        </CardContent></Card>

        {invites.length > 0 && (
          <Card><CardContent className="flex flex-col gap-2">
            <h3 className="text-sm font-semibold">Invitations</h3>
            {invites.map((i) => (
              <div key={i.id} className="flex flex-wrap items-center gap-2 py-1 text-sm">
                <span className="font-medium">{i.username}</span>
                <Badge variant={i.status === "pending" ? "success" : "muted"}>{i.status}</Badge>
                {i.status === "pending" && <Button size="sm" variant="ghost" className="ml-auto" onClick={() => void act(() => api.invitationRevoke(i.id))}>Revoke</Button>}
              </div>
            ))}
          </CardContent></Card>
        )}
      </div>
    </AppShell>
  );
}
