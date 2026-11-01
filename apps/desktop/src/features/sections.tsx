import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AlertTriangle } from "lucide-react";
import { AppShell } from "../components/layout/AppShell";
import { Button } from "../components/ui/button";
import { Card, CardContent } from "../components/ui/card";
import { Modal } from "../components/ui/dialog";
import { Input } from "../components/ui/input";
import { Select } from "../components/ui/select";
import { api, ApiError, type MatchFormat, type Workspace } from "../lib/api";
import { useAuth } from "../lib/auth";
import { formatDate, getDateStyle, setDateStyle, type DateStyle } from "../lib/dates";
import { canManage } from "../lib/permissions";
import { getUserScoreFormat, setUserScoreFormat } from "../lib/score-format";
import { APP_VERSION } from "../lib/version";
import { useWorkspace } from "../lib/workspace-context";
import { ConnectionSettings } from "./settings/ConnectionSettings";
import { Appearance } from "./settings/Appearance";
import { ClubThemeEditor } from "./settings/ClubTheme";
import { UpdatesVersion } from "./settings/UpdatesVersion";
import { Placeholder } from "./Placeholder";

// Matches and People now have full feature screens (features/scorecard, features/people);
// their old placeholders were removed. The sections below remain placeholders until built.

export function Statistics() {
  return (
    <Placeholder
      title="Statistics"
      subtitle="Records, reports and the statistics engine"
      planned={[
        "Club records and player statistics",
        "Batting, bowling, fielding and partnerships",
        "Teams & captains, milestones",
        "Report Builder and Data Integrity",
      ]}
    />
  );
}

export function Settings() {
  const { current, reload } = useWorkspace();
  const { user } = useAuth();
  const navigate = useNavigate();
  const admin = canManage(user, current);
  const [wsFormat, setWsFormat] = useState<string>(current?.score_format ?? "au");
  const [userFormat, setUserFmt] = useState<string>(getUserScoreFormat() ?? "");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [dateStyle, setDS] = useState<DateStyle>(getDateStyle);

  const saveWorkspace = async (v: string) => {
    if (!current) return;
    setWsFormat(v); setErr(null);
    try { await api.updateWorkspace(current.id, { score_format: v }); await reload(); setMsg("Workspace default updated."); }
    catch (e) { setErr(e instanceof ApiError ? e.message : "Could not update the workspace default."); }
  };
  const example = (fmt: string) => (fmt === "en" ? "127/10" : "10/127");

  return (
    <AppShell title="Settings" subtitle="Workspace, display and configuration">
      <div className="mx-auto flex max-w-5xl flex-col gap-4">
        <Card><CardContent className="flex flex-col gap-4">
          <div>
            <h3 className="text-sm font-semibold">Scorecard Display</h3>
            <p className="text-xs text-muted-foreground">How innings scores are shown. Display only — runs and wickets are always stored separately and never changed by this.</p>
          </div>
          {msg && <p className="text-xs text-success">{msg}</p>}
          {err && <p className="text-xs text-danger">{err}</p>}
          <label className="flex flex-col gap-1 text-sm">
            <span className="font-medium">Workspace default {admin ? "" : "(admin only)"}</span>
            <Select value={wsFormat} disabled={!admin} onChange={(e) => void saveWorkspace(e.target.value)} className="max-w-xs">
              <option value="au">Australian — wickets/runs (e.g. 10/127)</option>
              <option value="en">English — runs/wickets (e.g. 127/10)</option>
            </Select>
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="font-medium">My preference</span>
            <Select value={userFormat} className="max-w-xs"
              onChange={(e) => { const v = e.target.value; setUserFmt(v); setUserScoreFormat(v === "" ? null : (v as "au" | "en")); setMsg("Your display preference was updated."); }}>
              <option value="">Use the workspace default ({example(wsFormat)})</option>
              <option value="au">Australian — wickets/runs (e.g. 10/127)</option>
              <option value="en">English — runs/wickets (e.g. 127/10)</option>
            </Select>
            <span className="text-xs text-muted-foreground">Applies to your view across the app; it does not change anyone else's display or any stored data.</span>
          </label>
        </CardContent></Card>
        <Card><CardContent className="flex flex-col gap-4">
          <div>
            <h3 className="text-sm font-semibold">Date Format</h3>
            <p className="text-xs text-muted-foreground">How dates are shown across the app. Display only — it never changes stored dates.</p>
          </div>
          <label className="flex flex-col gap-1 text-sm">
            <span className="font-medium">My preference</span>
            <Select value={dateStyle} className="max-w-xs"
              onChange={(e) => { const v = e.target.value as DateStyle; setDS(v); setDateStyle(v); setMsg("Your date format was updated."); }}>
              <option value="dmy">Day/Month/Year — {formatDate("2026-10-30", "dmy")}</option>
              <option value="mdy">Month/Day/Year — {formatDate("2026-10-30", "mdy")}</option>
            </Select>
            <span className="text-xs text-muted-foreground">Applies to your view on this device.</span>
          </label>
        </CardContent></Card>
        <UpdatesVersion />
        <Appearance />
        <div id="club-theme-editor"><ClubThemeEditor admin={admin} /></div>
        <MatchFormatsSettings workspaceId={current?.id ?? null} admin={admin} />
        {admin && <RecalcStatsSettings workspaceId={current?.id ?? null} />}
        {admin && (
          <Card><CardContent className="flex items-center justify-between gap-2">
            <div><h3 className="text-sm font-semibold">API &amp; Integrations</h3>
              <p className="text-xs text-muted-foreground">Connect external data providers (e.g. PlayHQ). Credentials are encrypted, workspace-isolated and never shown in plaintext.</p></div>
            <a href="#/settings/integrations" className="whitespace-nowrap rounded-[var(--radius-app)] border border-brand bg-brand/10 px-3 py-1.5 text-sm font-medium text-brand">Manage →</a>
          </CardContent></Card>
        )}
        {user?.is_super_admin && (
          <Card><CardContent className="flex items-center justify-between gap-2">
            <div><h3 className="text-sm font-semibold">System Administration</h3>
              <p className="text-xs text-muted-foreground">Manage user accounts, roles, temporary passwords and invitations.</p></div>
            <a href="#/admin/users" className="whitespace-nowrap rounded-[var(--radius-app)] border border-brand bg-brand/10 px-3 py-1.5 text-sm font-medium text-brand">User Management →</a>
          </CardContent></Card>
        )}
        {user?.is_super_admin && current && (
          <DangerZone
            workspace={current}
            onDeleted={async () => { await reload(); navigate("/platform"); }}
          />
        )}
        <Card><CardContent className="flex flex-col gap-4">
          <ConnectionSettings />
        </CardContent></Card>
        <Card><CardContent className="flex items-center justify-between gap-2">
          <div><h3 className="text-sm font-semibold">About</h3>
            <p className="text-xs text-muted-foreground">OneStats — Cricket Statistics Made Simple</p></div>
          <span className="text-xs text-muted-foreground">Version {APP_VERSION}</span>
        </CardContent></Card>
      </div>
    </AppShell>
  );
}

/**
 * Danger zone — permanently delete the current workspace (Super Admin only). Deliberately a
 * multi-step action: open the dialog, type the workspace's exact short name, then confirm. The
 * server re-validates the confirmation and the Super-Admin privilege; the deletion is audited.
 */
function DangerZone({ workspace, onDeleted }: { workspace: Workspace; onDeleted: () => Promise<void> }) {
  const [open, setOpen] = useState(false);
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const expected = (workspace.short_name ?? "").trim();
  const matches = confirm.trim().toLowerCase() === expected.toLowerCase() && expected !== "";

  const doDelete = async () => {
    if (!matches) return;
    setBusy(true); setErr(null);
    try {
      await api.deleteWorkspace(workspace.id, confirm.trim());
      setOpen(false);
      await onDeleted();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Could not delete the workspace.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="border-danger/40"><CardContent className="flex flex-col gap-3">
      <div className="flex items-start gap-2">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-danger" aria-hidden />
        <div>
          <h3 className="text-sm font-semibold text-danger">Danger zone</h3>
          <p className="text-xs text-muted-foreground">
            Permanently delete <b>{workspace.name}</b> and all of its data — matches, players,
            scorecards, competitions, media and history. This cannot be undone.
          </p>
        </div>
      </div>
      <div>
        <button
          type="button"
          onClick={() => { setConfirm(""); setErr(null); setOpen(true); }}
          className="rounded-[var(--radius-app)] border border-danger/50 px-3 py-1.5 text-sm font-medium text-danger hover:bg-danger/10"
        >
          Delete this workspace…
        </button>
      </div>

      <Modal open={open} title={`Delete ${workspace.name}?`} onClose={() => !busy && setOpen(false)}>
        <div className="flex flex-col gap-3">
          <p className="text-sm text-muted-foreground">
            This permanently removes the workspace and <b>everything in it</b>. It cannot be undone.
          </p>
          <label className="flex flex-col gap-1 text-sm">
            <span>Type the workspace short name <b>{expected}</b> to confirm:</span>
            <Input
              value={confirm}
              autoFocus
              onChange={(e) => setConfirm(e.target.value)}
              placeholder={expected}
              aria-label="Confirm workspace short name"
            />
          </label>
          {err && <p className="text-xs text-danger">{err}</p>}
          <div className="flex justify-end gap-2">
            <Button size="sm" variant="outline" disabled={busy} onClick={() => setOpen(false)}>Cancel</Button>
            <button
              type="button"
              disabled={!matches || busy}
              onClick={() => void doDelete()}
              className="rounded-[var(--radius-app)] bg-danger px-3 py-1.5 text-sm font-medium text-white disabled:opacity-40"
            >
              {busy ? "Deleting…" : "Delete permanently"}
            </button>
          </div>
        </div>
      </Modal>
    </CardContent></Card>
  );
}

function RecalcStatsSettings({ workspaceId }: { workspaceId: string | null }) {
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const run = async () => {
    if (!workspaceId) return;
    setBusy(true); setNote(null);
    try {
      const r = await api.recalcStats(workspaceId);
      setNote(`Recalculated ${r.matches} match(es); ${r.contributions} official contribution(s) stored.`);
    } catch (e) {
      setNote(e instanceof ApiError ? e.message : "Recalculation failed.");
    } finally { setBusy(false); }
  };
  return (
    <Card><CardContent className="flex flex-col gap-3">
      <div>
        <h3 className="text-sm font-semibold">Official Statistics</h3>
        <p className="text-xs text-muted-foreground">Only approved scorecards contribute to official statistics. Recalculation is idempotent and never double counts. Use this after bulk-approving historical imports.</p>
      </div>
      {note && <p className="text-xs text-muted-foreground">{note}</p>}
      <div><Button size="sm" disabled={busy} onClick={() => void run()}>{busy ? "Recalculating…" : "Recalculate official statistics"}</Button></div>
    </CardContent></Card>
  );
}

function MatchFormatsSettings({ workspaceId, admin }: { workspaceId: string | null; admin: boolean }) {
  const [formats, setFormats] = useState<MatchFormat[]>([]);
  const [custom, setCustom] = useState("");
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!workspaceId) return;
    try { setFormats(await api.listMatchFormats(workspaceId)); } catch (e) { setErr(e instanceof ApiError ? e.message : "Could not load formats."); }
  }, [workspaceId]);
  useEffect(() => { void load(); }, [load]);

  const patch = async (id: string, body: { enabled?: boolean; is_default?: boolean }) => {
    if (!workspaceId) return;
    setErr(null);
    try { await api.updateMatchFormat(workspaceId, id, body); await load(); }
    catch (e) { setErr(e instanceof ApiError ? e.message : "Could not update the format."); }
  };
  const addCustom = async () => {
    if (!workspaceId || !custom.trim()) return;
    setErr(null);
    try { await api.createMatchFormat(workspaceId, custom.trim()); setCustom(""); await load(); }
    catch (e) { setErr(e instanceof ApiError ? e.message : "Could not add the format."); }
  };

  return (
    <Card><CardContent className="flex flex-col gap-3">
      <div>
        <h3 className="text-sm font-semibold">Match Formats</h3>
        <p className="text-xs text-muted-foreground">Enable the formats your workspace uses and nominate a default. Playing format only — separate from statistical classification. Disabling a format never changes matches already using it.</p>
      </div>
      {err && <p className="text-xs text-danger">{err}</p>}
      <div className="overflow-hidden rounded-[var(--radius-app)] border border-border">
        <table className="w-full text-sm">
          <thead className="bg-muted text-left text-xs text-muted-foreground">
            <tr><th className="px-2 py-1.5">Format</th><th className="w-20 px-2 py-1.5 text-center">Enabled</th><th className="w-24 px-2 py-1.5 text-center">Default</th></tr>
          </thead>
          <tbody>
            {formats.map((f) => (
              <tr key={f.id} className="border-t border-border">
                <td className="px-2 py-1.5">{f.label}{f.is_custom && <span className="ml-1 text-xs text-muted-foreground">(custom)</span>}</td>
                <td className="px-2 py-1.5 text-center">
                  <input type="checkbox" checked={f.enabled} disabled={!admin} onChange={(e) => void patch(f.id, { enabled: e.target.checked })} aria-label={`Enable ${f.label}`} />
                </td>
                <td className="px-2 py-1.5 text-center">
                  <input type="radio" name="default_format" checked={f.is_default} disabled={!admin || !f.enabled}
                    onChange={() => void patch(f.id, { is_default: true })} aria-label={`Default ${f.label}`} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {admin && (
        <div className="flex items-end gap-2">
          <label className="flex flex-1 flex-col gap-1 text-sm">Add a custom format
            <Input value={custom} onChange={(e) => setCustom(e.target.value)} placeholder="e.g. Super Eights" />
          </label>
          <Button size="sm" disabled={!custom.trim()} onClick={() => void addCustom()}>Add</Button>
        </div>
      )}
    </CardContent></Card>
  );
}
