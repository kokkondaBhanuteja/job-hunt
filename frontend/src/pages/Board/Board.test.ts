import { describe, expect, it } from "vitest";
import { BOARD_COLUMN, JOB_STATE } from "../../lib/constants";
import { columnFor } from "./Board";

describe("columnFor", () => {
  it("folds discovered + enriched into the Discovered column", () => {
    expect(columnFor(JOB_STATE.DISCOVERED)).toBe(BOARD_COLUMN.discovered);
    expect(columnFor(JOB_STATE.ENRICHED)).toBe(BOARD_COLUMN.discovered);
  });

  it("puts scored jobs in Scored", () => {
    expect(columnFor(JOB_STATE.SCORED)).toBe(BOARD_COLUMN.scored);
  });

  it("groups the drafting funnel into Pursuing", () => {
    expect(columnFor(JOB_STATE.TAILORING_READY)).toBe(BOARD_COLUMN.pursuing);
    expect(columnFor(JOB_STATE.DRAFTED)).toBe(BOARD_COLUMN.pursuing);
    expect(columnFor(JOB_STATE.REVIEW_PENDING)).toBe(BOARD_COLUMN.pursuing);
  });

  it("puts applied jobs in Applied", () => {
    expect(columnFor(JOB_STATE.APPLIED)).toBe(BOARD_COLUMN.applied);
  });

  it("groups OA + interview + HR into Interview", () => {
    expect(columnFor(JOB_STATE.OA)).toBe(BOARD_COLUMN.interview);
    expect(columnFor(JOB_STATE.INTERVIEW)).toBe(BOARD_COLUMN.interview);
    expect(columnFor(JOB_STATE.HR)).toBe(BOARD_COLUMN.interview);
  });

  it("puts offers in Offer", () => {
    expect(columnFor(JOB_STATE.OFFER)).toBe(BOARD_COLUMN.offer);
  });

  it("groups terminal + parked states into Closed", () => {
    expect(columnFor(JOB_STATE.REJECTED)).toBe(BOARD_COLUMN.closed);
    expect(columnFor(JOB_STATE.ARCHIVED)).toBe(BOARD_COLUMN.closed);
    expect(columnFor(JOB_STATE.WITHDRAWN)).toBe(BOARD_COLUMN.closed);
    expect(columnFor(JOB_STATE.DEFERRED)).toBe(BOARD_COLUMN.closed);
  });

  it("falls back to Discovered for unknown states (soft failure — see Board.tsx)", () => {
    expect(columnFor("negotiating")).toBe(BOARD_COLUMN.discovered);
    expect(columnFor("")).toBe(BOARD_COLUMN.discovered);
  });
});
