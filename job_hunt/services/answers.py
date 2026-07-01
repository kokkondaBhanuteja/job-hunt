"""Answer-template services — a library of truthful screening-question answers.

`suggest_answer` picks the best-matching template for a form's screening question by
keyword overlap, so the apply step reuses vetted answers (with light variation) instead
of the same canned paragraph everywhere.
"""
from __future__ import annotations

import json
import re
from typing import Any

from job_hunt.storage import repo

_STOP = {"the", "a", "an", "to", "of", "for", "do", "you", "your", "why", "how", "what",
         "is", "are", "in", "on", "at", "we", "our", "this", "that", "with", "and", "or",
         "have", "has", "had", "many", "much", "any", "please", "us"}


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in _STOP}


def add_answer_template(
    question_pattern: str, answer_text: str, tags: list[str] | None = None
) -> int:
    repo.init_db()
    return repo.save_answer_template(
        question_pattern=question_pattern, answer_text=answer_text, tags=tags
    )


def list_answer_templates() -> list[dict[str, Any]]:
    repo.init_db()
    return [dict(r) for r in repo.list_answer_templates()]


def suggest_answer(question: str) -> dict[str, Any] | None:
    """Best-matching template answer for a screening question, or None."""
    repo.init_db()
    q = _tokens(question)
    if not q:
        return None
    best: dict[str, Any] | None = None
    best_score = 0
    for template in repo.list_answer_templates():
        overlap = len(q & _tokens(template["question_pattern"]))
        if overlap > best_score:
            best_score = overlap
            best = dict(template)
    if best is None or best_score == 0:
        return None
    return {
        "answer": best["answer_text"],
        "matched": best["question_pattern"],
        "score": best_score,
        "tags": json.loads(best["tags"]) if best.get("tags") else [],
    }
