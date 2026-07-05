import { describe, expect, it } from "vitest";
import { isErrorResult } from "./SimilarJobs";
import type { SimilarResult } from "@/lib/api";

describe("isErrorResult", () => {
  it("returns true when the result has an error field", () => {
    const result: SimilarResult = { error: "postgres only" };
    expect(isErrorResult(result)).toBe(true);
  });

  it("returns false for a valid SimilarSuccessful response", () => {
    const result: SimilarResult = {
      job_id: 1,
      matches: [{ job_id: 2, title: "SWE", company: "Acme", distance: 0.12, state: "interview" }],
      count: 1,
    };
    expect(isErrorResult(result)).toBe(false);
  });

  it("returns false for a zero-match response (still a valid shape)", () => {
    const result: SimilarResult = { job_id: 1, matches: [], count: 0 };
    expect(isErrorResult(result)).toBe(false);
  });
});
