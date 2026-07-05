import { useQuery } from "@tanstack/react-query";
import { ChevronRight } from "lucide-react";
import { EmptyView } from "@/components/EmptyView";
import { ErrorView } from "@/components/ErrorView";
import { LoadingView } from "@/components/LoadingView";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { FUNNEL_STAGES, QUERY_KEYS } from "@/lib/constants";
import { SkillGapCard } from "./SkillGapCard";

export function Analytics() {
  const q = useQuery({ queryKey: QUERY_KEYS.analytics, queryFn: api.analytics });

  if (q.isError) return <ErrorView error={q.error} />;
  if (!q.data) return <LoadingView label="Loading analytics…" rows={5} />;
  const d = q.data;
  const funnel = Object.fromEntries(d.funnel.map((f) => [f.stage, f.n]));

  return (
    <div className="space-y-5">
      <h1 className="text-xl font-semibold tracking-tight">Analytics</h1>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Application funnel</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-6">
            {FUNNEL_STAGES.map((stage, i) => (
              <div
                key={stage}
                className="relative rounded-lg border border-border bg-secondary/40 p-4 text-center"
              >
                <div className="text-2xl font-semibold tabular-nums text-primary">
                  {funnel[stage] ?? 0}
                </div>
                <div className="mt-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                  {stage}
                </div>
                {i < FUNNEL_STAGES.length - 1 && (
                  <ChevronRight
                    className="absolute -right-3 top-1/2 hidden h-4 w-4 -translate-y-1/2 text-border md:block"
                    aria-hidden
                  />
                )}
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">LLM cost</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <Metric label="calls" value={d.llm_cost.calls} />
            <Metric label="tokens" value={d.llm_cost.tokens} />
            <Metric label="cost (USD)" value={`$${Number(d.llm_cost.cost).toFixed(4)}`} />
          </div>
          <MiniTable
            title="By task"
            rows={d.llm_by_task.map((t) => [t.task, `${t.calls} calls`, `$${Number(t.cost).toFixed(4)}`])}
          />
        </CardContent>
      </Card>

      <SkillGapCard />

      <div className="grid gap-5 md:grid-cols-2">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Jobs by state</CardTitle>
          </CardHeader>
          <CardContent>
            <MiniTable rows={d.jobs_by_state.map((s) => [s.state, String(s.n)])} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Jobs by source</CardTitle>
          </CardHeader>
          <CardContent>
            <MiniTable rows={d.jobs_by_source.map((s) => [s.source, String(s.n)])} />
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-5 md:grid-cols-2">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Source effectiveness (applied)</CardTitle>
          </CardHeader>
          <CardContent>
            <MiniTable rows={d.source_effectiveness.map((s) => [s.source, String(s.applied)])} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Resume variant performance</CardTitle>
          </CardHeader>
          <CardContent>
            <MiniTable
              rows={d.variant_performance.map((v) => [
                v.variant,
                `${v.applications} app · ${v.interviews} intv · ${v.offers} off`,
              ])}
            />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-lg border border-border bg-secondary/40 px-4 py-3">
      <div className="text-xl font-semibold tabular-nums">{value}</div>
      <div className="mt-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
    </div>
  );
}

function MiniTable({ title, rows }: { title?: string; rows: string[][] }) {
  return (
    <div className="space-y-1">
      {title && (
        <div className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          {title}
        </div>
      )}
      {rows.length === 0 && <EmptyView icon={null}>no data yet</EmptyView>}
      <div className="divide-y divide-border">
        {rows.map((cells, i) => (
          <div key={i} className="flex justify-between gap-3 py-1.5 text-sm">
            {cells.map((c, j) => (
              <span key={j} className={j === 0 ? "text-foreground" : "text-muted-foreground tabular-nums"}>
                {c}
              </span>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
