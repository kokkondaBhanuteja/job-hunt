import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { QUERY_KEYS } from "@/lib/constants";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

// Read-only connection status. The API base is fixed (same-origin — nginx proxies /api), so
// there is nothing for the user to configure; an editable base only ever broke things.
export function ConnectionPanel() {
  const health = useQuery({ queryKey: QUERY_KEYS.health, queryFn: api.health, retry: false });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Connection</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <p className="text-xs text-muted-foreground">
          The UI talks to the API on the same origin — nginx proxies <code>/api</code> and injects
          auth. Nothing to configure here.
        </p>
        {health.isSuccess ? (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <Badge className="bg-emerald-500/15 text-emerald-600 hover:bg-emerald-500/20 dark:text-emerald-400">
                connected
              </Badge>
              <span className="font-mono text-xs text-muted-foreground">
                datastore={health.data.datastore} · sources={health.data.sources.join(",")}
              </span>
            </div>
            <div className="space-y-0.5 font-mono text-[11px] text-muted-foreground">
              {Object.entries(health.data.llm).map(([task, cfg]) => (
                <div key={task}>
                  {task}: {cfg.provider}/{cfg.model}
                </div>
              ))}
            </div>
          </>
        ) : (
          <Badge variant="destructive">not connected</Badge>
        )}
      </CardContent>
    </Card>
  );
}
