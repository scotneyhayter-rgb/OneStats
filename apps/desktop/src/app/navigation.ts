import {
  BarChart3,
  Building2,
  DatabaseBackup,
  Award,
  GitBranch,
  Globe,
  Image,
  LayoutDashboard,
  MessageCircleQuestion,
  RefreshCw,
  ScrollText,
  Settings,
  SlidersHorizontal,
  Smartphone,
  Trophy,
  UserCog,
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
  /** Permission required to SEE this section (role-based nav gating). Undefined = visible to any
   * member of the workspace. The backend still enforces permissions on every action. */
  perm?: string;
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
    perm: "match.view",
  },
  {
    key: "people",
    label: "People",
    path: "/people",
    icon: Users,
    blurb: "Player registry, profiles and identity management.",
    perm: "match.view",
  },
  {
    key: "statistics",
    label: "Statistics",
    path: "/statistics",
    icon: BarChart3,
    blurb: "Records, reports and the statistics engine.",
    perm: "match.view",
  },
  {
    key: "ask",
    label: "Ask OneStats",
    path: "/ask",
    icon: MessageCircleQuestion,
    blurb: "Natural-language statistical queries.",
    perm: "ask.query",
  },
  {
    key: "settings",
    label: "Settings",
    path: "/settings",
    icon: Settings,
    blurb: "Workspace, branding, users and configuration.",
    perm: "workspace.manage",
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
    perm: "organisation.manage",
  },
  {
    key: "teams-venues",
    label: "Teams & Venues",
    path: "/manage/teams-venues",
    icon: Users,
    blurb: "Teams, cricket programs and grounds.",
    perm: "venue.manage",
  },
  {
    key: "competitions",
    label: "Competitions",
    path: "/manage/competitions",
    icon: Trophy,
    blurb: "Competitions, divisions, grades and seasons.",
    perm: "competition.manage",
  },
  {
    key: "conditions",
    label: "Playing Conditions",
    path: "/manage/conditions",
    icon: SlidersHorizontal,
    blurb: "Historical rules by competition, season, grade and match.",
    perm: "competition.manage",
  },
  {
    key: "history",
    label: "Organisation History",
    path: "/manage/history",
    icon: GitBranch,
    blurb: "Timeline, relationships and provenance.",
    perm: "organisation.manage",
  },
  {
    key: "import",
    label: "Import Data",
    path: "/manage/import",
    icon: DatabaseBackup,
    blurb: "Import matches and scorecards from CricketStatz and other sources.",
    perm: "import.manage",
  },
  {
    key: "autosync",
    label: "AutoSync",
    path: "/manage/autosync",
    icon: RefreshCw,
    blurb: "Automatically discover new and historical matches and scorecard updates.",
    perm: "import.manage",
  },
  {
    key: "research",
    label: "Research Centre",
    path: "/manage/research",
    icon: ScrollText,
    blurb: "Reconstruct historical matches from newspapers, scorebooks and other sources.",
    perm: "research.manage",
  },
  {
    key: "media",
    label: "Media Archive",
    path: "/manage/media",
    icon: Image,
    blurb: "Preserve original scorecard images, photographs and documents, with heritage collections.",
    perm: "media.manage",
  },
  {
    key: "records",
    label: "Records & Achievements",
    path: "/manage/records",
    icon: Award,
    blurb: "All-time record holders, seasonal leaders, milestones, Life Members and the Club Record Book.",
    perm: "match.view",
  },
  {
    key: "publishing",
    label: "Website Publishing",
    path: "/manage/publishing",
    icon: Globe,
    blurb: "Publish reports and player profiles to permanent public URLs, or export them for your website.",
    perm: "publish.configure",
  },
  {
    key: "portal",
    label: "Member Portal",
    path: "/manage/portal",
    icon: Smartphone,
    blurb: "The members' read-only view of published and members-only records, with Ask OneStats.",
    perm: "match.view",
  },
  {
    key: "members",
    label: "Members",
    path: "/manage/members",
    icon: UserCog,
    blurb: "Add people to this workspace and manage their roles.",
    perm: "user.admin",
  },
];
