"""Tests for services.naukri_refresh — draft-only, zero browser interaction."""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from job_hunt.services import naukri_refresh as mod

# ---------- helpers ----------

_FAKE_DRAFT: dict[str, Any] = {
    "headline": "Backend Engineer | Python",
    "summary": "Experienced Python backend developer with FastAPI and AWS expertise.",
    "skills": ["Python"],
}


def _stub_chat_json(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    return _FAKE_DRAFT


def _seed_context_and_variant(db: Any) -> None:
    db.set_user_context(
        content="I am a backend engineer with 4 years of Python experience.",
        fmt="md",
    )
    db.upsert_resume_variant(
        slug="backend-python",
        source_path="/resumes/backend.tex",
        parsed={"headline": "Backend Engineer", "skills": {"languages": ["Python"]}},
        tags=["backend", "python"],
    )


# ---------- happy path ----------

def test_draft_profile_refresh_returns_expected_shape(tmp_db, monkeypatch):
    """draft_profile_refresh() with context + variant returns the LLM dict."""
    _seed_context_and_variant(tmp_db)
    monkeypatch.setattr(mod, "chat_json", _stub_chat_json)

    result = mod.draft_profile_refresh()

    assert result["headline"] == "Backend Engineer | Python"
    assert "summary" in result
    assert "skills" in result


def test_draft_profile_refresh_prompt_includes_context_and_resume(tmp_db, monkeypatch):
    """The prompt passed to chat_json contains both the context preamble and résumé JSON."""
    _seed_context_and_variant(tmp_db)

    captured: dict[str, Any] = {}

    def _capture(prompt: str, **kwargs: Any) -> dict[str, Any]:
        captured["prompt"] = prompt
        captured["kwargs"] = kwargs
        return _FAKE_DRAFT

    monkeypatch.setattr(mod, "chat_json", _capture)

    mod.draft_profile_refresh()

    assert "About the candidate" in captured["prompt"]
    assert "backend-python" in captured["prompt"] or "Backend Engineer" in captured["prompt"]
    assert captured["kwargs"]["task"] == "drafting"
    assert captured["kwargs"]["system"] == mod.PROFILE_REFRESH.system


# ---------- no-context path ----------

def test_draft_profile_refresh_no_context_returns_error(tmp_db, monkeypatch):
    """draft_profile_refresh() without any career context returns {error: ...}."""
    monkeypatch.setattr(mod, "chat_json", _stub_chat_json)

    result = mod.draft_profile_refresh()

    assert "error" in result


# ---------- no-variant path ----------

def test_draft_profile_refresh_no_variant_returns_error(tmp_db, monkeypatch):
    """draft_profile_refresh() with context but no résumé variants returns {error: ...}."""
    tmp_db.set_user_context(
        content="I am a backend engineer.",
        fmt="md",
    )
    monkeypatch.setattr(mod, "chat_json", _stub_chat_json)

    result = mod.draft_profile_refresh()

    assert "error" in result


# ---------- refresh_reminder ----------

def test_refresh_reminder_sends_notification_on_success(tmp_db, monkeypatch):
    """refresh_reminder() calls notifier.send with the headline and summary."""
    _seed_context_and_variant(tmp_db)
    monkeypatch.setattr(mod, "chat_json", _stub_chat_json)

    sent_texts: list[str] = []

    fake_notifier = MagicMock()
    fake_notifier.send.side_effect = lambda text: sent_texts.append(text)
    monkeypatch.setattr(mod, "get_notifier", lambda: fake_notifier)

    mod.refresh_reminder()  # must not raise

    assert len(sent_texts) == 1
    assert "Backend Engineer | Python" in sent_texts[0]
    assert "Summary" in sent_texts[0]


def test_refresh_reminder_does_not_raise_on_error(tmp_db, monkeypatch):
    """refresh_reminder() swallows exceptions and never raises."""
    monkeypatch.setattr(mod, "chat_json", _stub_chat_json)
    # No context → draft_profile_refresh returns {error: ...} → logs and returns
    mod.refresh_reminder()  # must not raise


# ---------- no browser / login import guard ----------

def test_module_has_no_browser_or_login_import():
    """naukri_refresh must not import browser, login, or automation modules."""
    import re

    source_path = mod.__file__
    assert source_path is not None

    with open(source_path, encoding="utf-8") as fh:
        source = fh.read()

    # Check that none of the forbidden modules appear in import statements.
    forbidden_imports = [
        r"job_hunt\.browser",
        r"job_hunt\.sources\.login",
        r"playwright",
        r"selenium",
        r"puppeteer",
        r"webdriver",
    ]
    import_lines = [ln for ln in source.splitlines() if ln.strip().startswith(("import ", "from "))]
    import_block = "\n".join(import_lines)

    for pattern in forbidden_imports:
        assert not re.search(pattern, import_block), (
            f"naukri_refresh.py must not import '{pattern}' — found in import statements"
        )
