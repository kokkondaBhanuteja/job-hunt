import { describe, expect, it } from "vitest";
import { paginate } from "./Pagination";

describe("paginate", () => {
  const items = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];

  it("returns the requested slice", () => {
    expect(paginate(items, 1, 3)).toEqual([1, 2, 3]);
    expect(paginate(items, 2, 3)).toEqual([4, 5, 6]);
    expect(paginate(items, 4, 3)).toEqual([10]);
  });

  it("clamps overshoots to the last page", () => {
    expect(paginate(items, 99, 3)).toEqual([10]);
  });

  it("clamps 0 or negative to page 1", () => {
    expect(paginate(items, 0, 3)).toEqual([1, 2, 3]);
    expect(paginate(items, -1, 3)).toEqual([1, 2, 3]);
  });

  it("returns empty array when input is empty", () => {
    expect(paginate([], 1, 5)).toEqual([]);
  });
});
