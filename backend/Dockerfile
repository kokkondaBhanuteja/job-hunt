FROM python:3.12-slim

# Install uv from the official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app/backend

# Copy dependency specs first so layer is cached on source-only changes
COPY backend/pyproject.toml backend/uv.lock ./

# Install all runtime dependencies (not the project itself yet) — cached layer
RUN uv sync --frozen --no-dev --no-install-project

# Copy source that changes more often
COPY backend/job_hunt ./job_hunt
COPY backend/migrations ./migrations
COPY backend/config ./config

# Install the project package (creates the `hunt` console-script entry-point)
RUN uv sync --frozen --no-dev

# Put the venv on PATH so we can call `hunt` and `python` directly at runtime
# without going through `uv run` (which would re-sync the environment).
ENV PATH="/app/backend/.venv/bin:$PATH"

# Default: serve the API on all interfaces so Docker port-mapping works.
# Override via compose `command:` for the worker service.
CMD ["hunt", "serve-api", "--host", "0.0.0.0", "--port", "8000"]
