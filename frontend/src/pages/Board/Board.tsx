import { useQuery } from "@tanstack/react-query";
import { ErrorView } from "../../components/ErrorView";
import { LoadingView } from "../../components/LoadingView";
import { api, type BoardJob } from "../../lib/api";
import {
  BOARD_COLUMN,
  JOB_STATE,
  QUERY_KEYS,
  ROUTES,
  type BoardColumn,
} from "../../lib/constants";
import { scoreClass } from "../../lib/format";
import { jobIdOf, navigate, useHashRoute } from "../../lib/router";
import { JobPanel } from "./JobPanel";

interface ColumnSpec {
  key: BoardColumn;
  label: string;
  states: readonly string[];
}

// Kanban columns mapped from jobs.state (kept in sync with job_hunt/enums.py::JobState).
// Exported so the bucketing logic can be tested directly.
export const COLUMNS: readonly ColumnSpec[] = [
  { key: BOARD_COLUMN.discovered, label: "Discovered", states: [JOB_STATE.DISCOVERED, JOB_STATE.ENRICHED] },
  { key: BOARD_COLUMN.scored, label: "Scored", states: [JOB_STATE.SCORED] },
  { key: BOARD_COLUMN.pursuing, label: "Pursuing", states: [JOB_STATE.TAILORING_READY, JOB_STATE.DRAFTED, JOB_STATE.REVIEW_PENDING] },
  { key: BOARD_COLUMN.applied, label: "Applied", states: [JOB_STATE.APPLIED] },
  { key: BOARD_COLUMN.interview, label: "Interview", states: [JOB_STATE.OA, JOB_STATE.INTERVIEW, JOB_STATE.HR] },
  { key: BOARD_COLUMN.offer, label: "Offer", states: [JOB_STATE.OFFER] },
  { key: BOARD_COLUMN.closed, label: "Closed", states: [JOB_STATE.REJECTED, JOB_STATE.ARCHIVED, JOB_STATE.WITHDRAWN, JOB_STATE.DEFERRED] },
];

export function columnFor(state: string): BoardColumn {
  return COLUMNS.find((c) => c.states.includes(state))?.key ?? BOARD_COLUMN.discovered;
}

export function Board() {
  const board = useQuery({ queryKey: QUERY_KEYS.board, queryFn: api.board });
  const selected = jobIdOf(useHashRoute()); // deep-linkable: #/board/<id>

  if (board.isError) return <ErrorView error={board.error} />;
  if (!board.data) return <LoadingView label="Loading board…" />;

  const byColumn: Record<BoardColumn, BoardJob[]> = {
    [BOARD_COLUMN.discovered]: [],
    [BOARD_COLUMN.scored]: [],
    [BOARD_COLUMN.pursuing]: [],
    [BOARD_COLUMN.applied]: [],
    [BOARD_COLUMN.interview]: [],
    [BOARD_COLUMN.offer]: [],
    [BOARD_COLUMN.closed]: [],
  };
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
                <button
                  className="card"
                  key={job.id}
                  onClick={() => navigate(ROUTES.jobDetail(job.id))}
                >
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
      {selected != null && (
        <JobPanel jobId={selected} onClose={() => navigate(ROUTES.board)} />
      )}
    </div>
  );
}
