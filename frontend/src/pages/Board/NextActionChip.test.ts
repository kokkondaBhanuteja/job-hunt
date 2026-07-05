import { describe, expect, it } from "vitest";
import { actionVariant } from "./NextActionChip";

describe("actionVariant", () => {
  it("maps apply and follow_up to default (primary)", () => {
    expect(actionVariant("apply")).toBe("default");
    expect(actionVariant("follow_up")).toBe("default");
  });

  it("maps reply and negotiate to destructive (strong)", () => {
    expect(actionVariant("reply")).toBe("destructive");
    expect(actionVariant("negotiate")).toBe("destructive");
  });

  it("maps wait and none to secondary (muted)", () => {
    expect(actionVariant("wait")).toBe("secondary");
    expect(actionVariant("none")).toBe("secondary");
  });

  it("falls back to secondary for unknown action verbs", () => {
    expect(actionVariant("research")).toBe("secondary");
    expect(actionVariant("")).toBe("secondary");
  });
});
