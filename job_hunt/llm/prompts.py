"""Prompt Library — the versioned home for every prompt + JSON schema.

Centralizing these makes `llm/` a true **AI Gateway**: services render per-call data
but never define the reusable prompt/schema inline. Bump a prompt's `version` when its
wording changes, so `llm_calls` can be correlated to prompt versions for A/B and quality
tracking later.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Prompt:
    """A named, versioned prompt: a system message + (for structured tasks) a JSON schema."""

    name: str
    version: int
    system: str
    schema: dict[str, Any] | None = None


# ---------- scoring (job × resume-variant fit) ----------

SCORE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["fit_score", "confidence", "reasoning"],
    "properties": {
        "fit_score": {
            "type": "integer",
            "minimum": 0,
            "maximum": 100,
            "description": (
                "How well this resume variant fits the job. "
                "0-40 = poor fit; 50-69 = stretch; 70-84 = solid; 85+ = strong."
            ),
        },
        "confidence": {
            "type": "integer",
            "minimum": 0,
            "maximum": 100,
            "description": (
                "How sure you are of this score given the information available. "
                "Lower it when the job description is thin/incomplete (e.g. only a "
                "listing snippet) so weak inputs can be flagged for review."
            ),
        },
        "reasoning": {
            "type": "string",
            "description": (
                "ONE short paragraph (2-4 sentences). Be specific: which skills, "
                "experience years, or projects justify the score; what's missing."
            ),
        },
    },
}

SCORING = Prompt(
    name="scoring",
    version=1,
    system=(
        "You are a hiring manager scoring how well a candidate's resume fits a job. "
        "Be honest and concrete. Penalize stack mismatches and seniority gaps. "
        "Reward overlap in tech, domain, and scope. Output JSON only."
    ),
    schema=SCORE_SCHEMA,
)


# ---------- resume parsing (file text → structured JSON) ----------

RESUME_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["slug", "headline", "summary", "skills", "experience", "tags"],
    "properties": {
        "slug": {
            "type": "string",
            "description": "kebab-case identifier matching the file's stem, e.g. 'backend-node'",
        },
        "headline": {
            "type": "string",
            "description": "Short role title under the name, e.g. 'Backend & Cloud Engineer'",
        },
        "summary": {"type": "string"},
        "contact": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "email": {"type": "string"},
                "phone": {"type": "string"},
                "location": {"type": "string"},
                "linkedin": {"type": "string"},
                "github": {"type": "string"},
                "portfolio": {"type": "string"},
            },
        },
        "skills": {
            "type": "object",
            "properties": {
                "languages": {"type": "array", "items": {"type": "string"}},
                "backend": {"type": "array", "items": {"type": "string"}},
                "frontend": {"type": "array", "items": {"type": "string"}},
                "databases": {"type": "array", "items": {"type": "string"}},
                "cloud_devops": {"type": "array", "items": {"type": "string"}},
                "tools": {"type": "array", "items": {"type": "string"}},
            },
        },
        "experience": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["company", "title"],
                "properties": {
                    "company": {"type": "string"},
                    "title": {"type": "string"},
                    "dates": {"type": "string"},
                    "location": {"type": "string"},
                    "bullets": {"type": "array", "items": {"type": "string"}},
                    "tech": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "projects": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "tech": {"type": "array", "items": {"type": "string"}},
                    "dates": {"type": "string"},
                    "url": {"type": "string"},
                },
            },
        },
        "education": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "school": {"type": "string"},
                    "degree": {"type": "string"},
                    "dates": {"type": "string"},
                    "cgpa": {"type": "string"},
                    "location": {"type": "string"},
                },
            },
        },
        "tags": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "3-8 short tags describing the resume's best-fit role types, "
                "e.g. ['backend', 'nestjs', 'aws', 'multi-tenant-saas']. "
                "Used by the matcher to pick the right variant per JD."
            ),
        },
    },
}

RESUME_PARSE = Prompt(
    name="resume_parse",
    version=1,
    system=(
        "You parse software-engineer resumes into structured JSON. "
        "Be faithful to the source text — do NOT invent skills, projects, or experience. "
        "If a field is not in the resume, omit it or leave it empty. "
        "For `tags`, infer 3-8 short identifiers that describe the kind of role this "
        "resume is best suited for (e.g. 'backend', 'nestjs', 'aws', 'java-spring')."
    ),
    schema=RESUME_SCHEMA,
)
