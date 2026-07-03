import { describe, expect, it } from "vitest";
import { SCORE_THRESHOLDS } from "./constants";
import { scoreClass } from "./format";

describe("scoreClass", () => {
  it("returns 'score none' when the score is null", () => {
    expect(scoreClass(null)).toBe("score none");
  });

  it("returns 'score strong' at and above the strong threshold", () => {
    expect(scoreClass(SCORE_THRESHOLDS.strong)).toBe("score strong");
    expect(scoreClass(SCORE_THRESHOLDS.strong + 1)).toBe("score strong");
    expect(scoreClass(100)).toBe("score strong");
  });

  it("returns 'score solid' between solid and strong thresholds", () => {
    expect(scoreClass(SCORE_THRESHOLDS.solid)).toBe("score solid");
    expect(scoreClass(SCORE_THRESHOLDS.strong - 1)).toBe("score solid");
  });

  it("returns 'score weak' below the solid threshold", () => {
    expect(scoreClass(SCORE_THRESHOLDS.solid - 1)).toBe("score weak");
    expect(scoreClass(0)).toBe("score weak");
  });
});
