import { useQuery } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { QUERY_KEYS } from "@/lib/constants";

// Maps action verbs to Badge variants using shadcn token colors only.
// Exported so the mapping logic can be tested independently (node env, no DOM).
export function actionVariant(action: string): "default" | "secondary" | "destructive" | "outline" {
  if (action === "apply" || action === "follow_up") return "default";     // primary — go do it
  if (action === "reply" || action === "negotiate") return "destructive"; // strong — time-sensitive
  return "secondary"; // wait, none, or unknown → muted
}

/**
 * Supplemental decision chip shown near the top of the job detail panel.
 * Fetches /next-action and renders a colored pill with the reason as a tooltip.
 * Silent on loading/error — the chip is informational, not load-bearing content.
 */
export function NextActionChip({ jobId }: { jobId: number }) {
  const q = useQuery({
    queryKey: QUERY_KEYS.nextAction(jobId),
    queryFn: () => api.nextAction(jobId),
  });

  if (!q.data) return null;

  return (
    <Badge
      variant={actionVariant(q.data.action)}
      title={q.data.reason}
      className="cursor-default whitespace-nowrap"
    >
      Next: {q.data.action.replace(/_/g, " ")}
    </Badge>
  );
}
