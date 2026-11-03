import { describe, expect, it } from "vitest";
import { MANAGEMENT_SECTIONS, NAV_SECTIONS } from "./navigation";

describe("primary navigation", () => {
  it("defines the primary sections in order (Records promoted next to Statistics)", () => {
    expect(NAV_SECTIONS).toHaveLength(8);
    expect(NAV_SECTIONS.map((s) => s.label)).toEqual([
      "Dashboard",
      "International Updates",
      "Matches",
      "People",
      "Statistics",
      "Records & Achievements",
      "Ask OneStats",
      "Settings",
    ]);
  });

  it("gates International Updates to international workspaces only", () => {
    const intl = NAV_SECTIONS.find((s) => s.key === "intl-updates");
    expect(intl?.workspaceType).toBe("international");
    expect(intl?.perm).toBe("workspace.manage");
    // every other primary section is available to any workspace type
    for (const s of NAV_SECTIONS) {
      if (s.key !== "intl-updates") expect(s.workspaceType).toBeUndefined();
    }
  });

  it("has unique keys and paths", () => {
    const keys = new Set(NAV_SECTIONS.map((s) => s.key));
    const paths = new Set(NAV_SECTIONS.map((s) => s.path));
    expect(keys.size).toBe(NAV_SECTIONS.length);
    expect(paths.size).toBe(NAV_SECTIONS.length);
  });

  it("gives every section an icon and an absolute path", () => {
    for (const s of NAV_SECTIONS) {
      expect(s.icon).toBeTruthy();
      expect(s.path.startsWith("/")).toBe(true);
    }
  });
});

describe("club-management navigation (Phase 4, Stage 7)", () => {
  it("defines the management screens under /manage, grouped and ordered", () => {
    expect(MANAGEMENT_SECTIONS.map((s) => s.label)).toEqual([
      "Organisations",
      "Organisation History",
      "Teams & Venues",
      "Competitions",
      "Playing Conditions",
      "Import Data",
      "AutoSync",
      "Research Centre",
      "Media Archive",
      "Website Publishing",
      "Member Portal",
      "Members",
    ]);
    for (const s of MANAGEMENT_SECTIONS) {
      expect(s.path.startsWith("/manage/")).toBe(true);
      expect(s.icon).toBeTruthy();
      expect(s.group).toBeTruthy();
    }
  });

  it("groups the management sections into three contiguous sub-groups", () => {
    expect([...new Set(MANAGEMENT_SECTIONS.map((s) => s.group))]).toEqual([
      "Club structure",
      "Data & sources",
      "Publishing & members",
    ]);
  });

  it("does not collide with the primary sections", () => {
    const primary = new Set(NAV_SECTIONS.map((s) => s.path));
    for (const s of MANAGEMENT_SECTIONS) expect(primary.has(s.path)).toBe(false);
  });
});
