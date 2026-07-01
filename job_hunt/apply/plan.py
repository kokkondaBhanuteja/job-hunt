"""Assemble the application package a human reviews before submit.

Pure packaging — no browser, no LLM, and (by layering rule) **no imports from `services/`**.
The caller (a service) resolves screening answers and passes them in.
"""
from __future__ import annotations

from typing import Any


def build_application_package(
    *, resume_content: str, cover_body: str, answers: list[dict[str, Any]]
) -> dict[str, Any]:
    """Return {resume, cover_letter, answers:[{question, answer, matched}]}."""
    return {"resume": resume_content, "cover_letter": cover_body, "answers": answers}
