// Small shared UI helpers.

/** CSS class for a fit-score badge (shared by the board cards + the detail panel). */
export function scoreClass(score: number | null): string {
  if (score == null) return "score none";
  if (score >= 85) return "score strong";
  if (score >= 70) return "score solid";
  return "score weak";
}
