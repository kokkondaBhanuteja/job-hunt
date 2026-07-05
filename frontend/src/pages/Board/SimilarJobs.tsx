import { useQuery } from "@tanstack/react-query";
import { ErrorView } from "@/components/ErrorView";
import { api, type SimilarResult, type SimilarSuccessful } from "@/lib/api";
import { QUERY_KEYS } from "@/lib/constants";

// Type guard: discriminates the {error} shape from the full SimilarSuccessful shape.
// Exported so the guard logic can be tested in node env without a DOM.
export function isErrorResult(data: SimilarResult): data is { error: string } {
  return "error" in data;
}

function SimilarList({ data }: { data: SimilarSuccessful }) {
  return (
    <section className="space-y-2 rounded-md border border-border bg-muted/40 p-3">
      <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
        Resembles {data.count} past job{data.count !== 1 ? "s" : ""} that reached interview+
      </p>
      <ul className="space-y-1">
        {data.matches.map((m) => (
          <li key={m.job_id} className="flex flex-wrap gap-x-1 text-xs">
            <span className="font-medium text-foreground">{m.title}</span>
            <span className="text-muted-foreground">·</span>
            <span className="text-foreground/80">{m.company}</span>
            <span className="text-muted-foreground">·</span>
            <span className="text-muted-foreground capitalize">{m.state}</span>
            <span className="text-muted-foreground">·</span>
            <span className="text-muted-foreground">{m.distance.toFixed(3)}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

/**
 * Optional callout showing past jobs that vectorially resemble this one and
 * reached interview stage. Renders nothing (not an error) when the backend
 * returns {error} — that's the expected response on sqlite or when the job has
 * no embedding yet. ErrorView is reserved for genuine network failures.
 */
export function SimilarJobs({ jobId }: { jobId: number }) {
  const q = useQuery({
    queryKey: QUERY_KEYS.similar(jobId),
    queryFn: () => api.similarSuccessful(jobId),
  });

  // Supplemental callout — suppress loading state to avoid layout shift.
  if (q.isLoading || !q.data) return null;
  if (q.isError) return <ErrorView error={q.error} title="Couldn't load similar jobs" />;

  // sqlite / no-embedding returns {error}; count===0 means no match — both render nothing.
  if (isErrorResult(q.data) || q.data.count === 0) return null;

  return <SimilarList data={q.data} />;
}
