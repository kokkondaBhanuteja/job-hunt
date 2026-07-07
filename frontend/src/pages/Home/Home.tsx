import { useQuery } from "@tanstack/react-query";
import { ErrorView } from "@/components/ErrorView";
import { LoadingView } from "@/components/LoadingView";
import { api } from "@/lib/api";
import { QUERY_KEYS } from "@/lib/constants";
import { PipelineStats } from "./PipelineStats";
import { SetupChecklist } from "./SetupChecklist";

export function Home() {
  const q = useQuery({ queryKey: QUERY_KEYS.home, queryFn: api.home });

  if (q.isError) return <ErrorView error={q.error} />;
  if (!q.data) return <LoadingView label="Loading…" rows={4} />;

  return (
    <div className="space-y-5">
      <h1 className="text-xl font-semibold tracking-tight">Home</h1>
      <p className="text-sm text-muted-foreground">
        Set these up once, then review and apply from the Board.
      </p>
      <SetupChecklist setup={q.data.setup} />
      <PipelineStats activity={q.data.activity} />
    </div>
  );
}
