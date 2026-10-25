/**
 * Connection configuration (Phase 17) — choose how this computer reaches the OneStats backend:
 *  • "This computer (standalone)" — a local backend + database on this machine, or
 *  • "Connect to a server" — an existing shared OneStats server (the additional-client install path).
 * The choice is stored per machine and used at runtime, so one build serves all three install paths.
 * Test the connection before saving; saving reloads so the app re-bootstraps against the new server.
 */
import { useState } from "react";
import { Button } from "../../components/ui/button";
import { getApiBase, setApiBase } from "../../lib/api";

const LOCAL = "http://localhost:8000";

async function testConnection(url: string): Promise<boolean> {
  try {
    const r = await fetch(`${url.replace(/\/+$/, "")}/api/v1/health`, { method: "GET" });
    return r.ok;
  } catch {
    return false;
  }
}

export function ConnectionSettings({ compact = false }: { compact?: boolean }) {
  const current = getApiBase();
  const [mode, setMode] = useState<"standalone" | "server">(current === LOCAL ? "standalone" : "server");
  const [url, setUrl] = useState(current === LOCAL ? "" : current);
  const [result, setResult] = useState<"ok" | "fail" | null>(null);
  const [busy, setBusy] = useState(false);

  const target = mode === "standalone" ? LOCAL : url.trim();

  const test = async () => {
    setBusy(true); setResult(null);
    setResult((await testConnection(target)) ? "ok" : "fail");
    setBusy(false);
  };
  const save = () => {
    setApiBase(mode === "standalone" ? null : target);   // null → use the default (local)
    window.location.reload();
  };

  const field = "w-full rounded-[var(--radius-app)] border border-border bg-card px-3 py-2 text-sm";
  return (
    <div className="flex flex-col gap-3">
      {!compact && (
        <div>
          <h3 className="text-sm font-semibold">Server Connection</h3>
          <p className="text-xs text-muted-foreground">Where this computer finds the OneStats backend. Change this to connect an additional computer to your main OneStats server.</p>
        </div>
      )}
      <div className="flex flex-col gap-2 text-sm">
        <label className="flex items-center gap-2">
          <input type="radio" name="conn_mode" checked={mode === "standalone"} onChange={() => { setMode("standalone"); setResult(null); }} />
          This computer (standalone) — local backend &amp; database
        </label>
        <label className="flex items-center gap-2">
          <input type="radio" name="conn_mode" checked={mode === "server"} onChange={() => { setMode("server"); setResult(null); }} />
          Connect to a server
        </label>
        {mode === "server" && (
          <input className={field} value={url} onChange={(e) => { setUrl(e.target.value); setResult(null); }}
            placeholder="https://onestats.yourclub.local:8000" aria-label="Server URL" />
        )}
      </div>
      {result === "ok" && <p className="text-xs text-success">Connected — the OneStats server responded.</p>}
      {result === "fail" && <p className="text-xs text-danger">Could not reach {target || "(no URL)"}. Check the address and that the server is running.</p>}
      <div className="flex gap-2">
        <Button size="sm" variant="outline" disabled={busy || (mode === "server" && !url.trim())} onClick={() => void test()}>
          {busy ? "Testing…" : "Test connection"}
        </Button>
        <Button size="sm" disabled={mode === "server" && !url.trim()} onClick={save}>Save &amp; reconnect</Button>
      </div>
      <p className="text-xs text-muted-foreground">Currently using <code className="rounded bg-muted px-1">{current}</code>.</p>
    </div>
  );
}
