import type { WorkspaceDashboard } from "../../lib/api";

/**
 * "My Tasks" derivation for the shared dashboard (Part 16 — a single task surface, no duplicate
 * task system). Tasks are derived from the authoritative workspace dashboard figures and filtered
 * by what the signed-in user can actually ACT on in this workspace: a verifier sees approvals, an
 * editor sees drafts, a researcher sees research work, an admin sees data-quality items. All counts
 * come from the backend — never fabricated. Phase E will deepen this with per-item detail.
 */
export interface DashboardTask {
  key: string;
  label: string;
  count: number;
  to: string;
  /** visual urgency; "warning" when the item needs action, "muted" when it is a zero/steady state */
  tone: "warning" | "muted";
}

/** `has(perm)` should report whether the user holds `perm` in the current workspace. */
export function deriveMyTasks(
  data: WorkspaceDashboard | null,
  has: (perm: string) => boolean,
): DashboardTask[] {
  if (!data) return [];
  const at = data.attention;
  const rs = data.research;
  const tasks: DashboardTask[] = [];
  const add = (key: string, label: string, count: number, to: string) =>
    tasks.push({ key, label, count, to, tone: count > 0 ? "warning" : "muted" });

  // Data Verifier — scorecards awaiting approval
  if (has("scorecard.approve")) {
    add("awaiting_approval", "Scorecards awaiting approval", at.scorecards_awaiting_approval, "/matches");
  }
  // Scorecard Editor — drafts to finish and submit
  if (has("match.manage")) {
    add("incomplete_scorecards", "Draft / incomplete scorecards", rs.incomplete_scorecards, "/matches");
  }
  // Researcher — open research tasks and conflicts to resolve
  if (has("research.manage")) {
    add("open_research_tasks", "Open research tasks", rs.open_research_tasks, "/manage/research");
    add("research_conflicts", "Research conflicts", at.research_conflicts, "/manage/research");
  }
  // Organisation Admin / data quality — imports and duplicates
  if (has("import.manage")) {
    add("failed_autosync", "Failed AutoSync jobs", at.failed_autosync_jobs, "/manage/autosync");
    add("possible_duplicates", "Possible duplicate matches", at.possible_duplicate_matches, "/manage/autosync");
  }

  // de-duplicate by key (a user with several roles should not see a task twice)
  const seen = new Set<string>();
  return tasks.filter((t) => (seen.has(t.key) ? false : (seen.add(t.key), true)));
}

/** Only the tasks that currently need action (count > 0), most-urgent first. */
export function actionableTasks(tasks: DashboardTask[]): DashboardTask[] {
  return tasks.filter((t) => t.count > 0).sort((a, b) => b.count - a.count);
}
