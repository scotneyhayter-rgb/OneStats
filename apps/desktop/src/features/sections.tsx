import { Placeholder } from "./Placeholder";

export function Matches() {
  return (
    <Placeholder
      title="Matches"
      subtitle="Match management, scorecard entry, import and research"
      planned={[
        "Match management (list, filter, create, edit)",
        "Fast spreadsheet-style scorecard entry",
        "Import matches (Cricket Statz, PlayHQ)",
        "Research Centre (historical scorecards, discovery, timeline)",
      ]}
    />
  );
}

export function People() {
  return (
    <Placeholder
      title="People"
      subtitle="Player registry, profiles and identity management"
      planned={[
        "Canonical people registry and profiles",
        "Player Management — Find & Merge Duplicates",
        "Roles, history and affiliations",
        "Milestone badges and achievements",
      ]}
    />
  );
}

export function Statistics() {
  return (
    <Placeholder
      title="Statistics"
      subtitle="Records, reports and the statistics engine"
      planned={[
        "Club records and player statistics",
        "Batting, bowling, fielding and partnerships",
        "Teams & captains, milestones",
        "Report Builder and Data Integrity",
      ]}
    />
  );
}

export function Ask() {
  return (
    <Placeholder
      title="Ask OneStats"
      subtitle="Natural-language statistical queries"
      planned={[
        "Deterministic natural-language query mapping",
        "Answers from verified records only",
        "Supporting records and qualifications",
      ]}
    />
  );
}

export function Settings() {
  return (
    <Placeholder
      title="Settings"
      subtitle="Workspace, branding, users and configuration"
      planned={[
        "Workspace and onboarding",
        "Branding and themes (workspace-specific)",
        "Users and permissions",
        "Publishing, media and import connectors",
      ]}
    />
  );
}
