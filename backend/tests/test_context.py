"""User-context: store, retrieve, inject into prompts, and affect the scoring hash."""
from __future__ import annotations

from job_hunt import services
from job_hunt.scoring import match
from job_hunt.scoring.match import _hash
from job_hunt.services.context import context_preamble


def test_set_and_get_context(tmp_db):
    result = services.set_context("# Me\nBackend engineer, 2y Node.", "md")
    assert result["ok"] is True and result["format"] == "md"

    ctx = services.get_context()
    assert ctx["content"].startswith("# Me") and ctx["format"] == "md"


def test_set_context_rejects_empty_and_bad_format(tmp_db):
    assert "error" in services.set_context("   ", "md")
    assert "error" in services.set_context("something", "yaml")


def test_get_context_is_null_when_unset(tmp_db):
    assert services.get_context()["content"] is None


def test_set_context_replaces_previous(tmp_db):
    services.set_context("first", "md")
    services.set_context('{"a": 1}', "json")
    ctx = services.get_context()
    assert ctx["content"] == '{"a": 1}' and ctx["format"] == "json"


def test_preamble_empty_when_unset_and_populated_after(tmp_db):
    assert context_preamble() == ""
    services.set_context("Prefers remote backend roles; avoid FIFO.", "md")
    preamble = context_preamble()
    assert "Prefers remote backend roles" in preamble
    assert preamble.lower().startswith("about the candidate")


def test_preamble_injected_into_scoring_prompt(tmp_db):
    services.set_context("Prefers remote backend roles.", "md")
    job = {"title": "BE", "company": "Acme", "location": "blr", "source": "naukri"}
    prompt = match._build_prompt({"headline": "BE"}, job, "JD text", context_preamble())
    assert "Prefers remote backend roles." in prompt


def test_context_is_part_of_the_idempotency_hash():
    # Changing the user context must produce a different input_hash, so already-scored
    # jobs re-score against the new context.
    assert _hash("jd-text" + "") != _hash("jd-text" + "about me: remote only")
