"""Assemble the application package a human reviews before submit.

Pulls the tailored résumé + cover letter and answers each screening question from the
answer-template library (never a canned paragraph). Pure — no browser, no LLM.
"""
from __future__ import annotations

from typing import Any

from job_hunt.services.answers import suggest_answer


def build_application_package(
    *, resume_content: str, cover_body: str, screening_questions: list[str]
) -> dict[str, Any]:
    """Return {resume, cover_letter, answers:[{question, answer, matched}]}."""
    answers: list[dict[str, Any]] = []
    for question in screening_questions or []:
        suggestion = suggest_answer(question)
        answers.append({
            "question": question,
            "answer": suggestion["answer"] if suggestion else "",
            "matched": suggestion["matched"] if suggestion else None,
        })
    return {"resume": resume_content, "cover_letter": cover_body, "answers": answers}
