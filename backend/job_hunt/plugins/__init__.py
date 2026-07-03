"""Source plugins. Importing this package registers all built-in sources."""
from __future__ import annotations

from job_hunt.plugins import greenhouse  # noqa: F401 — registers GreenhouseSource
from job_hunt.plugins import lever  # noqa: F401 — registers LeverSource
from job_hunt.plugins import naukri  # noqa: F401 — registers NaukriSource
from job_hunt.plugins import remoteok  # noqa: F401 — registers RemoteOKSource
from job_hunt.plugins.base import Source, available_sources, get_source, register

__all__ = ["Source", "get_source", "available_sources", "register"]
