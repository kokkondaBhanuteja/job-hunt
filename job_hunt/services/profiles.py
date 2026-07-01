"""Search-profile services."""
from __future__ import annotations

from typing import Any

from job_hunt.storage import repo


def add_profile(
    *, name: str, keywords: str, location: str, pages: int = 1, **extra: Any
) -> int:
    repo.init_db()
    return repo.create_search_profile(
        name=name, keywords=keywords, location=location, pages=pages, **extra
    )


def list_profiles() -> list[dict[str, Any]]:
    repo.init_db()
    return repo.list_search_profiles()


def set_enabled(profile_id: int, enabled: bool) -> None:
    repo.init_db()
    repo.set_search_profile_enabled(profile_id, enabled)
