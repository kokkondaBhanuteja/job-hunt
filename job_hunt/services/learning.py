"""Learning services — persist what outcomes teach us about tailoring + variants."""
from __future__ import annotations

import json
from typing import Any

from job_hunt.enums import LearningKind
from job_hunt.learn.analyze import analyze_rejection
from job_hunt.storage import repo


def learn_from_rejection(job_id: int) -> dict[str, Any]:
    """Analyze a rejection (JD vs best resume) → store the missing-keyword gap."""
    repo.init_db()
    job = repo.get_job(job_id)
    if job is None:
        return {"error": f"no job with id={job_id}"}

    variant = repo.best_scored_variant(job_id)
    resume_json = json.loads(variant["parsed_json"]) if variant else {}
    jd_text = job["description_full"] or job["description"] or ""

    result = analyze_rejection(jd_text=jd_text, resume_json=resume_json)
    learning_id = repo.save_learning(
        job_id=job_id,
        variant_id=int(variant["id"]) if variant else None,
        kind=LearningKind.REJECTION,
        payload=result,
    )
    return {"job_id": job_id, "learning_id": learning_id, **result}
