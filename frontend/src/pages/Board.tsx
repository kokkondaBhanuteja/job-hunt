import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type BoardJob } from "../api";
import { JobActions } from "./JobActions";

const COLUMNS: { key: string; label: string; states: string[] }[] = [
  { key: "discovered", label: "Discovered", states: ["discovered", "enriched"] },
  { key: "scored", label: "Scored", states: ["scored"] },
  { key: "opportunity", label: "Opportunity", states: ["opportunity", "tailoring_ready", "drafted", "review_pending"] },
  { key: "ready", label: "Ready to apply", states: ["ready_to_apply"] },
  { key: "applied", label: "Applied", states: ["applied"] },
  { key: "interview", label: "Interview", states: ["oa", "interview", "hr"] },
  { key: "offer", label: "Offer", states: ["offer"] },
  { key: "closed", label: "Closed", states: ["rejected", "archived", "withdrawn", "deferred"] },
];

function columnFor(state: string): string {
  return COLUMNS.find((c) => c.states.includes(state))?.key ?? "discovered";
}

function scoreClass(score: number | null): string {
  if (score == null) return "score none";
  if (score >= 85) return "score strong";
  if (score >= 70) return "score solid";
  return "score weak";
}

export function Board() {
  const [selected, setSelected] = useState<number | null>(null);
  const board = useQuery({ queryKey: ["board"], queryFn: api.board });

  if (board.isError) return <div className="banner error">{String(board.error)}</div>;
  if (!board.data) return <div className="muted">Loading board…</div>;

  const byColumn: Record<string, BoardJob[]> = {};
  for (const c of COLUMNS) byColumn[c.key] = [];
  for (const job of board.data) byColumn[columnFor(job.state)].push(job);

  return (
    <div className="board-wrap">
      <div className="board">
        {COLUMNS.map((col) => (
          <div className="column" key={col.key}>
            <div className="column-head">
              {col.label} <span className="count">{byColumn[col.key].length}</span>
            </div>
            <div className="column-body">
              {byColumn[col.key].map((job) => (
                <button className="card" key={job.id} onClick={() => setSelected(job.id)}>
                  <div className="card-top">
                    <span className="company">{job.company}</span>
                    <span className={scoreClass(job.best_score)}>{job.best_score ?? "—"}</span>
                  </div>
                  <div className="title">{job.title}</div>
                  {job.location && <div className="loc">{job.location}</div>}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
      {selected != null && <JobPanel jobId={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}

function JobPanel({ jobId, onClose }: { jobId: number; onClose: () => void }) {
  const qc = useQueryClient();
  const detail = useQuery({ queryKey: ["job", jobId], queryFn: () => api.job(jobId) });
  const [variant, setVariant] = useState("");
  const [cover, setCover] = useState("");

  const apply = useMutation({
    mutationFn: () =>
      api.logApplication({ job_id: jobId, variant_slug: variant, cover_letter: cover }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["board"] });
      qc.invalidateQueries({ queryKey: ["job", jobId] });
    },
  });

  const scores = detail.data?.scores ?? [];
  const variantOptions = scores.map((s) => s.variant);
  const activeVariant = variant || variantOptions[0] || "";

  return (
    <aside className="panel">
      <div className="panel-head">
        <button className="close" onClick={onClose}>
          ✕
        </button>
      </div>
      {!detail.data ? (
        <div className="muted">Loading…</div>
      ) : (
        <div className="panel-body">
          <h2>{detail.data.job.title}</h2>
          <div className="sub">
            {detail.data.job.company} · {detail.data.job.location ?? "—"}
          </div>
          <div className="chips">
            <span className="chip">{detail.data.job.state}</span>
            <span className="chip">{detail.data.job.status}</span>
            <a className="chip link" href={detail.data.job.apply_url} target="_blank" rel="noreferrer">
              open ↗
            </a>
          </div>

          <h3>Scores</h3>
          {scores.length === 0 && <div className="muted">Not scored yet.</div>}
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

          <h3>Job description</h3>
          <pre className="jd">{detail.data.job.description || "(no description captured yet)"}</pre>

          <JobActions jobId={jobId} />

          <h3>Log application</h3>
          <div className="form">
            <select value={activeVariant} onChange={(e) => setVariant(e.target.value)}>
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
            <button
              className="primary"
              disabled={!activeVariant || apply.isPending}
              onClick={() => apply.mutate()}
            >
              {apply.isPending ? "Saving…" : "Mark applied"}
            </button>
            {apply.isError && <div className="banner error">{String(apply.error)}</div>}
            {apply.isSuccess && <div className="ok-msg">Logged ✓</div>}
          </div>
        </div>
      )}
    </aside>
  );
}
