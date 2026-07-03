import { describe, expect, it } from "vitest";
import { SCREEN } from "./constants";
import { jobIdOf, screenOf } from "./router";

describe("screenOf", () => {
  it("returns the first path segment", () => {
    expect(screenOf("/board")).toBe(SCREEN.board);
    expect(screenOf("/runs")).toBe(SCREEN.runs);
    expect(screenOf("/analytics")).toBe(SCREEN.analytics);
    expect(screenOf("/settings")).toBe(SCREEN.settings);
  });

  it("ignores trailing segments", () => {
    expect(screenOf("/board/42")).toBe(SCREEN.board);
    expect(screenOf("/board/42/anything")).toBe(SCREEN.board);
  });

  it("falls back to the board screen for an empty route", () => {
    expect(screenOf("")).toBe(SCREEN.board);
    expect(screenOf("/")).toBe(SCREEN.board);
  });
});

describe("jobIdOf", () => {
  it("extracts a numeric job id from /board/<id>", () => {
    expect(jobIdOf("/board/42")).toBe(42);
    expect(jobIdOf("/board/1")).toBe(1);
    expect(jobIdOf("/board/999999")).toBe(999999);
  });

  it("returns null when the id segment is missing", () => {
    expect(jobIdOf("/board")).toBeNull();
    expect(jobIdOf("/board/")).toBeNull();
  });

  it("returns null when the id segment is not numeric", () => {
    expect(jobIdOf("/board/foo")).toBeNull();
    expect(jobIdOf("/board/42abc")).toBeNull();
  });

  it("returns null when the first segment is not 'board'", () => {
    expect(jobIdOf("/runs/42")).toBeNull();
    expect(jobIdOf("/analytics/42")).toBeNull();
  });
});
