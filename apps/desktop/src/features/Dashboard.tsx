import { CheckCircle2, Database, Server, XCircle } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { AppShell } from "../components/layout/AppShell";
import { ErrorState, LoadingState } from "../components/states/States";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { api, ApiError, type DbHealth, type Health } from "../lib/api";

interface Status {
  loading: boolean;
  error: string | null;
  health: Health | null;
  db: DbHealth | null;
}

function StatusRow({
  ok,
  label,
  detail,
  icon,
}: {
  ok: boolean;
  label: string;
  detail: string;
  icon: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-4 py-2">
      <div className="flex items-center gap-2 text-sm">
        <span className="text-muted-foreground">{icon}</span>
        <span className="font-medium">{label}</span>
      </div>
      <div className="flex items-center gap-2 text-sm">
        <span className="text-muted-foreground">{detail}</span>
        {ok ? (
          <CheckCircle2 className="h-4 w-4 text-success" aria-label="ok" />
        ) : (
          <XCircle className="h-4 w-4 text-warning" aria-label="unavailable" />
        )}
      </div>
    </div>
  );
}

export function Dashboard() {
  const [s, setS] = useState<Status>({
    loading: true,
    error: null,
    health: null,
    db: null,
  });

  const load = useCallback(async (signal?: AbortSignal) => {
    setS((p) => ({ ...p, loading: true, error: null }));
    try {
      const health = await api.health(signal);
      const db = await api.dbHealth(signal);
      setS({ loading: false, error: null, health, db });
    } catch (e) {
      if (signal?.aborted) return;
      const msg = e instanceof ApiError ? e.message : "Unexpected error";
      setS({ loading: false, error: msg, health: null, db: null });
    }
  }, []);

  useEffect(() => {
    const ctrl = new AbortController();
    void load(ctrl.signal);
    return () => ctrl.abort();
  }, [load]);

  return (
    <AppShell title="Dashboard" subtitle="OneStats foundation — development build">
      <div className="grid gap-5 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Backend connection</CardTitle>
          </CardHeader>
          <CardContent>
            {s.loading && <LoadingState label="Checking the OneStats backend..." />}
            {!s.loading && s.error && (
              <ErrorState message={s.error} onRetry={() => void load()} />
            )}
            {!s.loading && !s.error && s.health && s.db && (
              <div className="divide-y divide-border">
                <StatusRow
                  ok
                  label="API"
                  detail={`${s.health.service} v${s.health.version} (${s.health.env})`}
                  icon={<Server className="h-4 w-4" aria-hidden />}
                />
                <StatusRow
                  ok={s.db.database_connected}
                  label="Database"
                  detail={
                    s.db.database_connected
                      ? "connected"
                      : s.db.database_configured
                        ? "configured, not reachable"
                        : "not configured"
                  }
                  icon={<Database className="h-4 w-4" aria-hidden />}
                />
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Getting started</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            <p>
              This is the Phase 2 foundation build. The six primary sections are available
              in the sidebar as labelled placeholders. Cricket-domain features arrive in
              later phases.
            </p>
            <p className="mt-3">
              If the database shows "not configured", set the{" "}
              <code className="rounded bg-muted px-1">onestats_app</code> credential in the
              backend's <code className="rounded bg-muted px-1">.env</code> (see
              docs/DEVELOPMENT.md).
            </p>
          </CardContent>
        </Card>
      </div>
    </AppShell>
  );
}
