import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ErrorView } from "@/components/ErrorView";
import { LoadingView } from "@/components/LoadingView";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api, type ScoreExplanation } from "@/lib/api";
import { QUERY_KEYS } from "@/lib/constants";

export function ScoreExplanationSection({ jobId }: { jobId: number }) {
  const [open, setOpen] = useState(false);
  const q = useQuery({
    queryKey: QUERY_KEYS.explain(jobId),
    queryFn: () => api.explain(jobId),
    enabled: open,
  });

  return (
    <div className="space-y-3">
      <Button variant="outline" size="sm" onClick={() => setOpen((v) => !v)}>
        Why this score?
      </Button>
      {open && (
        <>
          {q.isLoading && <LoadingView />}
          {q.isError && <ErrorView error={q.error} />}
          {q.data && <ExplanationCard data={q.data} />}
        </>
      )}
    </div>
  );
}

function ExplanationCard({ data }: { data: ScoreExplanation }) {
  const title =
    data.fit_score != null ? `Why this score? · ${data.fit_score}` : "Why this score?";
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-semibold">{title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {data.matched.length > 0 && (
          <div className="space-y-1.5">
            <h3 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              Matched
            </h3>
            <ul className="space-y-1.5">
              {data.matched.map((item, i) => (
                <li key={i} className="text-sm">
                  <span className="font-medium text-primary">{"✓ "}</span>
                  <span className="font-medium">{item.requirement}</span>
                  <span className="text-muted-foreground">{" — "}{item.evidence}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
        {data.missing.length > 0 && (
          <div className="space-y-1.5">
            <h3 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              Missing
            </h3>
            <ul className="space-y-1.5">
              {data.missing.map((item, i) => (
                <li key={i} className="text-sm">
                  <span className="font-medium text-destructive">{"✗ "}</span>
                  <span className="font-medium">{item.requirement}</span>
                  <span className="text-muted-foreground">{" — "}{item.why_it_matters}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
        {data.suggestions.length > 0 && (
          <div className="space-y-1.5">
            <h3 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              Suggestions
            </h3>
            <ul className="list-disc list-inside space-y-1">
              {data.suggestions.map((s, i) => (
                <li key={i} className="text-sm text-muted-foreground">
                  {s}
                </li>
              ))}
            </ul>
          </div>
        )}
        {data.matched.length === 0 &&
          data.missing.length === 0 &&
          data.suggestions.length === 0 && (
            <p className="text-sm text-muted-foreground">No explanation data available.</p>
          )}
      </CardContent>
    </Card>
  );
}
