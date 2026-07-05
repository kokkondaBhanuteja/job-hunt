"""Resume services — parse the vault and manage per-company text variants."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from job_hunt.resume.parser import parse_resume_text
from job_hunt.resume.parser import parse_vault as _parse_vault
from job_hunt.storage import repo


def parse_resume_vault(vault_dir: str | Path) -> list[tuple[str, int]]:
    """Parse every supported resume in `vault_dir`. Returns [(slug, variant_id), ...]."""
    repo.init_db()
    return _parse_vault(Path(vault_dir))


def save_variant_from_text(
    slug: str,
    *,
    company: str = "",
    body: str,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Parse `body` with the LLM and upsert a text-authored résumé variant.

    Returns {"slug", "id", "company"} on success, {"error": …} on failure.
    """
    repo.init_db()
    if not body or not body.strip():
        return {"error": "body must not be empty"}
    parsed = parse_resume_text(body)
    variant_id = repo.upsert_variant_from_text(
        slug=slug,
        company=company,
        body=body,
        parsed=parsed,
        tags=tags or [],
    )
    return {"slug": slug, "id": variant_id, "company": company}


def get_variant(slug: str) -> dict[str, Any]:
    """Return slug, company, body, parsed_json, tags for a variant, or {"error": …}."""
    repo.init_db()
    row = repo.get_resume_variant_by_slug(slug)
    if row is None:
        return {"error": f"no variant with slug={slug!r}"}
    tags_raw = row["tags"]
    parsed_raw = row["parsed_json"]
    return {
        "slug": row["slug"],
        "company": row["company"],
        "body": row["body"],
        "parsed_json": json.loads(parsed_raw) if parsed_raw else None,
        "tags": json.loads(tags_raw) if tags_raw else [],
    }


def list_variants() -> list[dict[str, Any]]:
    """Return all variants as [{slug, company, tags, has_body}, ...]."""
    repo.init_db()
    rows = repo.list_resume_variants()
    result = []
    for row in rows:
        tags_val = row["tags"]
        result.append({
            "slug": row["slug"],
            "company": row["company"],
            "tags": json.loads(tags_val) if tags_val else [],
            "has_body": bool(row["body"]),
        })
    return result
