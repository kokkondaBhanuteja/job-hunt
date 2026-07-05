"""API response models (DTOs).

Annotating endpoints with `response_model=` makes the response shape an ENFORCED contract
instead of an untyped dict that the hand-written frontend `api.ts` interfaces merely assume —
a service field rename now fails loudly (validation error) instead of silently breaking the UI.
Fields mirror `frontend/src/api.ts`; extra service-dict keys are filtered out by FastAPI.

Only the stably-shaped read endpoints get DTOs. The job-detail endpoint stays an open dict
(the frontend types it as `Record<string, unknown>` on purpose — it surfaces every job column).
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class HealthLLM(BaseModel):
    provider: str
    model: str


class Health(BaseModel):
    status: str
    datastore: str
    db_ok: bool = True
    sources: list[str]
    llm: dict[str, HealthLLM]


class BoardJob(BaseModel):
    id: int
    title: str
    company: str
    location: str | None = None
    state: str
    apply_url: str
    best_score: int | None = None


class TopMatch(BaseModel):
    job_id: int
    title: str
    company: str
    location: str | None = None
    apply_url: str
    source: str
    best_score: int
    best_variant: str


class Run(BaseModel):
    id: int
    status: str
    jobs_found: int | None = None
    jobs_new: int | None = None
    started_at: str | None = None
    finished_at: str | None = None
    log: str = ""


class Profile(BaseModel):
    id: int
    name: str
    keywords: str
    location: str
    pages: int
    enabled: bool


# ---------- analytics (nested) ----------


class _StateCount(BaseModel):
    state: str
    n: int


class _SourceCount(BaseModel):
    source: str
    n: int


class _StageCount(BaseModel):
    stage: str
    n: int


class _SourceEffectiveness(BaseModel):
    source: str
    applied: int


class _LLMByTask(BaseModel):
    task: str
    calls: int
    cost: float


class _VariantPerformance(BaseModel):
    variant: str
    applications: int
    interviews: int
    offers: int
    rejections: int


class _LLMCost(BaseModel):
    calls: int
    cost: float
    tokens: int


class Analytics(BaseModel):
    jobs_by_state: list[_StateCount]
    jobs_by_source: list[_SourceCount]
    funnel: list[_StageCount]
    source_effectiveness: list[_SourceEffectiveness]
    llm_by_task: list[_LLMByTask]
    variant_performance: list[_VariantPerformance]
    llm_cost: _LLMCost


class EmailSummary(BaseModel):
    """List-row projection of a triaged inbox email."""

    id: int
    from_addr: str | None = None
    from_name: str | None = None
    subject: str | None = None
    received_at: str | None = None
    category: str | None = None
    action_state: str | None = None
    job_id: int | None = None


class EmailDetail(BaseModel):
    """Full triaged-email detail (body_text omitted — the LLM-extracted fields are what the UI needs)."""

    id: int
    mailbox: str | None = None
    uid: int | None = None
    message_id: str | None = None
    from_addr: str | None = None
    from_name: str | None = None
    subject: str | None = None
    received_at: str | None = None
    snippet: str | None = None
    category: str | None = None
    extracted: str | None = None
    company_id: int | None = None
    job_id: int | None = None
    application_id: int | None = None
    action_state: str | None = None
    structured_at: str | None = None
    created_at: str | None = None


class UserContext(BaseModel):
    content: str | None = None
    format: str | None = None
    updated_at: str | None = None


class SearchPrefs(BaseModel):
    content: str | None = None
    updated_at: str | None = None


class Applicant(BaseModel):
    """Applicant personal-details profile (all fields optional — populated incrementally)."""

    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    portfolio_url: str | None = None
    work_authorization: str | None = None
    needs_sponsorship: bool | None = None
    willing_to_relocate: bool | None = None
    notice_period: str | None = None
    expected_ctc: str | None = None
    current_ctc: str | None = None
    years_experience: str | None = None
    referral_source: str | None = None
    extra: str | None = None
    updated_at: str | None = None


class EmailActionProposal(BaseModel):
    """Proposed email action awaiting human confirmation."""

    action_id: int
    kind: str
    payload: dict[str, Any] | None = None
    state: str


class RoleBrief(BaseModel):
    """Structured interview-prep brief for a job."""

    summary: str | None = None
    key_skills: list[str] = []
    interview_topics: list[str] = []
    questions_to_ask: list[str] = []
    fit_notes: str | None = None


class Post(BaseModel):
    """A content post draft — never auto-posted; always reviewed before posting."""

    id: int
    topic: str | None = None
    source_url: str | None = None
    body: str
    status: str
    created_at: str


class ApplyPolicy(BaseModel):
    """Apply-policy criteria: filters which scored jobs surface as ready-to-apply."""

    min_fit_score: int
    must_have: list[str]
    avoid: list[str]
    seniority: str
    remote_only: bool


# ---------- Career Intelligence Engine ----------


class _MatchedReq(BaseModel):
    requirement: str
    evidence: str


class _MissingReq(BaseModel):
    requirement: str
    why_it_matters: str


class ScoreExplanation(BaseModel):
    """Explainable breakdown of why a résumé scored the way it did for a job."""

    job_id: int
    fit_score: int | None = None
    matched: list[_MatchedReq]
    missing: list[_MissingReq]
    suggestions: list[str]


class _GapItem(BaseModel):
    skill: str
    count: int


class SkillGap(BaseModel):
    """Aggregated skill gaps ranked by frequency across all scored jobs."""

    gaps: list[_GapItem]
    considered: int
