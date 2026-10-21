import { Construction } from "lucide-react";
import { AppShell } from "../components/layout/AppShell";
import { Card, CardContent } from "../components/ui/card";

/**
 * Foundation placeholder for a primary section. Phase 2 ships the navigation shell only;
 * the full module functionality is built in later phases (clearly labelled, not faked).
 */
export function Placeholder({
  title,
  subtitle,
  planned,
}: {
  title: string;
  subtitle: string;
  planned: string[];
}) {
  return (
    <AppShell title={title} subtitle={subtitle}>
      <Card>
        <CardContent className="flex flex-col gap-4 py-8">
          <div className="flex items-center gap-3 text-muted-foreground">
            <Construction className="h-6 w-6" aria-hidden />
            <span className="font-medium">Foundation placeholder</span>
          </div>
          <p className="text-sm text-muted-foreground">
            This section's navigation is in place. Its functionality is planned for a later
            development phase and is not implemented yet.
          </p>
          <div>
            <p className="mb-2 text-sm font-medium">Planned for this section</p>
            <ul className="list-inside list-disc space-y-1 text-sm text-muted-foreground">
              {planned.map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
          </div>
        </CardContent>
      </Card>
    </AppShell>
  );
}
