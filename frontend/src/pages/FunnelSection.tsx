import { EmptyView } from "@/components/EmptyView";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { FunnelMetrics, SourceEffectivenessByOutcome } from "@/lib/api";
import { pct } from "@/lib/format";

interface Props {
  funnel_metrics: FunnelMetrics;
}

export function FunnelSection({ funnel_metrics: fm }: Props) {
  if (fm.applications_total === 0) {
    return (
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Funnel metrics</CardTitle>
        </CardHeader>
        <CardContent>
          <EmptyView>No applications recorded yet</EmptyView>
        </CardContent>
      </Card>
    );
  }

  return (
    <>
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Funnel metrics</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <RateCell label="Interview rate" value={pct(fm.interview_rate)} />
            <RateCell label="Offer rate" value={pct(fm.offer_rate)} />
            <RateCell label="Response rate" value={pct(fm.response_rate)} />
            <RateCell
              label="Days to interview"
              value={fm.time_to_interview_days !== null ? `${fm.time_to_interview_days.toFixed(1)}` : "—"}
            />
          </div>
          <div className="space-y-1">
            <p className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
              Stage conversion
            </p>
            <div className="divide-y divide-border">
              <ConvRow label="Applied → Interview" value={pct(fm.stage_conversion.applied_to_interview)} />
              <ConvRow label="Interview → Offer" value={pct(fm.stage_conversion.interview_to_offer)} />
            </div>
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Source effectiveness by outcome</CardTitle>
        </CardHeader>
        <CardContent>
          <SourceTable rows={fm.source_effectiveness_by_outcome} />
        </CardContent>
      </Card>
    </>
  );
}

function RateCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border bg-secondary/40 px-4 py-3">
      <div className="text-xl font-semibold tabular-nums">{value}</div>
      <div className="mt-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
    </div>
  );
}

function ConvRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-3 py-1.5 text-sm">
      <span className="text-foreground">{label}</span>
      <span className="tabular-nums text-muted-foreground">{value}</span>
    </div>
  );
}

function SourceTable({ rows }: { rows: SourceEffectivenessByOutcome[] }) {
  if (rows.length === 0) return <EmptyView icon={null}>No source data yet</EmptyView>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
            <th className="py-2 pr-4 text-left">Source</th>
            <th className="py-2 pr-4 text-right">Applied</th>
            <th className="py-2 pr-4 text-right">Interviews</th>
            <th className="py-2 pr-4 text-right">Offers</th>
            <th className="py-2 text-right">Int. rate</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {rows.map((r) => (
            <tr key={r.source}>
              <td className="py-1.5 pr-4 text-foreground">{r.source}</td>
              <td className="py-1.5 pr-4 text-right tabular-nums text-muted-foreground">{r.applied}</td>
              <td className="py-1.5 pr-4 text-right tabular-nums text-muted-foreground">{r.interviews}</td>
              <td className="py-1.5 pr-4 text-right tabular-nums text-muted-foreground">{r.offers}</td>
              <td className="py-1.5 text-right tabular-nums text-muted-foreground">{pct(r.interview_rate)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
