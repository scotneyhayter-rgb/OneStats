import {
  BarChart3,
  Building2,
  DatabaseBackup,
  GitBranch,
  LayoutDashboard,
  MessageCircleQuestion,
  Settings,
  SlidersHorizontal,
  Trophy,
  Users,
  type LucideIcon,
} from "lucide-react";

/** The six approved primary navigation sections (deliverable 10, §4). */
export interface NavSection {
  key: string;
  label: string;
  path: string;
  icon: LucideIcon;
  blurb: string;
}

export const NAV_SECTIONS: NavSection[] = [
  {
    key: "dashboard",
    label: "Dashboard",
    path: "/dashboard",
    icon: LayoutDashboard,
    blurb: "Overview, recent activity and alerts.",
  },
  {
    key: "matches",
    label: "Matches",
    path: "/matches",
    icon: Trophy,
    blurb: "Match management, scorecard entry, import and research.",
  },
  {
    key: "people",
    label: "People",
    path: "/people",
    icon: Users,
    blurb: "Player registry, profiles and identity management.",
  },
  {
    key: "statistics",
    label: "Statistics",
    path: "/statistics",
    icon: BarChart3,
    blurb: "Records, reports and the statistics engine.",
  },
  {
    key: "ask",
    label: "Ask OneStats",
    path: "/ask",
    icon: MessageCircleQuestion,
    blurb: "Natural-language statistical queries.",
  },
  {
    key: "settings",
    label: "Settings",
    path: "/settings",
    icon: Settings,
    blurb: "Workspace, branding, users and configuration.",
  },
];

/**
 * Phase 4 club-management screens. These are a distinct, workspace-scoped group — separate from
 * the six approved primary sections above — surfaced under their own sidebar heading.
 */
export const MANAGEMENT_SECTIONS: NavSection[] = [
  {
    key: "organisations",
    label: "Organisations",
    path: "/manage/organisations",
    icon: Building2,
    blurb: "Clubs, associations and historical organisations.",
  },
  {
    key: "teams-venues",
    label: "Teams & Venues",
    path: "/manage/teams-venues",
    icon: Users,
    blurb: "Teams, cricket programs and grounds.",
  },
  {
    key: "competitions",
    label: "Competitions",
    path: "/manage/competitions",
    icon: Trophy,
    blurb: "Competitions, divisions, grades and seasons.",
  },
  {
    key: "conditions",
    label: "Playing Conditions",
    path: "/manage/conditions",
    icon: SlidersHorizontal,
    blurb: "Historical rules by competition, season, grade and match.",
  },
  {
    key: "history",
    label: "Organisation History",
    path: "/manage/history",
    icon: GitBranch,
    blurb: "Timeline, relationships and provenance.",
  },
  {
    key: "import",
    label: "Import Data",
    path: "/manage/import",
    icon: DatabaseBackup,
    blurb: "Import matches and scorecards from CricketStatz and other sources.",
  },
];
