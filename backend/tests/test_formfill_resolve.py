"""Value resolution for form fields: applicant → resume → context → draft → file."""
from __future__ import annotations

from job_hunt.apply.formfill import _resolve

DATA = {
    "applicant": {"first_name": "Bhanu", "last_name": "T", "email": "a@b.in"},
    "resume": {"headline": "Backend Engineer"},
    "context": "Prefers remote roles.",
    "draft": {"cover": "Dear team,"},
    "file": {"resume_variant": "/vault/backend.pdf"},
}


def test_resolve_applicant_field():
    assert _resolve("applicant.first_name", DATA) == "Bhanu"


def test_resolve_synthetic_full_name():
    assert _resolve("applicant.full_name", DATA) == "Bhanu T"


def test_resolve_resume_context_draft_file():
    assert _resolve("resume.headline", DATA) == "Backend Engineer"
    assert _resolve("context", DATA) == "Prefers remote roles."
    assert _resolve("draft.cover", DATA) == "Dear team,"
    assert _resolve("file.resume_variant", DATA) == "/vault/backend.pdf"


def test_resolve_missing_or_unknown_returns_none():
    assert _resolve("applicant.phone", DATA) is None
    assert _resolve("bogus.thing", DATA) is None
