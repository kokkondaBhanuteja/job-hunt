"""Apply subsystem — ATS detection, AI pre-submit review, and (later) form-fill."""
from __future__ import annotations

from job_hunt.apply.ats import detect_ats
from job_hunt.apply.reviewer import review_application

__all__ = ["detect_ats", "review_application"]
