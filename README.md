# job-hunt — a personal "Career OS"

A self-hosted, quality-first job-hunt platform. It discovers jobs across boards, scores
each against your résumés with an LLM, enriches to the full JD, **tailors your résumé and
drafts cover letters / recruiter outreach**, runs an **AI pre-submit review**, tracks the
interview pipeline, and reports analytics — driven from a **React web UI**, a REST API, a
CLI, or any MCP host.

**Product thesis:** be a *highly efficient human, not a bot* — 20–40 targeted, tailored
applications beat 300 generic ones. Every automation saves time, improves quality, or aids a
decision **while you keep control of what matters** (review before submit).

Runs on your machine. Local LLM (Ollama) by default = **$0**; any task can be pointed at an
API key instead.

---

## Architecture (one glance)

```
React UI ─┐
REST API ─┤
CLI      ─┼──▶  services/  (the keystone: all business logic)  ──▶ storage (Postgres | SQLite)
MCP      ─┤          │
worker   ─┘          ├── llm/      AI Gateway: provider registry + prompt library + cost log
                     ├── plugins/  source contract (naukri, remoteok, greenhouse, lever)
                     ├── browser/  the only place Playwright launches (stealth, rate-limit)
                     ├── events/   in-DB transactional outbox (the "workflow")
                     └── states.py job state machine (DISCOVERED→…→OFFER)
```

- **One `services/` layer** — CLI, API, MCP, and worker all call it; no duplicated logic.
- **Pluggable LLM ("AI Gateway", `llm/`)** — provider registry (Ollama / OpenAI-compat / stub),
  versioned prompt library, retries + fallback, and a full `llm_calls` cost/latency log.
- **Two storage backends via `DB_BACKEND`** — `postgres` (pgvector, prod) or `sqlite` (fast tests).
- **Event-driven pipeline** — an in-DB outbox + job state machine; the worker auto-advances
  `discovered → enrich → scored → …`.

## The pipeline

```
discover ─▶ enrich (full JD) ─▶ score (idempotent, JD-aware) ─▶ tailor + cover letter
        ─▶ AI review ─▶ (you approve) apply ─▶ track stages ─▶ analytics + learning
```

---

## Setup

```bash
# 1. Postgres + pgvector (the datastore) — from the repo root
docker compose up -d db                    # host port 55432

# 2. Python project — everything backend lives under backend/
cd backend
uv sync
uv run playwright install chromium         # for the browser sources

# 3. Local LLM (optional but default)
brew install ollama && brew services start ollama
ollama pull qwen2.5:7b                      # scoring/drafting
ollama pull nomic-embed-text               # semantic search (optional)

# 4. Copy any existing v0 SQLite data into Postgres (optional)
uv run python scripts/sqlite_to_postgres.py

# 5. Sanity check
DB_BACKEND=postgres uv run hunt selfcheck
```

Config lives in env (see `backend/.env.example` — copy to `backend/.env.local`):
`DB_BACKEND`, `DATABASE_URL`, per-task `LLM_<TASK>_PROVIDER/MODEL` (+ `OPENAI_API_KEY`
etc.), `NOTIFY_CHANNEL`, `EMBED_PROVIDER`, `API_TOKEN`.

## Run the platform

```bash
# API (127.0.0.1, token-authed) — prints an ephemeral token if API_TOKEN is unset
cd backend && DB_BACKEND=postgres uv run hunt serve-api

# Web UI (separate terminal, from the repo root)
cd frontend && npm install && npm run dev        # → http://localhost:5000 (paste the token in Settings)

# Background worker (scheduled discovery + event dispatch + daily report)
cd backend && DB_BACKEND=postgres uv run hunt worker
```

## CLI (`uv run hunt …`)

| Command | Does |
|---|---|
| `selfcheck` | verify DB + each task's LLM provider (local or API key) |
| `discover --source <naukri\|remoteok\|greenhouse\|lever> --keyword … [--location …]` | crawl a source |
| `enrich` | fetch full JDs for discovered jobs |
| `score` | idempotent JD-aware scoring of every job × variant |
| `top [--min-score]` | best matches |
| `tailor <job_id>` / `cover <job_id>` | JD-tailored résumé / cover letter |
| `profiles` / `add-profile …` | saved searches |
| `run-cycle` / `worker` | one discovery+scoring cycle / the long-running scheduler |
| `report [--send]` | daily summary (Telegram/Discord if configured) |
| `embed` / `semantic "query"` | pgvector semantic search (Postgres only) |
| `serve-api` / `serve-mcp` | REST API / MCP stdio server |
| `db "SELECT …"` | ad-hoc read query against the active backend |

## Testing

```bash
cd backend && uv run pytest -q      # SQLite fast path; Postgres-gated tests run if the DB is up
```

## Layout

```
backend/                Python. All backend code + its data/config/scripts/tests.
├── job_hunt/           services/ · llm/ · storage/ (db.py sqlite, pg.py postgres, repo.py façade)
│                        plugins/ · browser/ · events/ · states.py · enrich/ · scoring/
│                        resume/ · draft/ · apply/ · learn/ · embed/ · notify/
│                        worker/ · api/ · mcp_server/ · cli/
├── migrations/         numbered .sql (Postgres); SQLite schema is in storage/db.py
├── tests/              pytest suite
├── scripts/            one-off tools (SQLite→PG migration, naukri debug, launchd install)
├── config/             CSS selectors etc.
├── data/               runtime data (SQLite DB, logs, resume vault) — mostly gitignored
├── pyproject.toml      Python deps + `hunt` CLI entrypoint
└── uv.lock

frontend/               React + TS + Vite + TanStack Query (Board · Runs · Analytics · Settings)
docs/                   career-os-plan.md (architecture + build status), engineering-standards.md
docker-compose.yml      Boots the Postgres+pgvector container
```

## Cost & privacy

$0 by default (local Ollama, local Postgres). Point any hard task at an API key when you
want more quality; `llm_calls` tracks every token and dollar. The API binds to `127.0.0.1`
and requires a token even locally — it can spend credits and (later) submit applications.
