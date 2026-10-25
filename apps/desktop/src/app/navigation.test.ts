import { describe, expect, it } from "vitest";
import { MANAGEMENT_SECTIONS, NAV_SECTIONS } from "./navigation";

describe("primary navigation", () => {
  it("defines exactly the six approved sections", () => {
    expect(NAV_SECTIONS).toHaveLength(6);
    expect(NAV_SECTIONS.map((s) => s.label)).toEqual([
      "Dashboard",
      "Matches",
      "People",
      "Statistics",
      "Ask OneStats",
      "Settings",
    ]);
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
  it("defines the management screens under /manage", () => {
    expect(MANAGEMENT_SECTIONS.map((s) => s.label)).toEqual([
      "Organisations",
      "Teams & Venues",
      "Competitions",
      "Playing Conditions",
      "Organisation History",
      "Import Data",
      "AutoSync",
      "Research Centre",
    ]);
    for (const s of MANAGEMENT_SECTIONS) {
      expect(s.path.startsWith("/manage/")).toBe(true);
      expect(s.icon).toBeTruthy();
    }
  });

  it("does not collide with the primary sections", () => {
    const primary = new Set(NAV_SECTIONS.map((s) => s.path));
    for (const s of MANAGEMENT_SECTIONS) expect(primary.has(s.path)).toBe(false);
  });
});
