import { describe, expect, it } from "vitest";
import { canSeeTasks, kindLabel, kindTone } from "./tasks";

const hasOnly = (perms: string[]) => (p: string) => perms.includes(p);

describe("canSeeTasks", () => {
  it("is true for a verifier, editor or researcher", () => {
    expect(canSeeTasks(hasOnly(["scorecard.approve"]))).toBe(true);
    expect(canSeeTasks(hasOnly(["match.manage"]))).toBe(true);
    expect(canSeeTasks(hasOnly(["research.manage"]))).toBe(true);
  });
  it("is false for a viewer", () => {
    expect(canSeeTasks(hasOnly(["match.view", "ask.query", "export"]))).toBe(false);
  });
});

describe("kind presentation", () => {
  it("labels each kind", () => {
    expect(kindLabel("approval")).toBe("Approve");
    expect(kindLabel("draft")).toBe("Draft");
    expect(kindLabel("research")).toBe("Research");
  });
  it("tones approvals as the most urgent", () => {
    expect(kindTone("approval")).toBe("warning");
    expect(kindTone("research")).toBe("brand");
    expect(kindTone("draft")).toBe("muted");
  });
});
