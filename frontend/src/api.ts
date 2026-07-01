// Typed client for the job-hunt FastAPI. Base URL + bearer token live in
// localStorage (set on the Settings page).

export function getApiBase(): string {
  return localStorage.getItem("apiBase") || "http://127.0.0.1:8000";
}
export function getToken(): string {
  return localStorage.getItem("apiToken") || "";
}
export function setConfig(base: string, token: string) {
  localStorage.setItem("apiBase", base);
  localStorage.setItem("apiToken", token);
}

async function req<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const res = await fetch(getApiBase() + path, {
    ...opts,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${getToken()}`,
      ...(opts.headers || {}),
    },
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`${res.status}: ${detail}`);
  }
  return (await res.json()) as T;
}

export interface Health {
  status: string;
  datastore: string;
  sources: string[];
  llm: Record<string, { provider: string; model: string }>;
}
export interface BoardJob {
  id: number;
  title: string;
  company: string;
  location: string | null;
  state: string;
  apply_url: string;
  best_score: number | null;
}
export interface ScoreRow {
  variant: string;
  fit_score: number;
  confidence: number | null;
  reasoning: string;
}
export interface JobDetail {
  job: Record<string, unknown> & {
    id: number;
    title: string;
    company: string;
    location: string | null;
    description: string | null;
    apply_url: string;
    state: string;
    status: string;
  };
  scores: ScoreRow[];
}
export interface Run {
  id: number;
  status: string;
  jobs_found: number;
  jobs_new: number;
  started_at: string | null;
  finished_at: string | null;
  log: string;
}
export interface Profile {
  id: number;
  name: string;
  keywords: string;
  location: string;
  pages: number;
  enabled: number | boolean;
}
export interface TailorResult {
  job_id: number;
  variant: string | null;
  content: string;
}
export interface CoverResult {
  job_id: number;
  draft_id: number;
  kind: string;
  body: string;
}
export interface Draft {
  id: number;
  kind: string;
  body: string;
  status: string;
  created_at: string;
}
export interface ReviewIssue {
  severity: string;
  field?: string;
  message: string;
}
export interface ReviewResult {
  job_id: number;
  ats: string;
  variant: string | null;
  ready: boolean;
  issues: ReviewIssue[];
}
export interface Analytics {
  jobs_by_state: { state: string; n: number }[];
  jobs_by_source: { source: string; n: number }[];
  funnel: { stage: string; n: number }[];
  source_effectiveness: { source: string; applied: number }[];
  llm_by_task: { task: string; calls: number; cost: number }[];
  variant_performance: {
    variant: string;
    applications: number;
    interviews: number;
    offers: number;
    rejections: number;
  }[];
  llm_cost: { calls: number; cost: number; tokens: number };
}

export const api = {
  health: () => fetch(getApiBase() + "/health").then((r) => r.json() as Promise<Health>),
  board: () => req<BoardJob[]>("/api/board"),
  job: (id: number) => req<JobDetail>(`/api/jobs/${id}`),
  runs: () => req<Run[]>("/api/runs?limit=20"),
  discover: () => req<{ started: boolean }>("/api/discover", { method: "POST" }),
  score: () => req<{ started: boolean }>("/api/score", { method: "POST" }),
  profiles: () => req<Profile[]>("/api/search-profiles"),
  addProfile: (b: { name: string; keywords: string; location: string; pages: number }) =>
    req<{ id: number }>("/api/search-profiles", { method: "POST", body: JSON.stringify(b) }),
  setProfileEnabled: (id: number, enabled: boolean) =>
    req(`/api/search-profiles/${id}`, { method: "PATCH", body: JSON.stringify({ enabled }) }),
  logApplication: (b: { job_id: number; variant_slug: string; cover_letter: string; status?: string }) =>
    req("/api/applications", { method: "POST", body: JSON.stringify(b) }),
  tailor: (id: number) => req<TailorResult>(`/api/jobs/${id}/tailor`, { method: "POST" }),
  cover: (id: number) => req<CoverResult>(`/api/jobs/${id}/cover`, { method: "POST" }),
  drafts: (id: number) => req<Draft[]>(`/api/jobs/${id}/drafts`),
  review: (id: number, cover_letter = "") =>
    req<ReviewResult>("/api/apply/review", {
      method: "POST",
      body: JSON.stringify({ job_id: id, cover_letter, answers: {} }),
    }),
  analytics: () => req<Analytics>("/api/analytics"),
};
