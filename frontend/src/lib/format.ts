// Small shared UI helpers.
import { SCORE_THRESHOLDS } from "./constants";

/** CSS class for a fit-score badge (shared by the board cards + the detail panel). */
export function scoreClass(score: number | null): string {
  if (score == null) return "score none";
  if (score >= SCORE_THRESHOLDS.strong) return "score strong";
  if (score >= SCORE_THRESHOLDS.solid) return "score solid";
  return "score weak";
}
