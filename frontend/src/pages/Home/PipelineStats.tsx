import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { HomeActivity } from "@/lib/api";
import { ROUTES } from "@/lib/constants";
import { Link } from "@/lib/router";

interface Props {
  activity: HomeActivity;
}

interface StatTileProps {
  value: number;
  label: string;
  to: string;
}

function StatTile({ value, label, to }: StatTileProps) {
  return (
    <Link
      to={to}
      className="flex flex-col items-center gap-1 rounded-lg border border-border bg-secondary/40 p-4 text-center transition-colors hover:bg-secondary"
    >
      <span className="text-2xl font-semibold tabular-nums text-primary">{value}</span>
      <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
        {label}
      </span>
    </Link>
  );
}

export function PipelineStats({ activity }: Props) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Your pipeline</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <StatTile value={activity.new_to_review} label="New to review" to={ROUTES.board} />
          <StatTile value={activity.ready_to_apply} label="Ready to apply" to={ROUTES.board} />
          <StatTile value={activity.applications} label="Applied" to={ROUTES.board} />
        </div>
        <p className="text-xs text-muted-foreground">
          Total jobs tracked: {activity.total_jobs}
        </p>
      </CardContent>
    </Card>
  );
}
