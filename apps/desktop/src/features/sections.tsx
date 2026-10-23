import { Placeholder } from "./Placeholder";

// Matches and People now have full feature screens (features/scorecard, features/people);
// their old placeholders were removed. The sections below remain placeholders until built.

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
