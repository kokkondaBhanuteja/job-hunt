"""Tests for the content post draft engine.

Hermetic — uses the tmp_db SQLite fixture; chat and top_topics are monkeypatched.
Nothing is posted or sent to external services.
"""
from __future__ import annotations

from job_hunt.content import sources as content_sources
from job_hunt.services import content as content_svc
from job_hunt.storage import repo

# ---------- helpers ----------


def _stub_topics(**k):  # noqa: ANN001, ANN202 — test stub, no public API
    return [{"title": "Rust in prod", "url": "http://x", "snippet": "s"}]


def _stub_chat(*args, **kwargs):  # noqa: ANN001, ANN202 — test stub
    return "my take..."


# ---------- generate_post ----------


def test_generate_post_stores_draft(tmp_db, monkeypatch):
    monkeypatch.setattr(content_sources, "top_topics", lambda **k: [
        {"title": "Rust in prod", "url": "http://x", "snippet": "s"}
    ])
    monkeypatch.setattr("job_hunt.services.content.chat", _stub_chat)
    result = content_svc.generate_post()
    assert "error" not in result
    assert result["topic"] == "Rust in prod"
    assert result["source_url"] == "http://x"
    assert result["body"] == "my take..."
    assert isinstance(result["post_id"], int)


def test_generate_post_status_is_draft(tmp_db, monkeypatch):
    monkeypatch.setattr(content_sources, "top_topics", lambda **k: [
        {"title": "Rust in prod", "url": "http://x", "snippet": "s"}
    ])
    monkeypatch.setattr("job_hunt.services.content.chat", _stub_chat)
    result = content_svc.generate_post()
    stored = repo.get_post(result["post_id"])
    assert stored is not None
    assert stored["status"] == "draft"


def test_generate_post_with_explicit_topic(tmp_db, monkeypatch):
    monkeypatch.setattr("job_hunt.services.content.chat", _stub_chat)
    result = content_svc.generate_post(topic="TypeScript 5.5")
    assert result["topic"] == "TypeScript 5.5"
    assert result["source_url"] is None
    assert result["body"] == "my take..."


def test_generate_post_no_topics_no_arg(tmp_db, monkeypatch):
    monkeypatch.setattr(content_sources, "top_topics", lambda **k: [])
    result = content_svc.generate_post()
    assert result == {"error": "no topic available"}


# ---------- list_posts ----------


def test_list_posts_by_status(tmp_db, monkeypatch):
    monkeypatch.setattr(content_sources, "top_topics", lambda **k: [
        {"title": "Rust in prod", "url": "http://x", "snippet": "s"}
    ])
    monkeypatch.setattr("job_hunt.services.content.chat", _stub_chat)
    content_svc.generate_post()
    posts = content_svc.list_posts(status="draft")
    assert len(posts) == 1
    assert posts[0]["topic"] == "Rust in prod"
    assert posts[0]["status"] == "draft"


def test_list_posts_no_filter_returns_all(tmp_db, monkeypatch):
    monkeypatch.setattr(content_sources, "top_topics", lambda **k: [
        {"title": "Rust in prod", "url": "http://x", "snippet": "s"}
    ])
    monkeypatch.setattr("job_hunt.services.content.chat", _stub_chat)
    content_svc.generate_post()
    content_svc.generate_post(topic="Go generics")
    posts = content_svc.list_posts()
    assert len(posts) == 2


# ---------- set_post_status ----------


def test_set_post_status_to_posted(tmp_db, monkeypatch):
    monkeypatch.setattr(content_sources, "top_topics", lambda **k: [
        {"title": "Rust in prod", "url": "http://x", "snippet": "s"}
    ])
    monkeypatch.setattr("job_hunt.services.content.chat", _stub_chat)
    result = content_svc.generate_post()
    post_id = result["post_id"]
    updated = content_svc.set_post_status(post_id, "posted")
    assert updated["status"] == "posted"
    assert repo.get_post(post_id)["status"] == "posted"


def test_set_post_status_to_dismissed(tmp_db, monkeypatch):
    monkeypatch.setattr(content_sources, "top_topics", lambda **k: [
        {"title": "Rust in prod", "url": "http://x", "snippet": "s"}
    ])
    monkeypatch.setattr("job_hunt.services.content.chat", _stub_chat)
    result = content_svc.generate_post()
    updated = content_svc.set_post_status(result["post_id"], "dismissed")
    assert updated["status"] == "dismissed"


def test_set_post_status_invalid_returns_error(tmp_db):
    result = content_svc.set_post_status(1, "bogus_status")
    assert "error" in result


def test_set_post_status_nonexistent_returns_error(tmp_db):
    result = content_svc.set_post_status(99999, "posted")
    assert "error" in result
    assert "not found" in result["error"]
