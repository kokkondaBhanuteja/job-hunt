import { RefreshCw, WifiOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { SCREEN } from "@/lib/constants";
import { Link } from "@/lib/router";

interface Props {
  onRetry: () => void;
  retrying?: boolean;
}

/**
 * Full-panel state shown when the backend health probe is failing.
 * One friendly message per screen instead of a red alert on every card.
 */
export function OfflineView({ onRetry, retrying }: Props) {
  return (
    <div className="mx-auto max-w-lg pt-6 md:pt-12">
      <Card>
        <CardContent className="flex flex-col items-center gap-3 p-8 text-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-destructive/10 text-destructive">
            <WifiOff className="h-6 w-6" />
          </div>
          <h2 className="text-lg font-semibold tracking-tight">Can’t reach the API</h2>
          <p className="max-w-sm text-sm text-muted-foreground">
            The job-hunt backend isn’t answering. Make sure it’s running, then try again.
            You can update the API base under Settings if it moved.
          </p>
          <div className="mt-2 flex flex-wrap items-center justify-center gap-2">
            <Button onClick={onRetry} disabled={retrying}>
              <RefreshCw className={"h-4 w-4 " + (retrying ? "animate-spin" : "")} />
              {retrying ? "Retrying…" : "Try again"}
            </Button>
            <Link
              className="inline-flex h-9 items-center rounded-md border border-border bg-background px-3 text-sm hover:bg-secondary"
              to={`/${SCREEN.settings}`}
            >
              Open Settings
            </Link>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
