// @vitest-environment jsdom
/** Theme registry + Club-branding runtime derivation/application. */
import { afterEach, describe, expect, it } from "vitest";
import { DEFAULT_THEME, isThemeId, THEME_BY_ID, THEMES } from "./themes";
import { applyClubVars, deriveClubVars } from "./branding-runtime";

describe("theme registry", () => {
  it("registers all eight themes including Club and OneStats", () => {
    expect(THEMES).toHaveLength(8);
    const ids = THEMES.map((t) => t.id);
    for (const id of ["traditional", "modern", "professional", "test", "oneday", "t20", "club", "onestats"]) {
      expect(ids).toContain(id);
    }
  });
  it("defaults to Modern", () => {
    expect(DEFAULT_THEME).toBe("modern");
  });
  it("marks Club as club-driven and OneStats as protected/official", () => {
    expect(THEME_BY_ID.club.clubDriven).toBe(true);
    expect(THEME_BY_ID.onestats.official).toBe(true);
  });
  it("validates theme ids", () => {
    expect(isThemeId("club")).toBe(true);
    expect(isThemeId("onestats")).toBe(true);
    expect(isThemeId("nope")).toBe(false);
    expect(isThemeId(null)).toBe(false);
  });
});

describe("deriveClubVars", () => {
  it("derives a full set of club variables from a primary colour", () => {
    const v = deriveClubVars({ primary: "#0b2447", accent: "#1a8fb3" });
    expect(v["--club-primary"]).toBe("#0b2447");
    expect(v["--club-primary-foreground"]).toBe("#ffffff"); // dark primary → white text
    expect(v["--club-accent"]).toBe("#1a8fb3");
    expect(v["--club-sidebar"]).toBeDefined();
    expect(v["--club-sidebar-foreground"]).toBeDefined();
  });
  it("uses secondary as the accent when no accent is given", () => {
    const v = deriveClubVars({ primary: "#334155", secondary: "#e8590c" });
    expect(v["--club-accent"]).toBe("#e8590c");
  });
  it("returns nothing for empty/invalid input (neutral fallback used by CSS)", () => {
    expect(deriveClubVars({})).toEqual({});
    expect(deriveClubVars({ primary: "not-a-colour" })).toEqual({});
  });
});

describe("applyClubVars", () => {
  afterEach(() => applyClubVars(null));
  it("sets and clears the club vars on the document root", () => {
    applyClubVars({ primary: "#7b2ff7" });
    expect(document.documentElement.style.getPropertyValue("--club-primary")).toBe("#7b2ff7");
    applyClubVars(null); // workspace switch with no branding → cleared
    expect(document.documentElement.style.getPropertyValue("--club-primary")).toBe("");
  });
});
