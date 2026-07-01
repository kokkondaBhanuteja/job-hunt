import { useQuery } from "@tanstack/react-query";
import { api, type BoardJob } from "../api";
import { scoreClass } from "../format";
import { jobIdOf, navigate, useHashRoute } from "../router";
import { JobPanel } from "./JobPanel";

// Kanban columns mapped from jobs.state (kept in sync with job_hunt/states.py).
const COLUMNS: { key: string; label: string; states: string[] }[] = [
  { key: "discovered", label: "Discovered", states: ["discovered", "enriched"] },
  { key: "scored", label: "Scored", states: ["scored"] },
  { key: "pursuing", label: "Pursuing", states: ["tailoring_ready", "drafted", "review_pending"] },
  { key: "applied", label: "Applied", states: ["applied"] },
  { key: "interview", label: "Interview", states: ["oa", "interview", "hr"] },
  { key: "offer", label: "Offer", states: ["offer"] },
  { key: "closed", label: "Closed", states: ["rejected", "archived", "withdrawn", "deferred"] },
];

function columnFor(state: string): string {
  return COLUMNS.find((c) => c.states.includes(state))?.key ?? "discovered";
}

export function Board() {
  const board = useQuery({ queryKey: ["board"], queryFn: api.board });
  const selected = jobIdOf(useHashRoute()); // deep-linkable: #/board/<id>

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
                <button className="card" key={job.id} onClick={() => navigate(`/board/${job.id}`)}>
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
      {selected != null && <JobPanel jobId={selected} onClose={() => navigate("/board")} />}
    </div>
  );
}
