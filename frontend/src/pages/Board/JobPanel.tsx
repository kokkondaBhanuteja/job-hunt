import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { EmptyView } from "../../components/EmptyView";
import { ErrorView } from "../../components/ErrorView";
import { LoadingView } from "../../components/LoadingView";
import { api, type JobDetail, type ScoreRow } from "../../lib/api";
import { QUERY_KEYS } from "../../lib/constants";
import { scoreClass } from "../../lib/format";
import { JobActions } from "./JobActions";

/** The slide-in job detail. Composed from small pieces so this file stays readable. */
export function JobPanel({ jobId, onClose }: { jobId: number; onClose: () => void }) {
  const detail = useQuery({ queryKey: QUERY_KEYS.job(jobId), queryFn: () => api.job(jobId) });

  return (
    <aside className="panel">
      <div className="panel-head">
        <button className="close" onClick={onClose}>
          ✕
        </button>
      </div>
      {!detail.data ? (
        <LoadingView />
      ) : (
        <div className="panel-body">
          <JobHeader job={detail.data.job} />
          <h3>Scores</h3>
          <ScoreList scores={detail.data.scores} />
          <h3>Job description</h3>
          <pre className="jd">{detail.data.job.description || "(no description captured yet)"}</pre>
          <JobActions jobId={jobId} />
          <h3>Log application</h3>
          <LogApplicationForm jobId={jobId} variantOptions={detail.data.scores.map((s) => s.variant)} />
        </div>
      )}
    </aside>
  );
}

function JobHeader({ job }: { job: JobDetail["job"] }) {
  return (
    <>
      <h2>{job.title}</h2>
      <div className="sub">
        {job.company} · {job.location ?? "—"}
      </div>
      <div className="chips">
        <span className="chip">{job.state}</span>
        <a className="chip link" href={job.apply_url} target="_blank" rel="noreferrer">
          open ↗
        </a>
      </div>
    </>
  );
}

function ScoreList({ scores }: { scores: ScoreRow[] }) {
  if (scores.length === 0) return <EmptyView>Not scored yet.</EmptyView>;
  return (
    <>
      {scores.map((s) => (
        <div className="scorebox" key={s.variant}>
          <div className="scorebox-head">
            <b>{s.variant}</b>
            <span className={scoreClass(s.fit_score)}>{s.fit_score}</span>
            {s.confidence != null && <span className="conf">conf {s.confidence}</span>}
          </div>
          <p className="reason">{s.reasoning}</p>
        </div>
      ))}
    </>
  );
}

function LogApplicationForm({ jobId, variantOptions }: { jobId: number; variantOptions: string[] }) {
  const qc = useQueryClient();
  const [variant, setVariant] = useState("");
  const [cover, setCover] = useState("");
  const active = variant || variantOptions[0] || "";

  const apply = useMutation({
    mutationFn: () =>
      api.logApplication({ job_id: jobId, variant_slug: active, cover_letter: cover }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QUERY_KEYS.board });
      qc.invalidateQueries({ queryKey: QUERY_KEYS.job(jobId) });
    },
  });

  return (
    <div className="form">
      <select value={active} onChange={(e) => setVariant(e.target.value)}>
        {variantOptions.length === 0 && <option value="">(no variant)</option>}
        {variantOptions.map((v) => (
          <option key={v} value={v}>
            {v}
          </option>
        ))}
      </select>
      <textarea
        placeholder="Cover letter / notes…"
        value={cover}
        onChange={(e) => setCover(e.target.value)}
      />
      <button className="primary" disabled={!active || apply.isPending} onClick={() => apply.mutate()}>
        {apply.isPending ? "Saving…" : "Mark applied"}
      </button>
      {apply.isError && <ErrorView error={apply.error} />}
      {apply.isSuccess && <div className="ok-msg">Logged ✓</div>}
    </div>
  );
}
