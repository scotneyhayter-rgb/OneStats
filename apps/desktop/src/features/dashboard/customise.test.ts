import { describe, expect, it } from "vitest";
import { CUSTOMISABLE_SECTIONS, hiddenSet, isHidden, toggleHidden } from "./customise";

describe("dashboard customisation", () => {
  it("defaults to everything visible", () => {
    expect(hiddenSet(undefined).size).toBe(0);
    expect(isHidden({}, "summary")).toBe(false);
  });

  it("toggles a customisable section off and on without mutating the input", () => {
    const base = {};
    const hidden = toggleHidden(base, "activity");
    expect(isHidden(hidden, "activity")).toBe(true);
    expect(base).toEqual({}); // not mutated
    const shown = toggleHidden(hidden, "activity");
    expect(isHidden(shown, "activity")).toBe(false);
  });

  it("NEVER hides a non-customisable section, even if asked", () => {
    const after = toggleHidden({}, "mytasks");
    expect(isHidden(after, "mytasks")).toBe(false);
    expect(hiddenSet(after).has("mytasks")).toBe(false);
  });

  it("ignores a tampered prefs blob that lists a non-customisable key as hidden", () => {
    // even if the stored prefs claim to hide the security banner / tasks, they stay visible
    const tampered = { hidden: ["summary", "mytasks", "super_admin_banner"] };
    const h = hiddenSet(tampered);
    expect(h.has("summary")).toBe(true);        // allowed
    expect(h.has("mytasks")).toBe(false);       // rejected
    expect(h.has("super_admin_banner")).toBe(false);
  });

  it("only exposes the three non-critical sections as customisable", () => {
    expect(CUSTOMISABLE_SECTIONS.map((s) => s.key).sort()).toEqual(["activity", "research", "summary"]);
  });
});
