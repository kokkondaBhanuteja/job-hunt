"""Content post draft service — generate, list, and status-transition post drafts.

Drafts are NEVER auto-posted anywhere. Every post starts as DRAFT and is reviewed
by the user before they choose to post it themselves.
"""
from __future__ import annotations

from typing import Any

from job_hunt.content import sources as content_sources
from job_hunt.enums import PostStatus
from job_hunt.llm.client import chat
from job_hunt.llm.prompts import POST_DRAFT
from job_hunt.logging_config import get_logger
from job_hunt.notify.base import get_notifier
from job_hunt.services.context import context_preamble
from job_hunt.storage import repo

logger = get_logger(__name__)


def generate_post(topic: str | None = None) -> dict[str, Any]:
    """Draft a new post grounded in a current tech topic; store it and return its data.

    If `topic` is None, the first result from `top_topics()` is used. Returns
    {error: ...} if no topic is available and no `topic` was given.
    """
    repo.init_db()
    source_url: str | None = None
    snippet: str = ""

    if topic is None:
        topics = content_sources.top_topics()
        if not topics:
            return {"error": "no topic available"}
        first = topics[0]
        topic = first["title"]
        source_url = first.get("url")
        snippet = first.get("snippet", "")

    preamble = context_preamble()
    snippet_part = f"\nTopic snippet: {snippet}" if snippet else ""
    prompt = (
        f"{preamble}"
        f"Write a post about this current tech topic:\n"
        f"Topic: {topic}{snippet_part}\n\n"
        f"Source: {source_url or '(none)'}\n"
    )
    body = chat(
        prompt,
        task="drafting",
        system=POST_DRAFT.system,
        prompt_name=POST_DRAFT.name,
        prompt_version=POST_DRAFT.version,
    )
    post_id = repo.create_post(topic=topic, source_url=source_url, body=body)
    return {"post_id": post_id, "topic": topic, "source_url": source_url, "body": body}


def list_posts(status: str | None = None) -> list[dict[str, Any]]:
    """Return stored post drafts, optionally filtered by status."""
    repo.init_db()
    return repo.list_posts(status=status)


def set_post_status(post_id: int, status: str) -> dict[str, Any]:
    """Transition a post to a new status; return the updated row or {error: ...}."""
    repo.init_db()
    if status not in set(PostStatus):
        valid = ", ".join(f"'{v}'" for v in PostStatus)
        return {"error": f"invalid status '{status}' — must be one of {valid}"}
    post = repo.get_post(post_id)
    if post is None:
        return {"error": f"post {post_id} not found"}
    repo.set_post_status(post_id, status)
    return {**post, "status": status}


def generate_and_notify_post() -> None:
    """Scheduled entrypoint: draft a post and notify the user. Never raises."""
    try:
        result = generate_post()
        if "error" in result:
            logger.warning("content_post scheduled draft failed: %s", result["error"])
            return
        topic = result["topic"]
        body = result["body"]
        source_url = result.get("source_url") or ""
        get_notifier().send(
            f"\U0001f4dd New post draft ({topic}):\n\n{body}\n\nsource: {source_url}"
        )
    except Exception:  # noqa: BLE001 — scheduled job must never crash the worker
        logger.exception("generate_and_notify_post failed")
