// Typed client for the job-hunt FastAPI. Base URL + bearer token live in
// localStorage (set on the Settings page).

import { API_ENDPOINTS, DEFAULT_API_BASE, ROUTES, STORAGE_KEYS } from "./constants";

export function getApiBase(): string {
  return localStorage.getItem(STORAGE_KEYS.apiBase) || DEFAULT_API_BASE;
}
export function getToken(): string {
  return localStorage.getItem(STORAGE_KEYS.apiToken) || "";
}
export function setConfig(base: string, token: string) {
  localStorage.setItem(STORAGE_KEYS.apiBase, base);
  localStorage.setItem(STORAGE_KEYS.apiToken, token);
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
  if (res.status === 401) {
    // Centralized session-expiry handling: clear the bad token and bounce the
    // user to Settings. Every caller sees a consistent error and doesn't need
    // its own auth-failure branch.
    localStorage.removeItem(STORAGE_KEYS.apiToken);
    if (!window.location.hash.endsWith(ROUTES.settings)) {
      window.location.hash = ROUTES.settings;
    }
    throw new Error("401: session expired — set your API token in Settings");
  }
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
// Mirrors backend dto.UserContext.
export interface UserContext {
  content: string | null;
  format: string | null;
  updated_at: string | null;
}
// Mirrors backend dto.Applicant.
export interface Applicant {
  first_name: string | null;
  last_name: string | null;
  email: string | null;
  phone: string | null;
  location: string | null;
  linkedin_url: string | null;
  github_url: string | null;
  portfolio_url: string | null;
  work_authorization: string | null;
  needs_sponsorship: boolean | null;
  willing_to_relocate: boolean | null;
  notice_period: string | null;
  expected_ctc: string | null;
  current_ctc: string | null;
  years_experience: string | null;
  referral_source: string | null;
  extra: string | null;
  updated_at: string | null;
}
// Mirrors backend dto.EmailSummary.
export interface EmailSummary {
  id: number;
  from_addr: string | null;
  from_name: string | null;
  subject: string | null;
  received_at: string | null;
  category: string | null;
  action_state: string | null;
  job_id: number | null;
}
// Mirrors backend dto.EmailDetail.
export interface EmailDetail {
  id: number;
  mailbox: string | null;
  uid: number | null;
  message_id: string | null;
  from_addr: string | null;
  from_name: string | null;
  subject: string | null;
  received_at: string | null;
  snippet: string | null;
  category: string | null;
  extracted: string | null;
  company_id: number | null;
  job_id: number | null;
  application_id: number | null;
  action_state: string | null;
  structured_at: string | null;
  created_at: string | null;
}
// Mirrors backend dto.EmailActionProposal.
export interface EmailActionProposal {
  action_id: number;
  kind: string;
  payload: Record<string, string | null | undefined> | null;
  state: string;
}

export const api = {
  health: () =>
    fetch(getApiBase() + API_ENDPOINTS.health).then((r) => r.json() as Promise<Health>),
  // Authed probe: /health is open, so it can't tell us the token is valid. This can.
  ping: () => req<unknown>(API_ENDPOINTS.ping),
  board: () => req<BoardJob[]>(API_ENDPOINTS.board),
  job: (id: number) => req<JobDetail>(API_ENDPOINTS.job(id)),
  runs: () => req<Run[]>(API_ENDPOINTS.runsList),
  discover: () => req<{ started: boolean }>(API_ENDPOINTS.discover, { method: "POST" }),
  score: () => req<{ started: boolean }>(API_ENDPOINTS.score, { method: "POST" }),
  profiles: () => req<Profile[]>(API_ENDPOINTS.profiles),
  addProfile: (b: { name: string; keywords: string; location: string; pages: number }) =>
    req<{ id: number }>(API_ENDPOINTS.profiles, { method: "POST", body: JSON.stringify(b) }),
  setProfileEnabled: (id: number, enabled: boolean) =>
    req(API_ENDPOINTS.profile(id), { method: "PATCH", body: JSON.stringify({ enabled }) }),
  logApplication: (b: { job_id: number; variant_slug: string; cover_letter: string; status?: string }) =>
    req(API_ENDPOINTS.applications, { method: "POST", body: JSON.stringify(b) }),
  tailor: (id: number) => req<TailorResult>(API_ENDPOINTS.jobTailor(id), { method: "POST" }),
  cover: (id: number) => req<CoverResult>(API_ENDPOINTS.jobCover(id), { method: "POST" }),
  drafts: (id: number) => req<Draft[]>(API_ENDPOINTS.jobDrafts(id)),
  review: (id: number, cover_letter = "") =>
    req<ReviewResult>(API_ENDPOINTS.applyReview, {
      method: "POST",
      body: JSON.stringify({ job_id: id, cover_letter, answers: {} }),
    }),
  analytics: () => req<Analytics>(API_ENDPOINTS.analytics),
  getContext: () => req<UserContext>(API_ENDPOINTS.context),
  setContext: (b: { content: string; format: string }) =>
    req<{ ok?: boolean; format?: string; length?: number }>(API_ENDPOINTS.context, {
      method: "POST",
      body: JSON.stringify(b),
    }),
  getApplicant: () => req<Applicant>(API_ENDPOINTS.applicant),
  setApplicant: (b: Partial<Applicant>) =>
    req<{ ok?: boolean }>(API_ENDPOINTS.applicant, { method: "POST", body: JSON.stringify(b) }),
  fillJob: (id: number) =>
    req<{ started: boolean }>(API_ENDPOINTS.jobFill(id), { method: "POST" }),
  emails: (params: { category?: string; state?: string } = {}) => {
    const qs = new URLSearchParams();
    if (params.category) qs.set("category", params.category);
    if (params.state) qs.set("state", params.state);
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return req<EmailSummary[]>(API_ENDPOINTS.emails + suffix);
  },
  emailDetail: (id: number) => req<EmailDetail>(API_ENDPOINTS.emailDetail(id)),
  syncEmails: () => req<{ started: boolean }>(API_ENDPOINTS.emailsSync, { method: "POST" }),
  proposeAction: (id: number, kind: string, label?: string | null) =>
    req<EmailActionProposal>(API_ENDPOINTS.emailPropose(id), {
      method: "POST",
      body: JSON.stringify({ kind, label: label ?? null }),
    }),
  confirmAction: (
    id: number,
    body: { kind: string; action_id?: number; confirm: boolean; label?: string | null },
  ) =>
    req<{ action_id: number; kind: string; state: string; executed_at: string }>(
      API_ENDPOINTS.emailAction(id),
      { method: "POST", body: JSON.stringify(body) },
    ),
  dismissAction: (id: number) =>
    req<{ action_id: number; state: string }>(
      API_ENDPOINTS.emailDismiss(id),
      { method: "POST" },
    ),
};
