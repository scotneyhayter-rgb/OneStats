import type { MyTask } from "../../lib/api";

/**
 * Frontend helpers for the unified "My Tasks" surface (Part 16). The task items themselves come
 * from the backend `/workspaces/{id}/tasks` endpoint, which reuses the verification queue and the
 * Research Centre tasks and filters by the user's permissions — there is no separate client task
 * system. These helpers only decide presentation.
 */

/** The permissions that let a user act on at least one kind of task; used to decide whether to
 * show the My Tasks section at all. */
const TASK_PERMISSIONS = ["scorecard.approve", "match.manage", "research.manage"];

export function canSeeTasks(has: (perm: string) => boolean): boolean {
  return TASK_PERMISSIONS.some(has);
}

export function kindLabel(kind: MyTask["kind"]): string {
  switch (kind) {
    case "approval": return "Approve";
    case "draft": return "Draft";
    case "research": return "Research";
  }
}

/** Badge tone per task kind (approvals are the most urgent). */
export function kindTone(kind: MyTask["kind"]): "warning" | "brand" | "muted" {
  switch (kind) {
    case "approval": return "warning";
    case "research": return "brand";
    case "draft": return "muted";
  }
}
