import { useQuery } from "@tanstack/react-query";
import { ErrorView } from "@/components/ErrorView";
import { LoadingView } from "@/components/LoadingView";
import { api, type BoardJob } from "@/lib/api";
import {
  BOARD_COLUMN,
  JOB_STATE,
  QUERY_KEYS,
  ROUTES,
  type BoardColumn,
} from "@/lib/constants";
import { jobIdOf, navigate, useRoute } from "@/lib/router";
import { JobPanel } from "./JobPanel";
import { ScoreBadge } from "./ScoreBadge";

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
  const selected = jobIdOf(useRoute());

  if (board.isError) return <ErrorView error={board.error} />;
  if (!board.data) return <LoadingView label="Loading board…" rows={4} />;

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
    <div className="flex h-[calc(100dvh-3.5rem)] gap-3">
      <div className="flex flex-1 gap-3 overflow-x-auto pb-2">
        {COLUMNS.map((col) => (
          <BoardColumnView key={col.key} label={col.label} jobs={byColumn[col.key]} />
        ))}
      </div>
      {selected != null && (
        <JobPanel jobId={selected} onClose={() => navigate(ROUTES.board)} />
      )}
    </div>
  );
}

function BoardColumnView({ label, jobs }: { label: string; jobs: BoardJob[] }) {
  return (
    <div className="flex w-64 shrink-0 flex-col rounded-lg border border-border bg-card">
      <div className="flex items-center justify-between border-b border-border px-3 py-2.5">
        <span className="text-sm font-semibold">{label}</span>
        <span className="rounded-md bg-muted px-1.5 py-0.5 text-xs font-medium tabular-nums text-muted-foreground">
          {jobs.length}
        </span>
      </div>
      <div className="flex flex-col gap-2 overflow-y-auto p-2">
        {jobs.map((job) => (
          <JobCard key={job.id} job={job} />
        ))}
        {jobs.length === 0 && (
          <div className="px-2 py-6 text-center text-xs text-muted-foreground">empty</div>
        )}
      </div>
    </div>
  );
}

function JobCard({ job }: { job: BoardJob }) {
  return (
    <button
      onClick={() => navigate(ROUTES.jobDetail(job.id))}
      className="group flex w-full flex-col gap-1 rounded-md border border-border bg-background p-2.5 text-left transition-colors hover:border-primary/50 hover:bg-secondary/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <div className="flex items-center justify-between gap-2">
        <span className="truncate text-xs text-muted-foreground">{job.company}</span>
        <ScoreBadge score={job.best_score} />
      </div>
      <div className="line-clamp-2 text-[13px] font-semibold leading-snug">{job.title}</div>
      {job.location && (
        <div className="truncate text-[11px] text-muted-foreground">{job.location}</div>
      )}
    </button>
  );
}
