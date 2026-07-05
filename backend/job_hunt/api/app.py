"""FastAPI app — REST over the services layer, for the React management UI.

Security posture (single-user, local): bind to 127.0.0.1 and require a bearer
token on every /api route even locally — this app can spend LLM credits and (later)
submit applications, so it must never be open on the LAN. Set API_TOKEN in the
environment; if unset, an ephemeral token is generated and printed at startup.

Run:  uv run hunt serve-api        (or: uvicorn job_hunt.api.app:app --host 127.0.0.1)
"""
from __future__ import annotations

import os
import secrets
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from job_hunt import plugins, services
from job_hunt.api import dto
from job_hunt.enums import Score
from job_hunt.llm.registry import resolve as resolve_llm
from job_hunt.logging_config import get_logger
from job_hunt.storage import repo

logger = get_logger(__name__)

# ---------- auth ----------

# Generated once per process; overridden by API_TOKEN if set.
_EPHEMERAL_TOKEN = secrets.token_hex(16)


def expected_token() -> str:
    return os.getenv("API_TOKEN") or _EPHEMERAL_TOKEN


def require_token(authorization: str | None = Header(default=None)) -> None:
    presented = (authorization or "").removeprefix("Bearer ").strip()
    if not secrets.compare_digest(presented, expected_token()):
        raise HTTPException(status_code=401, detail="invalid or missing API token")


# ---------- consistent service-error → HTTP mapping ----------
# One place decides the status for a service `{"error": ...}` result, so the same class of
# failure returns the same code everywhere (previously "no job" was 404 on one route, 400 on
# another). Missing-resource messages → 404; everything else (validation/precondition) → 400.
# (A typed service-exception hierarchy is the eventual upgrade; this fixes the inconsistency now.)
_NOT_FOUND_HINTS = ("no job with id", "no run", "not found")


def _unwrap(result: dict[str, Any]) -> dict[str, Any]:
    if isinstance(result, dict) and "error" in result:
        msg = str(result["error"])
        status = 404 if any(h in msg.lower() for h in _NOT_FOUND_HINTS) else 400
        raise HTTPException(status_code=status, detail=msg)
    return result


# ---------- request models (Pydantic only at the boundary) ----------


class ProfileIn(BaseModel):
    name: str
    keywords: str
    location: str
    pages: int = 1


class EnabledIn(BaseModel):
    enabled: bool


class ApplicationIn(BaseModel):
    job_id: int
    variant_slug: str
    cover_letter: str
    status: str = "applied"


class ReviewIn(BaseModel):
    job_id: int
    cover_letter: str = ""
    answers: dict[str, str] = Field(default_factory=dict)


class StageIn(BaseModel):
    stage: str


class AnswerTemplateIn(BaseModel):
    question_pattern: str
    answer_text: str
    tags: list[str] = Field(default_factory=list)


class ContactIn(BaseModel):
    company: str
    name: str
    role: str | None = None
    persona: str | None = None
    email_guess: str | None = None
    linkedin_url: str | None = None
    notes: str | None = None


class ContextIn(BaseModel):
    content: str
    format: str = "md"


class SearchPrefsIn(BaseModel):
    content: str


class ApplicantIn(BaseModel):
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


class DraftIn(BaseModel):
    kind: str
    email_id: int | None = None


class ProposeIn(BaseModel):
    kind: str
    label: str | None = None


class EmailActionIn(BaseModel):
    kind: str
    action_id: int | None = None
    confirm: bool = False
    label: str | None = None


class PostIn(BaseModel):
    topic: str | None = None


class PostStatusIn(BaseModel):
    status: str


class WatchIn(BaseModel):
    company: str
    ats: str
    board_token: str


# ---------- app ----------

app = FastAPI(title="job-hunt API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5000", "http://127.0.0.1:5000"],  # Vite dev
    allow_methods=["*"],
    allow_headers=["*"],
)


def _db_ok() -> bool:
    try:
        repo.raw_select("SELECT 1")
        return True
    except Exception:  # noqa: BLE001
        return False


@app.get("/health", response_model=dto.Health)
def health() -> dict[str, Any]:
    """Unauthenticated readiness + config summary (no secrets).

    Actually probes the datastore (SELECT 1) so it reports "degraded" when Postgres is down,
    instead of a blind "ok". (LLM liveness is intentionally not pinged on this polled endpoint;
    use `hunt selfcheck` for a deep provider probe.)
    """
    db_ok = _db_ok()
    tasks = {t: {"provider": p.name, "model": m} for t in ("scoring", "drafting")
             for p, m in [resolve_llm(t)]}
    return {"status": "ok" if db_ok else "degraded", "datastore": repo.backend,
            "db_ok": db_ok, "sources": plugins.available_sources(), "llm": tasks}


api = APIRouter(prefix="/api", dependencies=[Depends(require_token)])


@api.get("/jobs", response_model=list[dto.TopMatch])
def list_jobs(min_score: int = Score.DEFAULT_MIN_MATCH, limit: int = 20) -> list[dict[str, Any]]:
    return services.list_top_matches(min_score=min_score, limit=limit)


@api.get("/board", response_model=list[dto.BoardJob])
def board(limit: int = 200) -> list[dict[str, Any]]:
    return services.list_board(limit)


@api.get("/jobs/{job_id}")
def get_job(job_id: int) -> dict[str, Any]:
    return _unwrap(services.get_job(job_id))


@api.get("/resume-variants")
def resume_variants() -> list[dict[str, Any]]:
    return services.list_resume_vault()


@api.get("/search-profiles", response_model=list[dto.Profile])
def list_profiles() -> list[dict[str, Any]]:
    return services.list_profiles()


@api.post("/search-profiles", status_code=201)
def create_profile(body: ProfileIn) -> dict[str, Any]:
    pid = services.add_profile(
        name=body.name, keywords=body.keywords, location=body.location, pages=body.pages
    )
    return {"id": pid}


@api.patch("/search-profiles/{profile_id}")
def patch_profile(profile_id: int, body: EnabledIn) -> dict[str, Any]:
    services.set_enabled(profile_id, body.enabled)
    return {"ok": True, "id": profile_id, "enabled": body.enabled}


@api.post("/score", status_code=202)
def trigger_score(background: BackgroundTasks) -> dict[str, Any]:
    background.add_task(_safe_score)
    return {"started": True}


@api.post("/discover", status_code=202)
def trigger_discovery(background: BackgroundTasks) -> dict[str, Any]:
    background.add_task(services.run_discovery, headless=True)
    return {"started": True}


@api.get("/runs", response_model=list[dto.Run])
def list_runs(limit: int = 20) -> list[dict[str, Any]]:
    return services.list_runs(limit)


@api.get("/runs/{run_id}", response_model=dto.Run)
def get_run(run_id: int) -> dict[str, Any]:
    run = services.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"no run {run_id}")
    return run


@api.post("/runs/{run_id}/cancel")
def cancel_run(run_id: int) -> dict[str, Any]:
    services.request_cancel(run_id)
    return {"ok": True, "id": run_id}


@api.post("/jobs/{job_id}/tailor")
def tailor(job_id: int) -> dict[str, Any]:
    return _unwrap(services.tailor_for_job(job_id))


@api.post("/jobs/{job_id}/cover")
def cover(job_id: int) -> dict[str, Any]:
    return _unwrap(services.draft_cover_for_job(job_id))


@api.post("/jobs/{job_id}/brief", response_model=dto.RoleBrief)
def brief(job_id: int) -> dict[str, Any]:
    """Generate a structured interview-prep brief for a job."""
    return _unwrap(services.brief_for_job(job_id))


@api.get("/jobs/{job_id}/drafts")
def drafts(job_id: int) -> list[dict[str, Any]]:
    return services.list_drafts(job_id)


@api.post("/jobs/{job_id}/draft")
def draft_message(job_id: int, body: DraftIn) -> dict[str, Any]:
    """Generate a thank-you, follow-up, or negotiation message for a job."""
    return _unwrap(services.draft_message_for_job(job_id, body.kind, email_id=body.email_id))


@api.post("/jobs/{job_id}/outreach")
def outreach(job_id: int, contact_name: str = "") -> dict[str, Any]:
    return _unwrap(services.draft_outreach_for_job(job_id, contact_name=contact_name))


@api.get("/companies/{name}/history")
def company_history(name: str) -> dict[str, Any]:
    return services.company_history(name)


@api.get("/contacts")
def contacts(company: str | None = None) -> list[dict[str, Any]]:
    return services.list_contacts(company)


@api.post("/contacts", status_code=201)
def create_contact(body: ContactIn) -> dict[str, Any]:
    cid = services.add_contact(
        company=body.company, name=body.name, role=body.role, persona=body.persona,
        email_guess=body.email_guess, linkedin_url=body.linkedin_url, notes=body.notes,
    )
    return {"id": cid}


@api.post("/apply/review")
def apply_review(body: ReviewIn) -> dict[str, Any]:
    """AI pre-submit review of an application (never submits — for the review queue)."""
    return _unwrap(services.review_application(
        body.job_id, cover_letter=body.cover_letter, answers=body.answers
    ))


@api.get("/context", response_model=dto.UserContext)
def get_context() -> dict[str, Any]:
    return services.get_context()


@api.post("/context")
def set_context(body: ContextIn) -> dict[str, Any]:
    return _unwrap(services.set_context(body.content, body.format))


@api.get("/search-prefs", response_model=dto.SearchPrefs)
def get_search_prefs() -> dict[str, Any]:
    """Return the stored job-search preferences blob."""
    return services.get_search_prefs()


@api.post("/search-prefs")
def set_search_prefs(body: SearchPrefsIn) -> dict[str, Any]:
    """Parse and store job-search preferences, creating search profiles."""
    return _unwrap(services.set_search_prefs(body.content))


@api.get("/apply-policy", response_model=dto.ApplyPolicy)
def get_apply_policy() -> dict[str, Any]:
    """Return the stored apply-policy criteria (or safe defaults if unset)."""
    return services.get_policy()


@api.get("/ready-to-apply", response_model=list[dto.TopMatch])
def ready_to_apply(limit: int = 50) -> list[dict[str, Any]]:
    """Return scored jobs that pass the apply policy — for human review only."""
    return services.list_ready_to_apply(limit=limit)


@api.get("/applicant", response_model=dto.Applicant)
def get_applicant() -> dict[str, Any]:
    """Return the stored applicant personal-details profile."""
    return services.get_applicant()


@api.post("/applicant")
def set_applicant(body: ApplicantIn) -> dict[str, Any]:
    """Persist the supplied applicant fields; returns {ok: true} on success."""
    return _unwrap(services.set_applicant(body.model_dump(exclude_none=True)))


@api.post("/jobs/{job_id}/fill", status_code=202)
def fill_job(job_id: int, background: BackgroundTasks) -> dict[str, Any]:
    """Kick off a non-blocking ATS form-fill for the given job."""
    background.add_task(_safe_fill, job_id)
    return {"started": True}


@api.get("/answer-templates")
def answer_templates() -> list[dict[str, Any]]:
    return services.list_answer_templates()


@api.post("/answer-templates", status_code=201)
def create_answer_template(body: AnswerTemplateIn) -> dict[str, Any]:
    tid = services.add_answer_template(body.question_pattern, body.answer_text, body.tags)
    return {"id": tid}


@api.get("/answer-templates/suggest")
def suggest_answer(q: str) -> dict[str, Any]:
    result = services.suggest_answer(q)
    return result or {"answer": None}


@api.get("/analytics", response_model=dto.Analytics)
def analytics() -> dict[str, Any]:
    return services.dashboard()


@api.post("/embed")
def embed(limit: int = 200) -> dict[str, Any]:
    return _unwrap(services.embed_jobs(limit=limit))


@api.get("/semantic")
def semantic(q: str, limit: int = 10) -> dict[str, Any]:
    return _unwrap(services.semantic_match(q, limit=limit))


@api.get("/jobs/{job_id}/similar-successful")
def similar_successful(job_id: int, limit: int = 5) -> dict[str, Any]:
    """Return jobs similar to job_id that reached interview, HR, or offer stage."""
    return _unwrap(services.similar_successful(job_id, limit=limit))


@api.post("/jobs/{job_id}/learn-rejection")
def learn_rejection(job_id: int) -> dict[str, Any]:
    return _unwrap(services.learn_from_rejection(job_id))


@api.get("/jobs/{job_id}/next-action", response_model=dto.NextAction)
def next_action(job_id: int) -> dict[str, Any]:
    """Return the single highest-priority recommended action for a job (advisory only)."""
    return _unwrap(services.next_best_action(job_id))


@api.get("/jobs/{job_id}/explain", response_model=dto.ScoreExplanation)
def explain_score(job_id: int, force: bool = False) -> dict[str, Any]:
    """Return an explainable breakdown of which JD requirements the résumé meets/misses."""
    return _unwrap(services.explain_score(job_id, force=force))


@api.get("/skill-gap", response_model=dto.SkillGap)
def skill_gap(limit: int = 20) -> dict[str, Any]:
    """Aggregate missing requirements across all scored jobs and return ranked skill gaps."""
    return services.skill_gap(limit=limit)


@api.patch("/applications/{job_id}/stage")
def application_stage(job_id: int, body: StageIn) -> dict[str, Any]:
    return _unwrap(services.advance_stage(job_id, body.stage))


@api.post("/applications")
def log_application(body: ApplicationIn) -> dict[str, Any]:
    return _unwrap(services.log_application(
        body.job_id, body.variant_slug, body.cover_letter, status=body.status
    ))


@api.get("/emails", response_model=list[dto.EmailSummary])
def list_emails(category: str | None = None, state: str | None = None) -> list[dict[str, Any]]:
    """List triaged inbox emails, optionally filtered by category and/or action state."""
    return services.list_inbox(category=category, action_state=state)


@api.get("/emails/{email_id}", response_model=dto.EmailDetail)
def email_detail(email_id: int) -> dict[str, Any]:
    """Return one triaged email's full detail, or 404 if absent."""
    return _unwrap(services.get_email(email_id))


@api.post("/emails/{email_id}/propose", response_model=dto.EmailActionProposal)
def propose_email_action(email_id: int, body: ProposeIn) -> dict[str, Any]:
    """Propose an email action for human review and return the stored proposal."""
    return _unwrap(services.propose_action(email_id, body.kind, label=body.label))


@api.post("/emails/{email_id}/action")
def execute_email_action(email_id: int, body: EmailActionIn) -> dict[str, Any]:
    """Execute or gate a proposed email action; requires confirm=True to open IMAP."""
    return _unwrap(
        services.confirm_action(email_id, action_id=body.action_id, confirm=body.confirm)
    )


@api.post("/emails/{email_id}/dismiss")
def dismiss_email_action(email_id: int) -> dict[str, Any]:
    """Dismiss the pending proposed action on an email."""
    return _unwrap(services.dismiss_action(email_id))


@api.post("/emails/sync", status_code=202)
def sync_emails(background: BackgroundTasks) -> dict[str, Any]:
    """Kick off a non-blocking IMAP sync + LLM structuring pass (real IMAP must not block)."""
    background.add_task(_safe_email_sync)
    return {"started": True}


def _safe_score() -> None:
    try:
        services.score_pending(track=True)  # creates a run row so the Runs UI can show it
    except Exception:  # noqa: BLE001 — background task; the failure is recorded on the run row
        pass


def _safe_email_sync() -> None:
    """Sync the inbox then structure pending emails in the background; log and swallow errors."""
    try:
        services.sync_inbox()
        services.structure_pending()
    except Exception:  # noqa: BLE001 — background task; log and swallow
        logger.exception("email sync failed")


def _safe_fill(job_id: int) -> None:
    """Run prepare_form_fill in the background; log and swallow any exception."""
    try:
        services.prepare_form_fill(job_id)
    except Exception:  # noqa: BLE001 — background task; log and swallow
        logger.exception("form-fill failed for job %s", job_id)


@api.get("/posts", response_model=list[dto.Post])
def list_posts(status: str | None = None) -> list[dict[str, Any]]:
    """Return stored post drafts, optionally filtered by status."""
    return services.list_posts(status=status)


@api.post("/posts", response_model=dto.Post, status_code=201)
def create_post(body: PostIn) -> dict[str, Any]:
    """Generate a new AI post draft grounded in a current tech topic."""
    return _unwrap(services.generate_post(topic=body.topic))


@api.patch("/posts/{post_id}", response_model=dto.Post)
def update_post_status(post_id: int, body: PostStatusIn) -> dict[str, Any]:
    """Transition a post draft to a new status (draft → posted | dismissed)."""
    return _unwrap(services.set_post_status(post_id, body.status))


@api.get("/watchlist", response_model=list[dto.WatchEntry])
def list_watchlist() -> list[dict[str, Any]]:
    """Return all company watchlist entries."""
    return services.list_watch()


@api.post("/watchlist", response_model=dto.WatchEntry, status_code=201)
def create_watch(body: WatchIn) -> dict[str, Any]:
    """Add a company to the watchlist."""
    result = _unwrap(services.add_watch_company(body.company, body.ats, body.board_token))
    # Re-fetch the full row so the response contains real enabled/created_at values.
    rows = [r for r in services.list_watch() if r["id"] == result["id"]]
    if not rows:
        raise HTTPException(status_code=500, detail="watch entry created but not found on re-fetch")
    return rows[0]


@api.delete("/watchlist/{watch_id}")
def delete_watch(watch_id: int) -> dict[str, Any]:
    """Remove a company from the watchlist."""
    return _unwrap(services.remove_watch(watch_id))


@api.patch("/watchlist/{watch_id}", response_model=dto.WatchEntry)
def patch_watch(watch_id: int, body: EnabledIn) -> dict[str, Any]:
    """Enable or disable a watchlist entry."""
    _unwrap(services.set_watch_enabled(watch_id, body.enabled))
    # Re-fetch the updated row so the response model is populated.
    rows = [r for r in services.list_watch() if r["id"] == watch_id]
    if not rows:
        raise HTTPException(status_code=404, detail=f"no watchlist entry with id {watch_id}")
    return rows[0]


app.include_router(api)
