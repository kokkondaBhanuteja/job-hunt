import { describe, expect, it } from "vitest";
import { friendlyError, isOfflineError } from "./friendlyError";

describe("friendlyError", () => {
  it("translates a TypeError: Failed to fetch into a friendly network message", () => {
    const e = new TypeError("Failed to fetch");
    const f = friendlyError(e);
    expect(f.title).toBe("Can’t reach the server");
    expect(f.message).not.toMatch(/Failed to fetch/);
    expect(f.hint).toMatch(/Settings/);
  });

  it("recognises 401 / 403 as sign-in problems", () => {
    // req() in api.ts throws "<status>: <detail>" — that's the shape we scan.
    expect(friendlyError(new Error("401: Unauthorized")).title).toBe("Not signed in");
    expect(friendlyError({ status: 403, message: "" }).title).toBe("Not signed in");
  });

  it("does NOT extract a status from an unrelated 3-digit number in the message", () => {
    // "took 500 ms" contains "500" but no "<status>:" prefix — must fall back
    // to the generic bucket, not "Server hiccup".
    expect(friendlyError(new Error("took 500 ms")).title).toBe("Something went wrong");
    expect(friendlyError(new Error("job 42901 not found")).title).toBe("Something went wrong");
  });

  it("catches 5xx as server issues", () => {
    const f = friendlyError({ status: 503, message: "Service Unavailable" });
    expect(f.title).toBe("Server hiccup");
    expect(f.message).toMatch(/not something you did wrong/);
  });

  it("catches 429 as rate limit", () => {
    expect(friendlyError({ status: 429, message: "" }).title).toBe("Too many requests");
  });

  it("falls back to a generic-but-friendly message", () => {
    const f = friendlyError(new Error("weird internal thing"));
    expect(f.title).toBe("Something went wrong");
    expect(f.message).not.toMatch(/weird internal thing/);
    expect(f.technical).toBe("weird internal thing");
  });
});

describe("isOfflineError", () => {
  it("returns true for TypeError: Failed to fetch", () => {
    expect(isOfflineError(new TypeError("Failed to fetch"))).toBe(true);
  });

  it("returns false for a 500", () => {
    expect(isOfflineError({ status: 500, message: "server error" })).toBe(false);
  });
});
