import { describe, expect, it } from "vitest";
import {
  API_ENDPOINTS,
  BOARD_COLUMN,
  FUNNEL_STAGES,
  JOB_STATE,
  QUERY_KEYS,
  ROUTES,
} from "./constants";

describe("ROUTES", () => {
  it("has a hash-router path per screen", () => {
    expect(ROUTES.board).toBe("/board");
    expect(ROUTES.runs).toBe("/runs");
    expect(ROUTES.analytics).toBe("/analytics");
    expect(ROUTES.settings).toBe("/settings");
  });

  it("builds job-detail paths with the id", () => {
    expect(ROUTES.jobDetail(42)).toBe("/board/42");
    expect(ROUTES.jobDetail("abc")).toBe("/board/abc");
  });
});

describe("API_ENDPOINTS", () => {
  it("builds per-job endpoints with the id", () => {
    expect(API_ENDPOINTS.job(7)).toBe("/api/jobs/7");
    expect(API_ENDPOINTS.jobTailor(7)).toBe("/api/jobs/7/tailor");
    expect(API_ENDPOINTS.jobCover(7)).toBe("/api/jobs/7/cover");
    expect(API_ENDPOINTS.jobDrafts(7)).toBe("/api/jobs/7/drafts");
  });

  it("exposes the profile-by-id endpoint", () => {
    expect(API_ENDPOINTS.profile(3)).toBe("/api/search-profiles/3");
  });
});

describe("QUERY_KEYS", () => {
  it("uses arrays for single-resource keys", () => {
    expect(QUERY_KEYS.board).toEqual(["board"]);
    expect(QUERY_KEYS.runs).toEqual(["runs"]);
    expect(QUERY_KEYS.profiles).toEqual(["profiles"]);
    expect(QUERY_KEYS.analytics).toEqual(["analytics"]);
  });

  it("uses [resource, id] for per-job keys", () => {
    expect(QUERY_KEYS.job(42)).toEqual(["job", 42]);
    expect(QUERY_KEYS.drafts(42)).toEqual(["drafts", 42]);
  });
});

describe("JOB_STATE mirror", () => {
  it("contains every state the Board buckets into a column", () => {
    // Sanity: if the backend adds a state we must add it here too.
    const known = new Set(Object.values(JOB_STATE));
    for (const stage of FUNNEL_STAGES) expect(known.has(stage)).toBe(true);
  });
});

describe("BOARD_COLUMN", () => {
  it("has a stable key per Kanban column", () => {
    expect(BOARD_COLUMN.discovered).toBe("discovered");
    expect(BOARD_COLUMN.closed).toBe("closed");
  });
});
