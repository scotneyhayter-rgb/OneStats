import {
  BarChart3,
  LayoutDashboard,
  MessageCircleQuestion,
  Settings,
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
