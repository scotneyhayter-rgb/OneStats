import { Building2, Plus } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { AppShell } from "../../components/layout/AppShell";
import { EmptyState, ErrorState, LoadingState } from "../../components/states/States";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import { useAuth } from "../../lib/auth";
import { useWorkspace } from "../../lib/workspace-context";

export function MyWorkspaces() {
  const { user } = useAuth();
  const { workspaces, loading, error, setCurrent, reload } = useWorkspace();
  const nav = useNavigate();

  return (
    <AppShell title="My Workspaces" subtitle="Organisations you can access">
      {loading && <LoadingState label="Loading your workspaces..." />}
      {!loading && error && <ErrorState message={error} onRetry={() => void reload()} />}
      {!loading && !error && (
        <>
          {user?.is_super_admin && (
            <div className="mb-5">
              <Button onClick={() => nav("/onboarding")}>
                <Plus className="h-4 w-4" aria-hidden /> Create workspace
              </Button>
            </div>
          )}
          {workspaces.length === 0 ? (
            <EmptyState
              icon={<Building2 className="h-8 w-8" aria-hidden />}
              title="No workspaces yet"
              description={
                user?.is_super_admin
                  ? "Start onboarding to create your first cricket organisation."
                  : "Ask a Super Administrator to add you to a workspace."
              }
            />
          ) : (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {workspaces.map((w) => (
                <Card key={w.id}>
                  <CardContent className="flex flex-col gap-3 py-5">
                    <div className="flex items-center gap-2">
                      <Building2 className="h-5 w-5 text-muted-foreground" aria-hidden />
                      <div className="min-w-0">
                        <div className="truncate font-medium">{w.name}</div>
                        <div className="truncate text-xs text-muted-foreground">
                          {w.short_name} · {w.type}
                        </div>
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {(w.roles ?? []).map((r) => (
                        <span key={r} className="rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">
                          {r.replace(/_/g, " ")}
                        </span>
                      ))}
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        setCurrent(w.id);
                        nav("/dashboard");
                      }}
                    >
                      Open
                    </Button>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </>
      )}
    </AppShell>
  );
}
