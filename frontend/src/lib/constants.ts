// Central catalog of strings, keys, and thresholds shared across the app.
// Mirrors relevant backend enums (job_hunt/enums.py, job_hunt/api/app.py).

/** Hash-router paths. Prefix with `#` when assigning to window.location. */
export const ROUTES = {
  board: "/board",
  runs: "/runs",
  analytics: "/analytics",
  settings: "/settings",
  jobDetail: (id: number | string) => `/board/${id}`,
} as const;

/** Screen identifiers (first segment of the hash route). */
export const SCREEN = {
  board: "board",
  runs: "runs",
  analytics: "analytics",
  settings: "settings",
} as const;
export type Screen = (typeof SCREEN)[keyof typeof SCREEN];

/** REST endpoints on the FastAPI backend. */
export const API_ENDPOINTS = {
  health: "/health",
  ping: "/api/runs?limit=1",
  board: "/api/board",
  job: (id: number) => `/api/jobs/${id}`,
  jobTailor: (id: number) => `/api/jobs/${id}/tailor`,
  jobCover: (id: number) => `/api/jobs/${id}/cover`,
  jobDrafts: (id: number) => `/api/jobs/${id}/drafts`,
  runsList: "/api/runs?limit=20",
  discover: "/api/discover",
  score: "/api/score",
  profiles: "/api/search-profiles",
  profile: (id: number) => `/api/search-profiles/${id}`,
  applyReview: "/api/apply/review",
  applications: "/api/applications",
  analytics: "/api/analytics",
  context: "/api/context",
  applicant: "/api/applicant",
  jobFill: (id: number) => `/api/jobs/${id}/fill`,
} as const;

/** TanStack Query keys — `[resource, ...params]`. Always arrays. */
export const QUERY_KEYS = {
  health: ["health"] as const,
  auth: ["auth"] as const,
  board: ["board"] as const,
  job: (id: number) => ["job", id] as const,
  drafts: (id: number) => ["drafts", id] as const,
  runs: ["runs"] as const,
  profiles: ["profiles"] as const,
  analytics: ["analytics"] as const,
  context: ["context"] as const,
  applicant: ["applicant"] as const,
} as const;

/** Score → color-class thresholds (used in format.ts). */
export const SCORE_THRESHOLDS = {
  strong: 85,
  solid: 70,
} as const;

/** localStorage keys for connection config. */
export const STORAGE_KEYS = {
  apiBase: "apiBase",
  apiToken: "apiToken",
} as const;

/** Default API base URL when localStorage is empty. */
export const DEFAULT_API_BASE = "http://127.0.0.1:8000";

/** How often the Runs table re-polls (ms). */
export const RUNS_POLL_MS = 4000;

/** Mirror of job_hunt/enums.py::JobState — the vocabulary the backend uses. */
export const JOB_STATE = {
  DISCOVERED: "discovered",
  ENRICHED: "enriched",
  SCORED: "scored",
  ARCHIVED: "archived",
  TAILORING_READY: "tailoring_ready",
  DRAFTED: "drafted",
  REVIEW_PENDING: "review_pending",
  APPLIED: "applied",
  OA: "oa",
  INTERVIEW: "interview",
  HR: "hr",
  OFFER: "offer",
  REJECTED: "rejected",
  DEFERRED: "deferred",
  WITHDRAWN: "withdrawn",
} as const;
export type JobStateValue = (typeof JOB_STATE)[keyof typeof JOB_STATE];

/** Kanban column identifiers shown on the Board. */
export const BOARD_COLUMN = {
  discovered: "discovered",
  scored: "scored",
  pursuing: "pursuing",
  applied: "applied",
  interview: "interview",
  offer: "offer",
  closed: "closed",
} as const;
export type BoardColumn = (typeof BOARD_COLUMN)[keyof typeof BOARD_COLUMN];

/** Application funnel stages (order matters — drives the Analytics view). */
export const FUNNEL_STAGES = [
  "applied",
  "oa",
  "interview",
  "hr",
  "offer",
  "rejected",
] as const;
