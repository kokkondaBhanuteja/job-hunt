import { SCORE_THRESHOLDS } from "./constants";

export type ScoreVariant = "strong" | "solid" | "weak" | "none";

/** Bucket a numeric fit score into a semantic tier. */
export function scoreVariant(score: number | null): ScoreVariant {
  if (score == null) return "none";
  if (score >= SCORE_THRESHOLDS.strong) return "strong";
  if (score >= SCORE_THRESHOLDS.solid) return "solid";
  return "weak";
}

/** Legacy CSS class helper — kept for tests and any un-migrated call sites. */
export function scoreClass(score: number | null): string {
  return `score ${scoreVariant(score)}`;
}
