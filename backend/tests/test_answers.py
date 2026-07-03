"""Tests for the answer-template library + keyword-overlap matcher."""
from __future__ import annotations

from job_hunt import services


def _seed(tmp_db):
    services.add_answer_template(
        "Why do you want to join our company?",
        "I'm drawn to your work on payments infrastructure and want backend depth.",
        tags=["motivation"],
    )
    services.add_answer_template(
        "How many years of backend experience do you have?",
        "Two years building NestJS and Spring Boot services.",
        tags=["experience"],
    )


def test_add_and_list(tmp_db):
    _seed(tmp_db)
    rows = services.list_answer_templates()
    assert len(rows) == 2


def test_suggest_matches_best_by_keyword_overlap(tmp_db):
    _seed(tmp_db)
    s = services.suggest_answer("Why are you interested in joining this company?")
    assert s is not None
    assert "payments infrastructure" in s["answer"]  # matched the motivation template
    assert s["score"] >= 1


def test_suggest_experience_question(tmp_db):
    _seed(tmp_db)
    s = services.suggest_answer("How many years of experience?")
    assert "NestJS" in s["answer"]


def test_suggest_returns_none_when_no_overlap(tmp_db):
    _seed(tmp_db)
    assert services.suggest_answer("Do you have a driver's license?") is None
