import { describe, expect, it } from "vitest";
import type { WorkspaceDashboard } from "../../lib/api";
import { actionableTasks, deriveMyTasks } from "./tasks";

const data: WorkspaceDashboard = {
  totals: { matches: 10, players: 20, approved_scorecards: 8, seasons: 3, competitions: 2, organisations: 1, media_assets: 0 },
  attention: { scorecards_awaiting_approval: 4, possible_duplicate_matches: 1, research_conflicts: 2, failed_autosync_jobs: 0 },
  research: { projects_active: 1, incomplete_scorecards: 5, open_research_tasks: 3, sources: 7 },
  recent_activity: [],
  is_empty: false,
};

const hasOnly = (perms: string[]) => (p: string) => perms.includes(p);

describe("deriveMyTasks", () => {
  it("gives a Data Verifier only approval tasks", () => {
    const tasks = deriveMyTasks(data, hasOnly(["scorecard.approve"]));
    expect(tasks.map((t) => t.key)).toEqual(["awaiting_approval"]);
    expect(tasks[0].count).toBe(4);
  });

  it("gives a Scorecard Editor the drafts task, not approvals", () => {
    const tasks = deriveMyTasks(data, hasOnly(["match.manage"]));
    expect(tasks.map((t) => t.key)).toEqual(["incomplete_scorecards"]);
  });

  it("gives a Researcher research tasks and conflicts", () => {
    const keys = deriveMyTasks(data, hasOnly(["research.manage"])).map((t) => t.key);
    expect(keys).toContain("open_research_tasks");
    expect(keys).toContain("research_conflicts");
    expect(keys).not.toContain("awaiting_approval");
  });

  it("gives a Viewer no tasks", () => {
    expect(deriveMyTasks(data, hasOnly(["match.view", "ask.query"]))).toEqual([]);
  });

  it("does not duplicate tasks for a user holding several roles", () => {
    const tasks = deriveMyTasks(data, hasOnly(["scorecard.approve", "match.manage", "research.manage", "import.manage"]));
    expect(new Set(tasks.map((t) => t.key)).size).toBe(tasks.length);
  });

  it("actionableTasks keeps only count>0, most-urgent first", () => {
    const tasks = deriveMyTasks(data, hasOnly(["scorecard.approve", "research.manage", "import.manage"]));
    const act = actionableTasks(tasks);
    expect(act.every((t) => t.count > 0)).toBe(true);
    // failed_autosync_jobs is 0 -> dropped; sorted descending by count
    expect(act[0].count).toBeGreaterThanOrEqual(act[act.length - 1].count);
    expect(act.map((t) => t.key)).not.toContain("failed_autosync");
  });

  it("returns nothing when there is no data", () => {
    expect(deriveMyTasks(null, hasOnly(["scorecard.approve"]))).toEqual([]);
  });
});
