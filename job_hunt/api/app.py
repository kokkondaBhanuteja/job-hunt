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
from pydantic import BaseModel

from job_hunt import plugins, services
from job_hunt.enums import Score
from job_hunt.llm.registry import resolve as resolve_llm
from job_hunt.storage import repo

# ---------- auth ----------

# Generated once per process; overridden by API_TOKEN if set.
_EPHEMERAL_TOKEN = secrets.token_hex(16)


def expected_token() -> str:
    return os.getenv("API_TOKEN") or _EPHEMERAL_TOKEN


def require_token(authorization: str | None = Header(default=None)) -> None:
    presented = (authorization or "").removeprefix("Bearer ").strip()
    if not secrets.compare_digest(presented, expected_token()):
        raise HTTPException(status_code=401, detail="invalid or missing API token")


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
    answers: dict[str, str] = {}


class StageIn(BaseModel):
    stage: str


# ---------- app ----------

app = FastAPI(title="job-hunt API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],  # Vite dev
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, Any]:
    """Unauthenticated reachability + config summary (no secrets)."""
    tasks = {t: {"provider": p.name, "model": m} for t in ("scoring", "drafting")
             for p, m in [resolve_llm(t)]}
    return {"status": "ok", "datastore": repo.backend,
            "sources": plugins.available_sources(), "llm": tasks}


api = APIRouter(prefix="/api", dependencies=[Depends(require_token)])


@api.get("/jobs")
def list_jobs(min_score: int = Score.DEFAULT_MIN_MATCH, limit: int = 20) -> list[dict[str, Any]]:
    return services.list_top_matches(min_score=min_score, limit=limit)


@api.get("/board")
def board(limit: int = 200) -> list[dict[str, Any]]:
    return services.list_board(limit)


@api.get("/jobs/{job_id}")
def get_job(job_id: int) -> dict[str, Any]:
    result = services.get_job(job_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@api.get("/resume-variants")
def resume_variants() -> list[dict[str, Any]]:
    return services.list_resume_vault()


@api.get("/search-profiles")
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


@api.get("/runs")
def list_runs(limit: int = 20) -> list[dict[str, Any]]:
    return services.list_runs(limit)


@api.get("/runs/{run_id}")
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
    result = services.tailor_for_job(job_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@api.post("/jobs/{job_id}/cover")
def cover(job_id: int) -> dict[str, Any]:
    result = services.draft_cover_for_job(job_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@api.get("/jobs/{job_id}/drafts")
def drafts(job_id: int) -> list[dict[str, Any]]:
    return services.list_drafts(job_id)


@api.post("/apply/review")
def apply_review(body: ReviewIn) -> dict[str, Any]:
    """AI pre-submit review of an application (never submits — for the review queue)."""
    result = services.review_application(
        body.job_id, cover_letter=body.cover_letter, answers=body.answers
    )
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@api.get("/analytics")
def analytics() -> dict[str, Any]:
    return services.dashboard()


@api.post("/jobs/{job_id}/learn-rejection")
def learn_rejection(job_id: int) -> dict[str, Any]:
    result = services.learn_from_rejection(job_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@api.patch("/applications/{job_id}/stage")
def application_stage(job_id: int, body: StageIn) -> dict[str, Any]:
    result = services.advance_stage(job_id, body.stage)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@api.post("/applications")
def log_application(body: ApplicationIn) -> dict[str, Any]:
    result = services.log_application(
        body.job_id, body.variant_slug, body.cover_letter, status=body.status
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


def _safe_score() -> None:
    try:
        services.score_pending()
    except Exception:  # noqa: BLE001 — background task; failures are logged via llm_calls/runs
        pass


app.include_router(api)
