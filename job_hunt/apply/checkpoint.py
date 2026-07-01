"""Crash-resumable step runner for multi-page applications.

`run_resumable` executes an ordered list of steps, persisting a checkpoint after each.
If it dies partway (browser crash, page change), a re-run resumes from the next step —
we never re-fill pages already completed. On completion the checkpoint is cleared.
"""
from __future__ import annotations

import json
from typing import Any, Callable

from job_hunt.storage import repo

# execute(step, accumulated_data) -> new_accumulated_data
Executor = Callable[[Any, dict[str, Any]], dict[str, Any]]


def run_resumable(job_id: int, steps: list[Any], execute: Executor) -> dict[str, Any]:
    """Run `steps` for a job, checkpointing after each; resume from the last checkpoint."""
    checkpoint = repo.get_checkpoint(job_id)
    start = (int(checkpoint["step"]) + 1) if checkpoint else 0
    data: dict[str, Any] = (
        json.loads(checkpoint["data"]) if checkpoint and checkpoint["data"] else {}
    )

    for index in range(start, len(steps)):
        data = execute(steps[index], data)          # may raise → checkpoint stays at index-1
        repo.save_checkpoint(job_id=job_id, step=index, data=data)

    repo.clear_checkpoint(job_id)
    return data
