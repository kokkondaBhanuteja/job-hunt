import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { EmptyView } from "../../components/EmptyView";
import { ErrorView } from "../../components/ErrorView";
import { api, type ReviewResult } from "../../lib/api";
import { QUERY_KEYS } from "../../lib/constants";

export function JobActions({ jobId }: { jobId: number }) {
  const qc = useQueryClient();
  const drafts = useQuery({ queryKey: QUERY_KEYS.drafts(jobId), queryFn: () => api.drafts(jobId) });

  const tailor = useMutation({ mutationFn: () => api.tailor(jobId) });
  const cover = useMutation({
    mutationFn: () => api.cover(jobId),
    onSuccess: () => qc.invalidateQueries({ queryKey: QUERY_KEYS.drafts(jobId) }),
  });
  const review = useMutation({ mutationFn: () => api.review(jobId, cover.data?.body ?? "") });
  // fillJob returns {started: true} and opens a browser server-side — no fill summary.
  const fill = useMutation({ mutationFn: () => api.fillJob(jobId) });

  return (
    <div className="actions-block">
      <h3>Prepare application</h3>
      <div className="btn-row">
        <button className="primary" onClick={() => tailor.mutate()} disabled={tailor.isPending}>
          {tailor.isPending ? "Tailoring…" : "Tailor resume"}
        </button>
        <button onClick={() => cover.mutate()} disabled={cover.isPending}>
          {cover.isPending ? "Writing…" : "Cover letter"}
        </button>
        <button onClick={() => review.mutate()} disabled={review.isPending}>
          {review.isPending ? "Reviewing…" : "AI review"}
        </button>
        <button onClick={() => fill.mutate()} disabled={fill.isPending}>
          {fill.isPending ? "Launching…" : "Auto-fill form"}
        </button>
      </div>

      {(tailor.error || cover.error || review.error || fill.error) && (
        <ErrorView error={tailor.error || cover.error || review.error || fill.error} />
      )}
      {fill.isSuccess && (
        <div className="ok-msg">Opening browser — review &amp; submit there.</div>
      )}
      {tailor.data && (
        <details className="draft-box">
          <summary>Tailored resume · {tailor.data.variant}</summary>
          <pre className="jd">{tailor.data.content}</pre>
        </details>
      )}
      {cover.data && (
        <details className="draft-box" open>
          <summary>Cover letter</summary>
          <pre className="jd">{cover.data.body}</pre>
        </details>
      )}
      {review.data && <ReviewVerdict result={review.data} />}
      {(drafts.data ?? []).length > 0 && (
        <div className="muted small">{drafts.data!.length} saved draft(s)</div>
      )}
    </div>
  );
}

function ReviewVerdict({ result }: { result: ReviewResult }) {
  return (
    <div className="review">
      <span className={result.ready ? "pill ok" : "pill bad"}>
        {result.ready ? "ready to submit" : "needs work"} · ATS: {result.ats}
      </span>
      <ul className="issues">
        {result.issues.map((issue, i) => (
          <li key={i} className={`issue ${issue.severity}`}>
            <b>{issue.severity}</b>
            {issue.field ? ` (${issue.field})` : ""} — {issue.message}
          </li>
        ))}
        {result.issues.length === 0 && (
          <li>
            <EmptyView>No issues flagged.</EmptyView>
          </li>
        )}
      </ul>
    </div>
  );
}
