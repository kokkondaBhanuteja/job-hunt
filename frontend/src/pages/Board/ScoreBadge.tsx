import type { ScoreVariant } from "@/lib/format";
import { scoreVariant } from "@/lib/format";

const CLASSES: Record<ScoreVariant, string> = {
  strong:
    "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400",
  solid:
    "bg-primary/15 text-primary",
  weak:
    "bg-muted text-muted-foreground",
  none:
    "text-muted-foreground",
};

export function ScoreBadge({ score }: { score: number | null }) {
  const variant = scoreVariant(score);
  return (
    <span
      className={
        "inline-flex min-w-[28px] items-center justify-center rounded-md px-1.5 py-0.5 text-xs font-semibold tabular-nums " +
        CLASSES[variant]
      }
    >
      {score ?? "—"}
    </span>
  );
}
