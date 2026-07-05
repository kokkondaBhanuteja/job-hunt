"""Source plugins. Importing this package registers all built-in sources."""
from __future__ import annotations

from job_hunt.plugins import (
    adzuna,  # noqa: F401 — registers AdzunaSource
    greenhouse,  # noqa: F401 — registers GreenhouseSource
    jobspresso,  # noqa: F401 — registers JobspressoSource
    lever,  # noqa: F401 — registers LeverSource
    naukri,  # noqa: F401 — registers NaukriSource
    remoteok,  # noqa: F401 — registers RemoteOKSource
    remotive,  # noqa: F401 — registers RemotiveSource
    weworkremotely,  # noqa: F401 — registers WeWorkRemotelySource
    workingnomads,  # noqa: F401 — registers WorkingNomadsSource
)
from job_hunt.plugins.base import Source, available_sources, get_source, register

__all__ = ["Source", "get_source", "available_sources", "register"]
