import { KeyRound, ShieldCheck } from "lucide-react";
import { useState, type ReactNode } from "react";
import onestatsLogo from "../../assets/onestats-logo.png";
import { ApiError, api, setToken } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import { ErrorState } from "../../components/states/States";
import { ConnectionSettings } from "../settings/ConnectionSettings";

function AuthShell({ title, subtitle, icon, children }: {
  title: string; subtitle: string; icon: ReactNode; children: ReactNode;
}) {
  return (
    <div className="flex h-screen w-screen items-center justify-center bg-background p-4 text-foreground">
      <div className="w-full max-w-sm">
        {/* Official OneStats logo (supplied artwork, unmodified). It has a white background, so it
            sits on a white plate to read consistently in both light and dark themes. */}
        <div className="mb-6 flex justify-center rounded-[var(--radius-app)] border border-border bg-white p-4 shadow-sm">
          <img src={onestatsLogo} alt="OneStats — Cricket Statistics Made Simple" className="h-auto w-full max-w-[280px]" />
        </div>
        <Card>
          <CardContent className="py-6">
            <div className="mb-4 flex items-center gap-2 text-muted-foreground">
              {icon}
              <div>
                <div className="font-medium text-foreground">{title}</div>
                <div className="text-sm">{subtitle}</div>
              </div>
            </div>
            {children}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

const inputClass =
  "w-full rounded-[var(--radius-app)] border border-border bg-card px-3 py-2 text-sm focus-visible:outline-2 focus-visible:outline-[var(--ring)]";

export function Login() {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(username, password);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell title="Sign in" subtitle="Access your OneStats workspaces" icon={<KeyRound className="h-5 w-5" aria-hidden />}>
      <form onSubmit={submit} className="space-y-3">
        <label className="block text-sm">
          <span className="mb-1 block text-muted-foreground">Username</span>
          <input className={inputClass} value={username} onChange={(e) => setUsername(e.target.value)} autoFocus required />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block text-muted-foreground">Password</span>
          <input className={inputClass} type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </label>
        {error && <p className="text-sm text-danger">{error}</p>}
        <Button type="submit" className="w-full" disabled={busy}>
          {busy ? "Signing in..." : "Sign in"}
        </Button>
      </form>
    </AuthShell>
  );
}

export function Setup() {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [token, setTok] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.createSuperAdmin(username, password, token.trim());
      setToken(null);
      await login(username, password);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Setup failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell
      title="First-run setup"
      subtitle="Create the Super Administrator"
      icon={<ShieldCheck className="h-5 w-5" aria-hidden />}
    >
      <p className="mb-3 text-sm text-muted-foreground">
        Enter the one-time setup token from the server (file{" "}
        <code className="rounded bg-muted px-1">.onestats-setup-token</code>) to create the
        first administrator account.
      </p>
      <form onSubmit={submit} className="space-y-3">
        <label className="block text-sm">
          <span className="mb-1 block text-muted-foreground">Admin username</span>
          <input className={inputClass} value={username} onChange={(e) => setUsername(e.target.value)} minLength={3} required />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block text-muted-foreground">Password (min 10 chars)</span>
          <input className={inputClass} type="password" value={password} onChange={(e) => setPassword(e.target.value)} minLength={10} required />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block text-muted-foreground">Setup token</span>
          <input className={inputClass} value={token} onChange={(e) => setTok(e.target.value)} required />
        </label>
        {error && <p className="text-sm text-danger">{error}</p>}
        <Button type="submit" className="w-full" disabled={busy}>
          {busy ? "Creating..." : "Create administrator"}
        </Button>
      </form>
    </AuthShell>
  );
}

export function BackendDown({ message }: { message: string }) {
  const { refresh } = useAuth();
  return (
    <div className="flex h-screen w-screen items-center justify-center bg-background p-4">
      <div className="w-full max-w-md space-y-3">
        <ErrorState message={message} onRetry={() => void refresh()} />
        <Card><CardContent className="py-4">
          <ConnectionSettings />
        </CardContent></Card>
      </div>
    </div>
  );
}
