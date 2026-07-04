"""MCP server for the job-hunt toolkit.

This is the chat interface — an MCP host (Claude Code / Goose / Cherry Studio)
calls these tools to drive the toolkit. Each tool is a thin adapter over the
shared `job_hunt.services` layer (the same layer the CLI, API, and worker use).

Start manually:
    uv run python -m job_hunt.mcp_server.server

Or wire it into your host's config — see README.
"""
from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from job_hunt import services
from job_hunt.storage.repo import init_db

mcp = FastMCP("job-hunt")


# ---------- Discovery ----------


@mcp.tool()
def discover_naukri(keyword: str, location: str, pages: int = 1) -> dict[str, Any]:
    """Crawl Naukri for jobs matching keyword × location. Persists new jobs.

    Args:
        keyword: e.g. "nestjs backend" or "java spring boot"
        location: e.g. "bangalore" or "hyderabad"
        pages: how many listing pages to walk (1 = ~20 jobs)

    Returns:
        {found: int, new: int}
    """
    result = services.discover_naukri(keyword, location, pages=pages, headless=True)
    return {"found": result["found"], "new": result["new"]}


# ---------- Scoring ----------


@mcp.tool()
def score_pending(verbose: bool = False) -> dict[str, int]:
    """Run the LLM scorer on every job that doesn't yet have a score.

    Returns:
        {jobs_scored: int, score_rows_written: int}
    """
    return services.score_pending(verbose=verbose)


# ---------- Review / dashboard tools ----------


@mcp.tool()
def list_new_jobs(min_score: int = 70, limit: int = 10) -> list[dict[str, Any]]:
    """Show the best-scoring jobs currently awaiting review.

    Args:
        min_score: only show jobs scoring this or higher (default 70)
        limit: how many rows back (default 10)
    """
    return services.list_top_matches(min_score=min_score, limit=limit)


@mcp.tool()
def show_job(job_id: int) -> dict[str, Any]:
    """Get the full record for one job: JD text + all variant scores + reasoning."""
    return services.get_job(job_id)


@mcp.tool()
def list_resume_vault() -> list[dict[str, Any]]:
    """List your resume variants and their tags."""
    return services.list_resume_vault()


# ---------- Application logging ----------


@mcp.tool()
def log_application(
    job_id: int,
    variant_slug: str,
    cover_letter: str,
    status: str = "applied",
) -> dict[str, Any]:
    """Record that you applied to a job (or skipped/saved it).

    Args:
        job_id: from list_new_jobs / show_job
        variant_slug: which resume variant you sent (e.g. 'backend-node')
        cover_letter: the final cover letter text
        status: 'applied' | 'skipped' | 'saved'
    """
    return services.log_application(job_id, variant_slug, cover_letter, status=status)


@mcp.tool()
def fill_application(job_id: int) -> dict:
    """Open a job's ATS form and auto-fill it from stored data, stopping before submit."""
    return services.prepare_form_fill(job_id)


# ---------- Email Triage ----------


@mcp.tool()
def email_sync() -> dict[str, Any]:
    """Sync inbox from IMAP and structure pending emails with the LLM.

    Returns:
        {fetched: int, new: int, structured: int, linked: int} or {error: str}
    """
    result = services.sync_inbox()
    if "error" in result:
        return result
    struct = services.structure_pending()
    if "error" in struct:
        return struct
    return {
        "fetched": result["fetched"],
        "new": result["new"],
        "structured": struct["structured"],
        "linked": struct["linked"],
    }


@mcp.tool()
def email_list(category: str = "", action_state: str = "") -> list[dict[str, Any]]:
    """List emails from the inbox with optional filtering.

    Args:
        category: filter by category (e.g., "recruiter_outreach", "rejection", "other") — empty = no filter
        action_state: filter by action_state — empty = no filter

    Returns:
        list of email dicts (id, category, from_addr, subject, received_at, etc.)
    """
    return services.list_inbox(
        category=category if category else None,
        action_state=action_state if action_state else None,
        limit=100,
    )


@mcp.tool()
def email_get(email_id: int) -> dict[str, Any]:
    """Get a single email by ID with full details and links.

    Args:
        email_id: the email ID to fetch

    Returns:
        full email dict or {error: str} if not found
    """
    return services.get_email(email_id)


# ---------- Run ----------


def main() -> None:
    init_db()
    mcp.run()


if __name__ == "__main__":
    main()
