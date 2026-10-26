/** Forced first-login password change (temporary passwords must be changed before use). */
import { KeyRound } from "lucide-react";
import { useState } from "react";
import { ApiError, api } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { Button } from "../../components/ui/button";

const inputClass =
  "w-full rounded-[var(--radius-app)] border border-border bg-card px-3 py-2 text-sm focus-visible:outline-2 focus-visible:outline-[var(--ring)]";

export function ChangePassword() {
  const { refresh, logout } = useAuth();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (next !== confirm) { setError("The new passwords do not match."); return; }
    setBusy(true); setError(null);
    try {
      await api.changePassword(current, next);
      await refresh();                 // re-fetch /me → must_change_password cleared → app proceeds
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not change the password.");
    } finally { setBusy(false); }
  }

  return (
    <div className="flex h-screen w-screen items-center justify-center bg-background p-4 text-foreground">
      <div className="w-full max-w-sm rounded-[var(--radius-app)] border border-border bg-card p-6 shadow-sm">
        <div className="mb-4 flex items-center gap-2 text-muted-foreground">
          <KeyRound className="h-5 w-5" aria-hidden />
          <div>
            <div className="font-medium text-foreground">Set a new password</div>
            <div className="text-sm">Your temporary password must be changed before you continue.</div>
          </div>
        </div>
        <form onSubmit={submit} className="space-y-3">
          <label className="block text-sm"><span className="mb-1 block text-muted-foreground">Current (temporary) password</span>
            <input className={inputClass} type="password" value={current} onChange={(e) => setCurrent(e.target.value)} autoFocus required /></label>
          <label className="block text-sm"><span className="mb-1 block text-muted-foreground">New password (min 10, a letter and a number)</span>
            <input className={inputClass} type="password" value={next} onChange={(e) => setNext(e.target.value)} minLength={10} required /></label>
          <label className="block text-sm"><span className="mb-1 block text-muted-foreground">Confirm new password</span>
            <input className={inputClass} type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} minLength={10} required /></label>
          {error && <p className="text-sm text-danger">{error}</p>}
          <Button type="submit" className="w-full" disabled={busy}>{busy ? "Saving…" : "Set password & continue"}</Button>
          <button type="button" className="w-full text-xs text-muted-foreground hover:underline" onClick={() => void logout()}>Sign out</button>
        </form>
      </div>
    </div>
  );
}
