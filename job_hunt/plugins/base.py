"""Source plugin contract + registry.

Every job board implements `Source`. The registry lets the worker look a source up
by name, so adding a board later (LinkedIn, Lever, ...) is just a new module that
`register()`s itself — no changes to the worker. (Contract now; more impls in P5.)
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Source(Protocol):
    name: str

    def discover(
        self,
        *,
        keyword: str,
        location: str,
        pages: int = 1,
        headless: bool = True,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Crawl the board and persist new jobs. Returns {found, new, jobs}."""
        ...


_REGISTRY: dict[str, Source] = {}


def register(source: Source) -> None:
    _REGISTRY[source.name] = source


def get_source(name: str) -> Source:
    if name not in _REGISTRY:
        raise KeyError(f"unknown source '{name}' (registered: {sorted(_REGISTRY)})")
    return _REGISTRY[name]


def available_sources() -> list[str]:
    return sorted(_REGISTRY)
