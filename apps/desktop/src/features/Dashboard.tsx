import { Building2, CheckCircle2, Server } from "lucide-react";
import { useEffect, useState } from "react";
import { AppShell } from "../components/layout/AppShell";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { api } from "../lib/api";
import { useWorkspace } from "../lib/workspace-context";

export function Dashboard() {
  const { current } = useWorkspace();
  const [version, setVersion] = useState<string | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    api
      .health()
      .then((h) => setVersion(`${h.version} (${h.env})`))
      .catch(() => setVersion(null));
    return () => ctrl.abort();
  }, []);

  return (
    <AppShell
      title="Dashboard"
      subtitle={current ? current.name : "Select or create a workspace"}
    >
      <div className="grid gap-5 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Current workspace</CardTitle>
          </CardHeader>
          <CardContent>
            {current ? (
              <div className="flex items-center gap-3">
                <Building2 className="h-5 w-5 text-muted-foreground" aria-hidden />
                <div>
                  <div className="font-medium">{current.name}</div>
                  <div className="text-sm text-muted-foreground">
                    {current.short_name} · {current.type}
                    {current.roles?.length ? ` · ${current.roles.join(", ")}` : ""}
                  </div>
                </div>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                No workspace selected. Use <b>My Workspaces</b> in the sidebar.
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>System</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-between py-1 text-sm">
              <span className="flex items-center gap-2">
                <Server className="h-4 w-4 text-muted-foreground" aria-hidden /> OneStats API
              </span>
              {version ? (
                <span className="flex items-center gap-2 text-muted-foreground">
                  v{version} <CheckCircle2 className="h-4 w-4 text-success" aria-label="ok" />
                </span>
              ) : (
                <span className="text-muted-foreground">checking…</span>
              )}
            </div>
            <p className="mt-3 text-sm text-muted-foreground">
              Phase 3 foundation. Cricket-domain features arrive in later phases.
            </p>
          </CardContent>
        </Card>
      </div>
    </AppShell>
  );
}
