/**
 * Workspace Settings → API & Integrations (deliverable: Workspace API & Integrations Management).
 *
 * Clubs/associations manage their own external-provider API credentials here — no config-file or
 * source edits. For each supported provider: add/configure credentials, test the real connection,
 * enable/disable, rotate the secret, and revoke. Stored secrets are encrypted at rest by the backend
 * and are NEVER shown here (the UI only ever receives masked status), and every action is audited.
 * Admin-only (backend-enforced by the "Configure import connectors" permission).
 */
import { KeyRound, Lock, PlugZap, RefreshCw, ShieldCheck, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { AppShell } from "../../components/layout/AppShell";
import { EmptyState } from "../../components/states/States";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import { ConfirmDialog } from "../../components/ui/dialog";
import { Input } from "../../components/ui/input";
import {
  api,
  ApiError,
  type IntegrationAuditEntry,
  type IntegrationCredential,
  type IntegrationProvider,
} from "../../lib/api";
import { NoWorkspace, useManage } from "../manage/_shared";
import { useToast } from "../../lib/toast";

export function Integrations() {
  const { workspaceId, canManage } = useManage();
  const [providers, setProviders] = useState<IntegrationProvider[]>([]);
  const [creds, setCreds] = useState<IntegrationCredential[]>([]);
  const [auditLog, setAuditLog] = useState<IntegrationAuditEntry[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const toast = useToast();

  const load = useCallback(async () => {
    if (!workspaceId) return;
    try {
      const [p, c, a] = await Promise.all([
        api.integrationProviders(workspaceId),
        api.integrationCredentials(workspaceId),
        api.integrationAudit(workspaceId),
      ]);
      setProviders(p); setCreds(c); setAuditLog(a);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load integrations.");
    }
  }, [workspaceId]);
  useEffect(() => { void load(); }, [load]);

  if (!workspaceId) return <NoWorkspace />;
  if (!canManage) {
    return (
      <AppShell title="API & Integrations" subtitle="External data providers for this workspace">
        <EmptyState icon={<Lock className="h-8 w-8" aria-hidden />} title="Administrator access required"
          description="Managing API credentials and integrations needs the workspace administrator permission." />
      </AppShell>
    );
  }

  const act = async (fn: () => Promise<unknown>, msg: string) => {
    setBusy(true); setError(null);
    try { await fn(); toast.success(msg); await load(); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Action failed."); }
    finally { setBusy(false); }
  };

  const credFor = (providerId: string) => creds.find((c) => c.provider === providerId);

  return (
    <AppShell title="API & Integrations" subtitle="Connect external data providers for this workspace">
      <div className="mx-auto flex max-w-3xl flex-col gap-4">
        {error && <p className="rounded-[var(--radius-app)] border border-danger/40 bg-danger/5 px-3 py-2 text-sm text-danger">{error}</p>}

        <p className="flex items-start gap-2 rounded-[var(--radius-app)] border border-border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
          <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          Secrets are encrypted and stored securely on the server. They are never shown here, included in logs or
          exports, or shared with other workspaces. A connection is only confirmed working after a successful Test.
        </p>

        {providers.map((p) => (
          <ProviderCard key={p.id} provider={p} credential={credFor(p.id)} busy={busy}
            workspaceId={workspaceId} act={act} />
        ))}

        <Card><CardContent className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold">Integration activity</h3>
          {auditLog.length === 0 && <p className="text-xs text-muted-foreground">No credential activity recorded yet.</p>}
          {auditLog.map((a, i) => (
            <div key={i} className="flex flex-wrap items-center gap-2 border-t border-border pt-1.5 text-xs first:border-0 first:pt-0">
              <Badge variant="outline">{a.action.replace("integration.credential.", "")}</Badge>
              <span className="text-muted-foreground">{a.provider}</span>
              <span className="ml-auto text-muted-foreground">{a.at ? new Date(a.at).toLocaleString() : ""}</span>
            </div>
          ))}
        </CardContent></Card>
      </div>
    </AppShell>
  );
}

function ProviderCard({ provider, credential, busy, workspaceId, act }: {
  provider: IntegrationProvider;
  credential: IntegrationCredential | undefined;
  busy: boolean;
  workspaceId: string;
  act: (fn: () => Promise<unknown>, msg: string) => Promise<void>;
}) {
  const [adding, setAdding] = useState(false);
  const [rotating, setRotating] = useState(false);
  const [revoking, setRevoking] = useState(false);
  const configured = credential && credential.status === "active";

  const statusBadge = () => {
    if (!credential) return <Badge variant="outline">Not configured</Badge>;
    if (credential.status === "revoked") return <Badge variant="muted">Revoked</Badge>;
    if (!credential.enabled) return <Badge variant="warning">Disabled</Badge>;
    if (credential.last_test_ok === true) return <Badge variant="success">Connected</Badge>;
    if (credential.last_test_ok === false) return <Badge variant="warning">Test failed</Badge>;
    return <Badge variant="brand">Configured — untested</Badge>;
  };

  return (
    <Card><CardContent className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <PlugZap className="h-4 w-4 text-brand" aria-hidden />
        <h3 className="text-sm font-semibold">{provider.name}</h3>
        {statusBadge()}
      </div>
      {provider.notes && <p className="text-xs text-muted-foreground">{provider.notes}</p>}

      {configured && credential && (
        <div className="flex flex-col gap-2 rounded-[var(--radius-app)] border border-border p-3 text-sm">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Lock className="h-3.5 w-3.5" aria-hidden /> Secret stored securely (hidden)
            {credential.label && <span>· {credential.label}</span>}
          </div>
          {Object.keys(credential.config).length > 0 && (
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
              {Object.entries(credential.config).map(([k, v]) => (
                <span key={k} className="text-muted-foreground">{k}: <span className="text-foreground">{String(v)}</span></span>
              ))}
            </div>
          )}
          {credential.last_test_message && (
            <p className={`text-xs ${credential.last_test_ok ? "text-success" : "text-warning"}`}>
              {credential.last_test_message}
              {credential.last_test_at && <span className="text-muted-foreground"> · {new Date(credential.last_test_at).toLocaleString()}</span>}
            </p>
          )}
          <div className="flex flex-wrap gap-1">
            {provider.testable && (
              <Button size="sm" disabled={busy || !credential.enabled}
                onClick={() => void act(() => api.integrationTest(workspaceId, credential.id), "Connection tested.")}>
                <RefreshCw className="h-4 w-4" aria-hidden /> Test connection
              </Button>
            )}
            <Button size="sm" variant="outline" disabled={busy}
              onClick={() => void act(() => api.integrationSetEnabled(workspaceId, credential.id, !credential.enabled),
                credential.enabled ? "Integration disabled." : "Integration enabled.")}>
              {credential.enabled ? "Disable" : "Enable"}
            </Button>
            <Button size="sm" variant="outline" disabled={busy} onClick={() => setRotating((r) => !r)}>
              <KeyRound className="h-4 w-4" aria-hidden /> Rotate secret
            </Button>
            <Button size="sm" variant="outline" disabled={busy} onClick={() => setRevoking(true)}>
              <Trash2 className="h-4 w-4" aria-hidden /> Revoke
            </Button>
          </div>
          <ConfirmDialog
            open={revoking}
            title={`Revoke ${provider.name} credential`}
            description={`The stored secret will be permanently destroyed and this integration will stop working. This cannot be undone.`}
            confirmLabel="Revoke credential"
            danger
            busy={busy}
            onCancel={() => setRevoking(false)}
            onConfirm={async () => {
              await act(() => api.integrationRevoke(workspaceId, credential.id), "Credential revoked.");
              setRevoking(false);
            }}
          />
          {rotating && (
            <CredentialForm provider={provider} secretsOnly busy={busy} submitLabel="Replace secret"
              onCancel={() => setRotating(false)}
              onSubmit={async (secrets) => { await act(() => api.integrationRotate(workspaceId, credential.id, secrets), "Secret rotated."); setRotating(false); }} />
          )}
        </div>
      )}

      {!configured && (
        adding ? (
          <CredentialForm provider={provider} busy={busy} submitLabel="Save credential"
            onCancel={() => setAdding(false)}
            onSubmit={async (secrets, config, label) => {
              await act(() => api.integrationCreate(workspaceId, { provider: provider.id, label, secrets, config }), `${provider.name} connected.`);
              setAdding(false);
            }} />
        ) : (
          <div>
            <Button size="sm" disabled={busy} onClick={() => setAdding(true)}>
              {credential ? "Reconfigure" : "Add credential"}
            </Button>
          </div>
        )
      )}
    </CardContent></Card>
  );
}

function CredentialForm({ provider, secretsOnly, busy, submitLabel, onSubmit, onCancel }: {
  provider: IntegrationProvider;
  secretsOnly?: boolean;
  busy: boolean;
  submitLabel: string;
  onSubmit: (secrets: Record<string, string>, config: Record<string, unknown>, label: string) => Promise<void>;
  onCancel: () => void;
}) {
  const [secrets, setSecrets] = useState<Record<string, string>>({});
  const [config, setConfig] = useState<Record<string, string>>(
    () => Object.fromEntries(provider.config_fields.map((f) => [f.key, f.default ?? ""])),
  );
  const [label, setLabel] = useState("");

  const missingSecret = provider.secret_fields.some((f) => f.required && !secrets[f.key]?.trim());
  const missingConfig = !secretsOnly && provider.config_fields.some((f) => f.required && !config[f.key]?.trim());

  return (
    <div className="mt-1 flex flex-col gap-2 border-t border-border pt-3">
      {provider.secret_fields.map((f) => (
        <label key={f.key} className="flex flex-col gap-1 text-xs">
          <span className="font-medium">{f.label}{f.required ? "" : " (optional)"}</span>
          <Input type="password" autoComplete="off" value={secrets[f.key] ?? ""} disabled={busy}
            placeholder="Entered securely; never displayed again"
            onChange={(e) => setSecrets((s) => ({ ...s, [f.key]: e.target.value }))} />
        </label>
      ))}
      {!secretsOnly && provider.config_fields.map((f) => (
        <label key={f.key} className="flex flex-col gap-1 text-xs">
          <span className="font-medium">{f.label}{f.required ? "" : " (optional)"}</span>
          <Input value={config[f.key] ?? ""} disabled={busy}
            onChange={(e) => setConfig((c) => ({ ...c, [f.key]: e.target.value }))} />
        </label>
      ))}
      {!secretsOnly && (
        <label className="flex flex-col gap-1 text-xs">
          <span className="font-medium">Label (optional)</span>
          <Input value={label} disabled={busy} placeholder="e.g. Main association account"
            onChange={(e) => setLabel(e.target.value)} />
        </label>
      )}
      <div className="flex gap-1">
        <Button size="sm" disabled={busy || missingSecret || missingConfig}
          onClick={() => void onSubmit(secrets, config, label)}>{submitLabel}</Button>
        <Button size="sm" variant="outline" disabled={busy} onClick={onCancel}>Cancel</Button>
      </div>
    </div>
  );
}
