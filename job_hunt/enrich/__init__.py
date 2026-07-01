"""Enrichment: fetch the full JD for a job (and later, company research)."""
from __future__ import annotations

from job_hunt.enrich.service import enrich_job, enrich_pending

__all__ = ["enrich_job", "enrich_pending"]
