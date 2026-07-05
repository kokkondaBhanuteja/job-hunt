# Architecture — Career OS (job-hunt)

> **Purpose of this document.** A single, authoritative reference that lets an LLM agent or a new
> engineer understand the entire system — every layer, every table, every source plugin, every feature,
> and every configuration knob — without reading any other file. Every claim here was verified against
> the actual source code. Coding standards and agent rules live separately in `backend/CLAUDE.md` and
> `frontend/CLAUDE.md`.

---

## 1. What Career OS is

Career OS is a **self-hosted, local-first, single-user job-hunt platform** that automates the
mechanical parts of a job search while keeping the human in control of every decision that matters.
It runs on a developer's laptop; there is no cloud deployment and no SaaS hosting.

### Design thesis

| Principle | What it means in practice |
|---|---|
| **Local-first** | Ollama (`qwen2.5:7b` by default) runs entirely on the host — $0 in LLM costs. Cloud providers (Groq/OpenAI/Gemini) are optional drop-in replacements configured per task via env vars. |
| **Human-in-the-loop** | Every consequential action requires an explicit human confirmation: auto-fill stops at the review screen, email IMAP writes require `confirm=True`, nothing is auto-applied or auto-posted. |
| **Quality over quantity** | The pipeline scores, tailors, and drafts; it surfaces high-fit jobs and surfaces exactly what needs your attention next via the `next_best_action` rule engine. |
| **Official APIs only** | All job sources use official public APIs or authenticated user inboxes (IMAP). No LinkedIn scraping, no anti-bot evasion. |
| **Zero ops** | SQLite for development/testing, Postgres + pgvector for production. A single `make up` starts the whole stack. |

### Deployment reality

The system is designed for **two users at most** (typically one), running locally on macOS via Docker
Compose. The frontend is served by nginx on port `8770`. Ollama and browser-interactive features
(Naukri crawl, ATS auto-fill) run natively on the host — GPU passthrough into Linux containers on
macOS is painful and slow. There is no CI/CD, no cloud hosting, and no external network exposure.

---

## 2. Complete tech stack

### Backend (Python)

| Technology | Version pin | Role |
|---|---|---|
| Python | ≥ 3.12 | Language — uses `StrEnum`, `match`-free `if/elif`, modern type hint syntax |
| FastAPI | ≥ 0.138.2 | REST API server (`job_hunt/api/app.py`); all routes under `/api` with bearer-token auth |
| uvicorn[standard] | ≥ 0.49.0 | ASGI server behind FastAPI |
| Pydantic v2 | ≥ 2.13.4 | Request/response DTOs at the HTTP boundary only; internal service layer uses plain dicts |
| httpx | ≥ 0.28.1 | Sync HTTP for all API-source plugins (Adzuna, RemoteOK, Greenhouse, Lever, …) |
| Playwright | ≥ 1.60.0 | Async browser automation for Naukri crawl + ATS auto-fill |
| playwright-stealth | ≥ 2.0.3 | Browser fingerprint normalization (persistent profile, user-agent spoofing) |
| APScheduler | ≥ 3.11.3 | `BlockingScheduler` in the worker process — six named periodic/cron jobs |
| psycopg[binary] | ≥ 3.3.4 | Postgres driver (psycopg3 async/sync, binary protocol) |
| pdfplumber | ≥ 0.11.9 | PDF résumé parsing in `resume/` |
| mcp[cli] | ≥ 1.27.2 | FastMCP server that exposes all tools over stdio to MCP hosts (Claude Code, Cherry Studio, Goose) |
| python-dotenv | ≥ 1.2.2 | Loads `backend/.env.local` at process startup |
| PyYAML | ≥ 6.0.3 | Selector config loading (`config/selectors/naukri.json`) |
| uv | runtime | Package/venv manager; `pyproject.toml` is the manifest; `uv run hunt ...` is the CLI entry point |
| ruff | ≥ 0.8.0 (dev) | Linter + formatter (E, F, I, N, UP, B rule sets; line length 100/112) |
| pytest | ≥ 9.1.1 (dev) | Test runner — function-based, 70 test files in `backend/tests/` |
| stdlib: xml.etree, imaplib, email, ssl, hashlib, json, sqlite3 | stdlib | RSS parsing, IMAP reader, JSON storage, SQLite backend |

### LLM providers

| Provider | Kind | Default model | Notes |
|---|---|---|---|
| Ollama | Local | `qwen2.5:7b` | Default for all tasks; zero cost; accessed via `OLLAMA_URL` |
| Groq | Cloud (free) | `llama-3.3-70b-versatile` | OpenAI-compatible; key rotation on 429/401; falls back to Ollama on exhaustion |
| OpenAI | Cloud (paid) | `gpt-4o-mini` | OpenAI-compatible client; enabled by `OPENAI_API_KEY` |
| Gemini | Cloud (paid) | `gemini-1.5-flash` | OpenAI-compatible via Google's v1beta endpoint; enabled by `GEMINI_API_KEY` |
| Stub | Test | `stub` | Deterministic fake — used by all hermetic tests; returns hash-derived strings |

### Frontend

| Technology | Version | Role |
|---|---|---|
| React | 19.x | UI framework |
| Vite | ≥ 6.x | Build tool + dev server |
| TypeScript | ≥ 5.7, `strict: true` | All frontend code; no `any` allowed |
| TanStack Query | ≥ 5.x | Server state — every remote call goes through `useQuery`/`useMutation` |
| Tailwind CSS | v4 | Utility-first styling; `@tailwindcss/vite` plugin |
| shadcn/ui | vendored | Component library built on Radix UI primitives; primitives live in `src/components/ui/` |
| Radix UI | various | Accessible headless primitives underlying shadcn |
| react-hook-form + zod + @hookform/resolvers | form stack | Form state + schema validation |
| lucide-react | ≥ 1.x | Icon set |
| sonner | ≥ 2.x | Toast notifications |
| vitest | ≥ 3.x | Frontend test runner |
| History API (custom router) | — | Clean-URL client router in `src/lib/router.tsx` (~90 LOC); no React Router |

### Infrastructure

| Technology | Role |
|---|---|
| Docker Compose | Orchestrates `db`, `api`, `worker`, `frontend` services |
| pgvector/pgvector:pg16 | Postgres 16 + pgvector extension for semantic search |
| nginx (inside `frontend` image) | Serves built React app; proxies `/api` to the backend; injects the bearer token on every `/api` request via `envsubst` |
| SQLite 3 | Development and test datastore (zero-infra; `data/jobhunt.db`) |
| Telegram Bot API / Discord Webhook | Optional notification channels for the daily report |
| Makefile | Developer shortcuts: `make up`, `make down`, `make logs`, `make host-cli`, `make test`, `make clean` |

---

## 3. Architecture and layering

The central design decision is the **thin-adapter principle**: every entrypoint is a thin adapter
over the shared `services/` layer. Business logic never lives in the API handler, CLI command, MCP
tool, or worker job — it lives in the service function that all of them call. This means adding
a new entrypoint (e.g. a Slack bot) requires only a new adapter file, not a copy of any logic.

```mermaid
flowchart TB
    subgraph Entry["Entrypoints — thin adapters only"]
        UI["React Web UI\n(browser → nginx :8770)"]
        API["FastAPI REST\njob_hunt/api/app.py\n(127.0.0.1:8000)"]
        CLI["hunt CLI\njob_hunt/cli/main.py"]
        MCP["MCP server\njob_hunt/mcp_server/server.py\n(stdio)"]
        WK["APScheduler worker\njob_hunt/worker/scheduler.py"]
    end

    SVC["job_hunt/services/  ← the keystone\n27 modules · every business rule lives here\nreturns plain dicts · {error:…} on failure"]

    UI -->|"Bearer token /api/*"| API
    API --> SVC
    CLI --> SVC
    MCP --> SVC
    WK --> SVC

    subgraph Domain["Domain modules — called by services"]
        PLUG["plugins/ — 14 source adapters"]
        LLM["llm/ — AI Gateway\nregistry · client · prompts · providers"]
        SCORE["scoring/match.py — idempotent scorer"]
        RESUME["resume/ — LaTeX/PDF parser"]
        DRAFT["draft/ — cover/outreach/messages"]
        APPLY["apply/ — ATS detect + form-fill + answerer + reviewer"]
        EMAIL["email/reader.py — stdlib IMAP, read-only"]
        EMBED["embed/embedder.py — text→vector"]
        NOTIFY["notify/ — Telegram / Discord / null"]
        BROWSER["browser/manager.py — Playwright managed contexts"]
        EVENTS["events/bus.py — in-DB transactional outbox"]
        STATES["states.py — job state machine"]
        ENRICH["enrich/ — full-JD fetcher"]
        LEARN["learn/analyze.py — rejection analysis"]
    end

    SVC --> PLUG & LLM & SCORE & RESUME & DRAFT & APPLY
    SVC --> EMAIL & EMBED & NOTIFY & BROWSER & EVENTS & STATES & ENRICH & LEARN

    subgraph Storage["Storage — storage/repo.py façade"]
        REPOFA["repo.py routes to sqlite or postgres by DB_BACKEND env"]
        SQLITE["storage/db.py\nSQLite · inline SCHEMA string\ntest + dev backend"]
        PG["storage/pg.py\nPostgres + pgvector\npsycopg3 · numbered migrations\nprod backend"]
    end

    SVC --> REPOFA
    EVENTS --> REPOFA
    STATES --> REPOFA
    REPOFA --> SQLITE
    REPOFA --> PG

    LLM -->|"per-task routing"| OLL["Ollama (local, default)"]
    LLM -->|"optional"| CLOUD["Groq / OpenAI / Gemini"]
    EMAIL -->|"IMAP + app password"| GMAIL["User's email server\n(read-only sync; writes only on confirm)"]
```

### The storage façade

`storage/repo.py` selects the backend at import time from `DB_BACKEND` (default `sqlite`). Both
`db.py` and `pg.py` expose **exactly the same function surface** — every SQL helper is duplicated
and kept in sync. Callers import only from `repo`; they never reference `db` or `pg` directly.
Embeddings (pgvector) are Postgres-only: the corresponding `db.py` functions raise
`NotImplementedError` with an explanatory message.

---

## 4. The services keystone

`job_hunt/services/__init__.py` re-exports every public service function in `__all__`. There are
currently **27 service modules** under `job_hunt/services/`. The table below maps each module to its
exported functions and purpose.

| Module | Key exported functions | Purpose |
|---|---|---|
| `analytics.py` | `dashboard`, `funnel_metrics`, `variant_performance`, `daily_report_text`, `send_daily_report`, `send_test_notification` | Application funnel metrics, LLM-cost dashboard, daily digest |
| `answers.py` | `add_answer_template`, `list_answer_templates`, `suggest_answer` | Reusable screening-question answer bank; fuzzy match on question pattern |
| `applicant.py` | `get_applicant`, `set_applicant` | Singleton applicant profile (name, email, phone, visa, CTC, years of experience, etc.) |
| `applications.py` | `log_application`, `advance_stage` | Record that an application was submitted; advance interview pipeline stage |
| `apply.py` | `review_application` | AI pre-submit quality gate (LLM compares résumé + cover + answers against JD; returns `{ready, issues}`) |
| `apply_policy.py` | `get_policy`, `list_ready_to_apply` | Singleton apply-policy filter (min score, keywords, seniority, remote-only); surfaces ready-to-apply candidates |
| `brief.py` | `brief_for_job` | LLM-generated interview-prep brief for a job (structured: role context, likely questions, focus areas) |
| `companies.py` | `get_company`, `company_history` | Company research cache lookup; full engagement history for a company |
| `content.py` | `generate_post`, `list_posts`, `set_post_status`, `generate_and_notify_post` | AI-drafted tech post drafts grounded in HN/dev.to topics; never auto-posts |
| `context.py` | `get_context`, `set_context` | Singleton career-context blob (Markdown or JSON); prepended to every LLM prompt |
| `crm.py` | `add_contact`, `list_contacts` | Recruiter/contact CRM (name, role, persona, email guess, LinkedIn) |
| `discovery.py` | `discover`, `discover_naukri` | Dispatch to a source plugin by name; Naukri-specific entry point (headless/headful mode) |
| `drafting.py` | `tailor_for_job`, `draft_cover_for_job`, `draft_outreach_for_job`, `draft_message_for_job`, `list_drafts` | LLM tailoring of résumé to a JD; cover letter and all message-draft kinds |
| `email_actions.py` | `propose_action`, `confirm_action`, `dismiss_action` | Human-confirmed IMAP actions on triaged emails (draft reply / label / archive) |
| `email_triage.py` | `sync_inbox`, `structure_pending`, `list_inbox`, `get_email` | IMAP incremental sync + LLM structuring pass; email→job/application linking |
| `enrichment.py` | `enrich_pending_jobs` | Fetch full JD text for discovered jobs that only have a snippet |
| `intelligence.py` | `explain_score`, `next_best_action`, `skill_gap` | Career Intelligence Engine: per-requirement score breakdown, rule-based next action, cross-job skill-gap aggregation |
| `learning.py` | `learn_from_rejection` | LLM analyzes a rejected application for missing keywords; stores in `learnings` |
| `naukri_refresh.py` | `draft_profile_refresh`, `refresh_reminder` | LLM-drafted Naukri headline/summary/skills for manual copy-paste; weekly reminder notification |
| `profiles.py` | `add_profile`, `list_profiles`, `set_enabled` | Search profile CRUD (keyword × location × pages; enable/disable) |
| `resumes.py` | `parse_resume_vault`, `list_variants`, `get_variant`, `save_variant_from_text`, `list_resume_vault` | Parse LaTeX/PDF vault; manage résumé variants (file-backed or text-authored) |
| `review.py` | `list_top_matches`, `list_board`, `get_job`, `list_resume_vault` | Board data: top-scored jobs, Kanban view, individual job detail with all scores |
| `runs.py` | `run_discovery`, `list_runs`, `get_run`, `request_cancel` | Background run lifecycle management; cancel flag |
| `scoring.py` | `score_pending` | Dispatch the LLM scorer over all unscored (job × variant) pairs; idempotent |
| `search_prefs.py` | `get_search_prefs`, `set_search_prefs` | Store a Markdown preferences blob; LLM parses it into `search_profiles` rows |
| `semantic.py` | `embed_jobs`, `semantic_match`, `similar_successful` | Compute and store job embeddings; semantic free-text search; outcome-aware similarity |
| `watchlist.py` | `add_company`, `list_watch`, `set_enabled`, `remove` | Company ATS watchlist CRUD — companies whose boards the worker polls automatically |

---

## 5. Domain modules

### 5.1 Plugins — 14 job sources

Each plugin is a Python file in `job_hunt/plugins/` that calls `register()` once. Importing the
package (`from job_hunt import plugins`) registers all 14 sources automatically.

| Plugin | Source name | Transport | Full JD at discovery? | Notes |
|---|---|---|---|---|
| `adzuna.py` | `adzuna` | httpx JSON API (official) | Yes → lands ENRICHED | Free API key required (`ADZUNA_APP_ID`, `ADZUNA_APP_KEY`); `ADZUNA_COUNTRY` selects market |
| `amazon.py` | `amazon` | httpx JSON API (public) | Yes → lands ENRICHED | `amazon.jobs/en/search.json` — no auth |
| `ashby.py` | `ashby` | httpx JSON API (per-company board token) | Yes → lands ENRICHED | `api.ashbyhq.com/posting-api/job-board/{token}` |
| `google.py` | `google` | httpx JSON API (public) | Yes → lands ENRICHED | `careers.google.com` v3 API; may require browser session on some networks |
| `greenhouse.py` | `greenhouse` | httpx JSON API (per-company board token) | Yes → lands ENRICHED | `boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true` |
| `jobspresso.py` | `jobspresso` | httpx RSS/XML (WP Job Manager feed) | Yes → lands ENRICHED | `jobspresso.co/feed/?post_type=job_listing` |
| `lever.py` | `lever` | httpx JSON API (per-company token) | Yes → lands ENRICHED | `api.lever.co/v0/postings/{company}?mode=json` |
| `naukri.py` | `naukri` | Playwright browser (RPA, persistent profile) | No → snippet only, enrich step needed | Thin adapter over `sources/naukri.py`; full Playwright stealth crawl |
| `remoteok.py` | `remoteok` | httpx JSON API (public) | Yes → lands ENRICHED | `remoteok.com/api` |
| `remotive.py` | `remotive` | httpx JSON API (public) | Yes → lands ENRICHED | ≤4 calls/day limit; NOT in the worker's fast loop |
| `weworkremotely.py` | `weworkremotely` | httpx RSS/XML | Yes → lands ENRICHED | `weworkremotely.com/remote-jobs.rss` |
| `workable.py` | `workable` | httpx JSON API (per-company account slug) | Yes → lands ENRICHED | `apply.workable.com/api/v1/widget/accounts/{token}?details=true` |
| `workday.py` | `workday` | httpx JSON API (per-company CXS endpoint) | Yes → lands ENRICHED | Public endpoint; no login; 4-hour politeness throttle per token |
| `workingnomads.py` | `workingnomads` | httpx RSS/XML | Yes → lands ENRICHED | `workingnomads.com/jobsrss` |

**Plugin transport categories:**
- **httpx JSON API — per-company board token** (Ashby, Greenhouse, Lever, Workable, Workday): used for the company **watchlist** feature — the worker polls these automatically when a company is in `company_watchlist`.
- **httpx JSON API — global search** (Adzuna, Amazon, Google, RemoteOK, Remotive): used in the worker's `api_discovery` loop.
- **httpx RSS/XML** (Jobspresso, WeWorkRemotely, WorkingNomads): simple XML parse, no auth.
- **Playwright browser** (Naukri): full RPA — persisted sessions in `data/sessions/naukri/`, stealth options, hot-patchable CSS selectors via `config/selectors/naukri.json`.

API sources that return the full JD skip the browser enrich step: they are stored with
`description_full` already set and their state transitions immediately to `ENRICHED` via
`_persist.py::persist_full_jd_job`.

### 5.2 AI Gateway (`llm/`)

The `llm/` package is a complete AI gateway. Services never call a provider directly — they call
`chat()` or `chat_json()` from `llm/client.py`.

**Registry** (`llm/registry.py`): resolves `(provider, model)` from environment variables for a
named task. Per-task env pattern: `LLM_<TASK>_PROVIDER` / `LLM_<TASK>_MODEL`. Optional fallback:
`LLM_<TASK>_FALLBACK_PROVIDER` / `LLM_<TASK>_FALLBACK_MODEL`. Recognized tasks: `scoring`,
`drafting`, `tailoring`, `email_structure`. Legacy aliases `OLLAMA_SCORING_MODEL` /
`OLLAMA_DRAFTING_MODEL` are honored as fallbacks.

**Defined LLM tasks** (`enums.py::LLMTask`):

| Task | Default use |
|---|---|
| `scoring` | Job × résumé variant fit score (0-100) |
| `drafting` | Cover letters, outreach, thank-you/follow-up/negotiation messages, AI review |
| `tailoring` | JD-tailored résumé emphasis pass |
| `email_structure` | Inbox email category + field extraction |

**Providers** (`llm/providers/`):
- `OllamaProvider` (`providers/ollama.py`): HTTP to `OLLAMA_URL`; detects if alive; lists installed models for `selfcheck`.
- `OpenAICompatProvider` (`providers/openai_compat.py`): single client for OpenAI, Groq, and Gemini — all share the OpenAI wire format. Groq adds **key rotation** (comma-separated `GROQ_API_KEYS`) and **Ollama fallback** on exhaustion.
- `StubProvider` (`providers/stub.py`): deterministic fake for tests; never makes network calls.

**Client** (`llm/client.py`): `chat(prompt, *, task, system, json_schema, temperature, timeout_s,
prompt_name, prompt_version)` — retries up to `LLM_MAX_ATTEMPTS` (default 2) on transient
`LLMError` with exponential backoff (`LLM_BACKOFF_BASE_S` default 0.5s), then tries the fallback
provider once. Every attempt (success or failure) is logged to `llm_calls` — best-effort,
never raises.

`chat_json(prompt, *, schema, ...)` — returns parsed, schema-validated JSON. On invalid output it
sends a **repair turn** ("your previous response was invalid: …") and retries up to `LLM_MAX_ATTEMPTS`.
Falls back to regex extraction of the first `{…}` block from prose-wrapped responses.

**Prompt Library** (`llm/prompts.py`): all prompts are `Prompt(name, version, system, schema)` frozen
dataclasses. Bumping `version` means `llm_calls.prompt_version` changes, enabling A/B analysis in
the cost dashboard. Named prompts include `SCORING`, `TAILORING`, `DRAFTING`, `EMAIL_STRUCTURE`,
`EXPLAIN_SCORE`, `APPLICATION_REVIEW`, and others.

**Cost log**: every call records `prompt_tokens`, `completion_tokens`, and `cost` (USD, from a
hard-coded `_COST_PER_1K` table extensible via `LLM_COST_TABLE` JSON env). Local/Ollama calls log
`cost=0`. Unknown paid models log a one-time warning.

### 5.3 Scoring (`scoring/match.py`)

Idempotent LLM scorer. For every eligible (job, variant) pair, computes a hash over `(jd_text,
provider/model)`; if the hash matches the stored `input_hash`, the call is skipped (nothing billed,
nothing overwritten). Re-enrichment or a model switch both invalidate the hash and trigger a rescore.
Scores are `{fit_score: 0-100, confidence: 0-100, reasoning: "…"}` via `chat_json` with
`SCORING` prompt. Returns the best (highest) variant for the job. Emits `JOB_SCORED` event on first
score.

Score thresholds (`enums.py::Score`): `DEFAULT_MIN_MATCH = 70`, `APPLY_THRESHOLD = 80`,
`STRONG = 85`.

### 5.4 Resume (`resume/`)

Parses the user's résumé vault (`data/resumes/`) — LaTeX files via regex extraction, PDFs via
pdfplumber. Produces a structured JSON representation stored in `resume_variants.parsed_json`.
Variants have a `slug` (e.g. `backend-node`), optional `company` (for company-specific variants),
optional `source_path` (for file-backed variants), and optional `body` (for text-authored variants).

### 5.5 Draft (`draft/`)

LLM-powered drafting for all messaging kinds defined by `DraftKind`:
`cover`, `outreach`, `thank_you`, `follow_up`, `negotiation`. Each draft is stored in the `drafts`
table with its `kind`. The `tailor_for_job` service uses `TAILORING` prompt to produce a
JD-emphasized résumé stored in `tailored_resumes`. The `best_scored_variant_for_company` query
prioritizes company-specific variants when tailoring.

### 5.6 Apply (`apply/`)

Four modules:
- **`ats.py`**: pure URL-pattern ATS detection (host substring match). Recognizes Greenhouse, Lever,
  Workday, Ashby, SmartRecruiters, iCIMS, Naukri, RemoteOK.
- **`formfill.py`**: the main entry point — resolves stored data from `applicant_profile` +
  `tailored_resumes` + `answer_templates`, opens the job's ATS form via Playwright's
  `managed_context`, fills every field it can, and **stops at the review screen without submitting**.
  Crash-resumable via `apply_checkpoints` table.
- **`answerer.py`**: LLM-generates answers to novel screening questions not covered by stored templates.
- **`reviewer.py`**: AI pre-submit review — compares résumé + cover + answers against the JD,
  returns `{ready: bool, issues: [str]}`. Uses `APPLICATION_REVIEW` prompt; routes through the
  `drafting` task (can point to a stronger model).

### 5.7 Email (`email/reader.py`)

Read-only stdlib IMAP reader — zero new dependencies (`imaplib`, `email`, `ssl`, `html.parser`).
Uses `BODY.PEEK` so fetching never sets `\Seen`. Implements UID-based incremental sync with
`uidvalidity` checking (stored in `email_sync_state`). Produces plain-text body from multipart and
HTML messages. Decodes RFC 2047 encoded headers.

Email actions (`services/email_actions.py`) follow a propose→confirm→execute gate:
1. `propose_action(email_id, kind)` — stores an `email_actions` row with state `PROPOSED`.
2. `confirm_action(email_id, confirm=True)` — transitions to `CONFIRMED` then executes the IMAP
   write (only if `confirm=True`). Without `confirm=True`, returns the proposal for human review.
3. `dismiss_action` — marks `DISMISSED`, no IMAP access.

Action kinds: `draft_reply`, `apply_label`, `archive`.

### 5.8 Content (`content/`)

Generates unique tech post drafts (LinkedIn/X style) by fetching trending topics from Hacker News or
dev.to. Stores drafts in `content_posts` with `PostStatus`: `draft → posted | dismissed`. The worker
runs this every 3 days and sends a notification. **Never auto-posts** — the user pastes/posts manually.

### 5.9 Embed / semantic search (`embed/embedder.py`)

Converts job descriptions into dense vectors via Ollama (`nomic-embed-text`, 768-dim) or a
deterministic stub. Stores embeddings in Postgres's `vector(768)` column (migration 0008). Provides:
- `embed_jobs(limit)` — embed all un-embedded jobs.
- `semantic_match(query)` — free-text search against all job embeddings via pgvector cosine distance.
- `similar_successful(job_id)` — find jobs with similar embeddings that reached interview/HR/offer
  stage (outcome-aware similarity for the Career Intelligence Engine).

Embedding is Postgres-only. The `db.py` stubs raise `NotImplementedError`.

### 5.10 Notify (`notify/`)

Three backends selected by `NOTIFY_CHANNEL`: `telegram`, `discord`, `none` (default). The daily
report is assembled by `notify/report.py::build_daily_report` and dispatched by the appropriate
backend. `send_test_notification` is available via CLI and the MCP server for verification.

### 5.11 Browser (`browser/manager.py`)

`managed_context(site)` is an async context manager that yields a stealthed Playwright
`BrowserContext` backed by a persistent profile in `data/sessions/<site>/`. Centralizes launch
options (stealth settings, viewport, timeout). Uses `browser/ratelimit.py` for per-source politeness
throttling (`SCRAPE_MIN_INTERVAL_S`, default 2.0s). Naukri crawl uses this; ATS auto-fill also uses
this. The browser always runs on the host (never inside Docker).

### 5.12 Events + states (`events/bus.py`, `states.py`)

**Transactional outbox** (`events/bus.py`): domain events are written to the `events` table inside
the same transaction as the state change that produced them — no external broker. The worker drains
unprocessed events every `DISPATCH_INTERVAL_SEC` (default 30s) by calling `dispatch_pending(handlers)`.
A handler that keeps failing is retried up to `MAX_EVENT_RETRIES = 5`; on exhaustion, `dead_at` is
set (dead-lettered) and the event is skipped so it cannot freeze the queue.

**State machine** (`states.py`): `ALLOWED_TRANSITIONS` is the authoritative graph. `transition_job()`
validates, writes an audit row to `job_transitions`, updates `jobs.state`, and appends the state's
domain event — all atomically via `repo.apply_transition` (one `connect()` = one transaction).
`advance_if_legal` is a no-op variant used by artifact-producing services that don't know the exact
current state.

### 5.13 Sources / Naukri (`sources/naukri.py`)

The Naukri crawler is a full Playwright RPA implementation:
- Persistent browser profile (`data/sessions/naukri/`) that can hold a logged-in session.
- Default CSS selectors in `DEFAULT_SELECTORS` (hot-patchable via `config/selectors/naukri.json` for
  when Naukri reshuffles its markup — no code change needed).
- `crawl_sync` returns listing cards; `fetch_job_description_sync` returns the full JD (called by
  the enrich step). Both run the async Playwright code via `asyncio.run`.
- `sources/dedup.py` provides `dedup_hash(company, normalized_title)` — the cross-source dedup key.
- `sources/login.py` provides one-time interactive login persistence (also supports foundit).

---

## 6. Data model

### 6.1 Dual backend

| Backend | File | When used | Schema mechanism |
|---|---|---|---|
| SQLite | `storage/db.py` | Tests, local dev (`DB_BACKEND=sqlite`) | Inline `SCHEMA` string (`CREATE TABLE IF NOT EXISTS` + `CREATE INDEX IF NOT EXISTS`). `_migrate()` applies `ALTER TABLE ADD COLUMN IF NOT EXISTS` for columns added after a DB was created. A 12-step table rebuild removes `NOT NULL` from `resume_variants.source_path` on pre-0024 DBs. |
| Postgres | `storage/pg.py` | Production (`DB_BACKEND=postgres`) | Numbered migration files `migrations/00NN_*.sql`, applied idempotently by `init_db()`. 24 migrations, 0001–0024. |

### 6.2 Table inventory

Every table that exists in both `db.py::SCHEMA` and the Postgres migrations:

| Table | Key columns | Purpose |
|---|---|---|
| `resume_variants` | `slug` (unique), `source_path`, `parsed_json`, `tags`, `company`, `body`, `updated_at` | User's résumé variants; file-backed (`.tex`/`.pdf`) or text-authored |
| `jobs` | `id`, `dedup_hash` (unique), `source`, `title`, `company`, `location`, `description`, `description_full`, `enriched_at`, `apply_url`, `discovered_at`, `state`, `status` | Every discovered job; deduped by `sha1(company|normalized_title)` |
| `scores` | `job_id`, `variant_id` (unique pair), `fit_score`, `confidence`, `reasoning`, `scored_against`, `input_hash`, `provider_model` | One row per (job, variant) — idempotency via `input_hash` |
| `applications` | `job_id` (unique), `variant_id`, `cover_letter`, `applied_at`, `reply_type`, `reply_notes`, `stage` | Jobs the user applied to (or skipped/saved); one row per job |
| `contacts` | `company`, `name` (unique pair), `role`, `persona`, `email_guess`, `linkedin_url`, `notes` | Recruiter/contact CRM |
| `outreach` | `contact_id`, `job_id`, `template_slug`, `subject`, `body`, `mailto_url`, `drafted_at`, `sent_at` | Outreach messages drafted toward a contact |
| `runs` | `id`, `started_at`, `finished_at`, `sources`, `jobs_found`, `jobs_new`, `status`, `heartbeat_at`, `cancel_requested`, `log` | One row per pipeline run; cooperative cancel via `cancel_requested` flag |
| `job_transitions` | `job_id`, `from_state`, `to_state`, `reason`, `created_at` | Immutable audit trail of every state machine transition |
| `events` | `id`, `type`, `class`, `payload`, `created_at`, `processed_at`, `retry_count`, `dead_at` | In-DB transactional outbox; `dead_at` = dead-lettered after 5 failures |
| `companies` | `name` (unique), `size`, `funding_stage`, `tech`, `glassdoor`, `notes`, `fetched_at` | Company research cache |
| `answer_templates` | `question_pattern`, `answer_text`, `tags`, `created_at` | Reusable screening-question answers |
| `user_context` | `id = 1` (singleton), `content`, `format` | Career context blob (Markdown or JSON) injected into every LLM prompt |
| `search_prefs` | `id = 1` (singleton), `content`, `updated_at` | Raw Markdown search preferences; LLM parses these into `search_profiles` |
| `applicant_profile` | `id = 1` (singleton), `first_name`, `last_name`, `email`, `phone`, `location`, `linkedin_url`, `github_url`, `portfolio_url`, `work_authorization`, `needs_sponsorship`, `willing_to_relocate`, `notice_period`, `expected_ctc`, `current_ctc`, `years_experience`, `referral_source`, `extra` | Standing answers for application forms; one active row |
| `learnings` | `job_id`, `variant_id`, `kind` (`rejection`/`interview`/`explanation`/`alert`), `payload`, `created_at` | Outcome-derived insights fed back into tailoring and skill-gap analysis |
| `tailored_resumes` | `job_id`, `variant_id` (unique pair), `content`, `created_at` | LLM-tailored résumé (Markdown) per (job, variant) |
| `apply_checkpoints` | `job_id` (unique), `step`, `data`, `updated_at` | Crash-resumable ATS form-fill progress |
| `submitted_resumes` | `job_id`, `variant_id`, `content`, `submitted_at` | Immutable snapshot of exactly what résumé was submitted |
| `drafts` | `job_id`, `kind` (cover/outreach/thank_you/follow_up/negotiation), `body`, `status`, `created_at` | Generated drafts; multiple per job per kind |
| `search_profiles` | `name` (unique), `keywords`, `location`, `pages`, `exclusions`, `min_salary`, `companies_include`, `companies_exclude`, `remote_only`, `min_yoe`, `enabled`, `created_at` | Saved searches; the worker runs discovery for each enabled profile |
| `llm_calls` | `task`, `provider`, `model`, `prompt`, `response`, `prompt_tokens`, `completion_tokens`, `cost`, `latency_ms`, `ok`, `error`, `prompt_name`, `prompt_version`, `created_at` | Observability log of every LLM call; powers the cost dashboard |
| `email_messages` | `mailbox`, `uid` (unique with mailbox), `message_id` (unique), `from_addr`, `from_name`, `subject`, `received_at`, `snippet`, `body_text`, `category`, `extracted`, `company_id`, `job_id`, `application_id`, `action_state`, `structured_at` | Triaged inbound emails; linked to jobs/applications |
| `email_sync_state` | `mailbox` (PK), `uidvalidity`, `last_uid`, `updated_at` | Per-mailbox IMAP cursor (incremental sync) |
| `email_actions` | `email_id`, `kind` (draft_reply/apply_label/archive), `payload`, `state` (proposed/confirmed/executed/failed/dismissed), `created_at`, `executed_at` | Proposed and executed IMAP actions |
| `content_posts` | `topic`, `source_url`, `body`, `status` (draft/posted/dismissed), `created_at` | AI-drafted tech post drafts |
| `apply_policy` | `id = 1` (singleton), `policy` (JSON), `updated_at` | Apply-policy criteria (min score, must-have/avoid keywords, seniority, remote-only) |
| `company_watchlist` | `company`, `ats`, `board_token`, `enabled`, `created_at` | Companies whose ATS boards the worker polls automatically |

### 6.3 Postgres migrations (0001–0024)

| Migration | Description |
|---|---|
| `0001_init` | Initial Postgres schema — port of the v0 SQLite schema (jobs, scores, applications, contacts, outreach, runs, resume_variants) |
| `0002_state_events_runs` | Job state machine (`jobs.state`), in-DB event outbox (`events`), run lifecycle columns |
| `0003_search_profiles` | `search_profiles` table (saved searches) |
| `0004_enrichment_idempotent_scoring` | `jobs.description_full`, `jobs.enriched_at`; idempotency columns on `scores` (`scored_against`, `input_hash`, `provider_model`) |
| `0005_drafting` | `tailored_resumes` and `drafts` tables |
| `0006_application_stage` | `applications.stage` column (OA/interview/HR/offer funnel) |
| `0007_learnings` | `learnings` table (rejection/interview outcomes) |
| `0008_embeddings` | `CREATE EXTENSION vector`; `embedding vector(768)` on `jobs` and `resume_variants`; cosine distance function |
| `0009_answer_templates` | `answer_templates` table |
| `0010_companies` | `companies` table (research cache) |
| `0011_apply` | `apply_checkpoints` and `submitted_resumes` tables |
| `0012_event_dead_letter` | `events.retry_count` and `events.dead_at` columns |
| `0013_fk_indexes` | Indexes on FK columns used by JOINs / `ON DELETE CASCADE` |
| `0014_llm_call_prompt_version` | `llm_calls.prompt_name` and `llm_calls.prompt_version` |
| `0015_user_context` | `user_context` singleton table |
| `0016_applicant_profile` | `applicant_profile` singleton table |
| `0017_email_triage` | `email_messages` and `email_sync_state` tables |
| `0018_email_actions` | `email_actions` table |
| `0019_draft_kinds` | Expand `drafts.kind` CHECK to include `thank_you`, `follow_up`, `negotiation` |
| `0020_search_prefs` | `search_prefs` singleton table |
| `0021_content_posts` | `content_posts` table |
| `0022_apply_policy` | `apply_policy` singleton table |
| `0023_company_watchlist` | `company_watchlist` table |
| `0024_variant_company_body` | `resume_variants.source_path` becomes nullable; adds `company` and `body` columns (text-authored variants) |

---

## 7. The job lifecycle

### 7.1 Pipeline overview

```mermaid
flowchart LR
    MD["Search prefs\n(.md file)"]
    |"LLM parses\ninto profiles"| PROF["search_profiles rows"]

    PROF -->|"worker every 180min\n(active hours only)"| DISC["discover\n— source plugins"]
    DISC -->|"JOB_DISCOVERED event"| ENRICH["enrich\n— fetch full JD"]
    ENRICH -->|"JOB_ENRICHED event"| SCORE["score\n— LLM fit 0-100\nper variant pair"]
    SCORE -->|"JOB_SCORED event"| TAILOR["tailor résumé\n+ draft cover/messages"]
    TAILOR -->|"RESUME_TAILORED event"| REVIEW["AI pre-submit\nreview"]
    REVIEW --> APPLY["human applies\nATS auto-fill\nstops at review screen"]
    APPLY -->|"APPLICATION_SUBMITTED event"| TRACK["track stage\nOA→interview→HR\n→offer/rejected"]
    TRACK --> LEARN["learn from outcome\n→ skill-gap analysis"]

    INBOX["Gmail IMAP\ntriage + actions"] -.->|"links email to job/application"| TRACK
```

API-source plugins (Adzuna, RemoteOK, Greenhouse, Lever, etc.) persist jobs already-enriched —
they skip the browser enrich step and enter the pipeline at `ENRICHED`.

### 7.2 `JobState` state machine

States are in `enums.py::JobState`. Transitions live in `states.py::ALLOWED_TRANSITIONS`. Every
transition is validated, audited in `job_transitions`, and emits a domain event — all in one transaction.

```mermaid
stateDiagram-v2
    [*] --> DISCOVERED : scrape / persist_full_jd_job

    DISCOVERED --> ENRICHED : enrich step
    DISCOVERED --> SCORED : fast-path (API source, no enrich needed)
    DISCOVERED --> ARCHIVED : below threshold
    DISCOVERED --> WITHDRAWN : user decision

    ENRICHED --> SCORED : scoring pass
    ENRICHED --> ARCHIVED
    ENRICHED --> WITHDRAWN

    SCORED --> TAILORING_READY : tailor_for_job
    SCORED --> ARCHIVED : below threshold
    SCORED --> DEFERRED : wait / referral / salary unknown
    SCORED --> WITHDRAWN

    TAILORING_READY --> DRAFTED : draft_cover_for_job
    TAILORING_READY --> DEFERRED
    TAILORING_READY --> ARCHIVED
    TAILORING_READY --> WITHDRAWN

    DRAFTED --> REVIEW_PENDING : package assembled
    DRAFTED --> DEFERRED
    DRAFTED --> WITHDRAWN

    REVIEW_PENDING --> APPLIED : human applies
    REVIEW_PENDING --> DEFERRED
    REVIEW_PENDING --> ARCHIVED
    REVIEW_PENDING --> WITHDRAWN

    APPLIED --> OA
    APPLIED --> INTERVIEW
    APPLIED --> REJECTED
    APPLIED --> WITHDRAWN

    OA --> INTERVIEW
    OA --> REJECTED
    OA --> WITHDRAWN

    INTERVIEW --> HR
    INTERVIEW --> OFFER
    INTERVIEW --> REJECTED
    INTERVIEW --> WITHDRAWN

    HR --> OFFER
    HR --> REJECTED
    HR --> WITHDRAWN

    OFFER --> WITHDRAWN

    ARCHIVED --> TAILORING_READY : un-archive
    ARCHIVED --> WITHDRAWN

    DEFERRED --> TAILORING_READY : revive
    DEFERRED --> ARCHIVED
    DEFERRED --> WITHDRAWN

    REJECTED --> [*]
    WITHDRAWN --> [*]
```

`CLOSED_STATES` (excluded from top-matches): `APPLIED`, `OA`, `INTERVIEW`, `HR`, `OFFER`,
`REJECTED`, `ARCHIVED`, `WITHDRAWN`, `DEFERRED`.

### 7.3 Event outbox

Domain events emitted by state transitions:

| State entered | Event type |
|---|---|
| `DISCOVERED` | `job.discovered` |
| `ENRICHED` | `job.enriched` |
| `SCORED` | `job.scored` |
| `TAILORING_READY` | `resume.tailored` |
| `DRAFTED` | `draft.generated` |
| `APPLIED` | `application.submitted` |
| `OA`, `INTERVIEW`, `HR`, `OFFER` | `interview.updated` |

Infra events (no handler, for monitoring): `run.started`, `run.finished`, `scrape.blocked`,
`rate_limit.reached`.

The worker's `dispatch` job calls `events/bus.py::dispatch_pending(handlers)` every 30s. Handlers
for `job.scored` can trigger automatic enrichment or notifications. A handler failing 5 times is
dead-lettered (`dead_at` set) and never re-tried.

---

## 8. Feature catalog

### Multi-source discovery and fast worker loop

The APScheduler worker runs two discovery loops:
1. **Slow loop** (`discovery`, every 180min, active hours only): runs all enabled `search_profiles`
   across the browser-sourced and configurable sources. Respects `WORKER_DAILY_CAP` (default 30 runs
   per day) and `WORKER_ACTIVE_START`/`WORKER_ACTIVE_END` time gates (default 09:30–21:00 local time).
2. **Fast loop** (`api_discovery`, every 20min, no active-hours gate): polls the API sources listed
   in `WORKER_API_SOURCES` (default: remoteok, adzuna, weworkremotely, workingnomads, jobspresso,
   amazon, google) — cheap httpx calls, no browser, no pacing needed.

Modules: `worker/scheduler.py`, `worker/runner.py`, `worker/config.py`, `worker/pacing.py`.

### Company watchlist (ATS board polling)

The `company_watchlist` table stores `(company, ats, board_token, enabled)` entries. The worker
polls each enabled entry's ATS board API automatically, discovering new postings from watched
companies. Supported ATS platforms: Greenhouse, Lever, Ashby, Workable, Workday (and any other
plugin with a per-company board-token API). Managed via `hunt watch add|list|rm` or the Watchlist
panel in the Settings page.

Modules: `services/watchlist.py`, `plugins/greenhouse.py` (and other per-company ATS plugins).

### Instant match alerts

When a job is scored above the configured threshold and the user has a notification channel set up,
the `analytics` service / daily report surfaces it. The `learnings` table stores `LearningKind.ALERT`
dedup markers so the same high-score job is not alerted twice.

### Apply policy and ready-to-apply

The `apply_policy` singleton stores a JSON policy with: `min_score`, `must_have` keywords,
`avoid` keywords, `seniority` preference, `remote_only` flag. `list_ready_to_apply()` applies
these filters over scored jobs in live states. The result is presented for human review — the system
never applies automatically.

Modules: `services/apply_policy.py`, `storage/db.py::get_apply_policy`.

### ATS auto-fill and screening answerer

`services.prepare_form_fill(job_id)` detects the ATS from the apply URL, opens a Playwright browser
on the **host** (never in Docker), resolves all stored answers from `applicant_profile`,
`tailored_resumes`, and `answer_templates`, fills every field it can, and stops at the review
screen. Novel questions not covered by stored templates are answered by the `apply/answerer.py` LLM
call. Crash-resumable via `apply_checkpoints`.

Modules: `apply/formfill.py`, `apply/ats.py`, `apply/answerer.py`, `apply/formfill_profiles.py`.

### Per-company résumé variants

`resume_variants` rows can carry a `company` field. When tailoring, `best_scored_variant_for_company`
first attempts to find a variant whose `company` matches the job's company (case-insensitive). This
allows maintaining company-specific résumé emphases (e.g. a variant for Google, one for startups)
without duplicating the variant-selection logic.

Modules: `storage/db.py::best_scored_variant_for_company`, `services/drafting.py::tailor_for_job`.

### Message drafts

Beyond cover letters, the `draft_message_for_job` service generates `thank_you`, `follow_up`, and
`negotiation` messages grounded in the job detail, the tailored résumé, and the user's career
context. All drafts are stored in `drafts` with the appropriate `DraftKind`.

### Interview prep brief

`brief_for_job(job_id)` sends the full JD + user context through the `DRAFTING`-task LLM and
returns a structured brief: role context, likely interview questions, focus areas, and talking
points. Available via CLI (`hunt brief <job_id>`), API (`POST /api/jobs/{job_id}/brief`), and MCP
(`job_brief`).

### Email inbox triage

`sync_inbox` connects via IMAP, fetches new messages incrementally (UID-based, `BODY.PEEK`),
stores them in `email_messages`. `structure_pending` runs the `email_structure` LLM task over
unstructured messages to extract `category`, company name, job title, and recruiter name.
Messages are linked to existing `jobs` and `applications` rows.

Read is always safe (stdlib IMAP, `BODY.PEEK`). IMAP **writes** (draft reply / label / archive)
require an explicit `confirm=True` from the user and go through the propose→confirm→execute gate.

Modules: `email/reader.py`, `services/email_triage.py`, `services/email_actions.py`.

### Content post-draft engine

Every 3 days the worker calls `generate_and_notify_post()`: fetches a trending topic from HN or
dev.to, drafts a LinkedIn/X-style post via LLM, stores it in `content_posts` as `DRAFT`, and
notifies the user via the configured channel. The user reviews the post in the Content page and
marks it `posted` or `dismissed`. Nothing is ever auto-posted.

Modules: `services/content.py`, `content/`.

### Naukri refresh helper

`draft_profile_refresh()` sends the user's résumé context through the LLM and returns an optimized
Naukri headline, summary, and skills list. The user copies and pastes these into their Naukri profile
manually. A weekly Monday-09:00 cron job (`naukri_refresh`) sends a reminder notification.

Modules: `services/naukri_refresh.py`.

### Career Intelligence Engine

Three advisory-only functions (no state mutations, no submissions):

- **`explain_score(job_id, force=False)`** — LLM breaks down which JD requirements the résumé
  meets (`matched: [{requirement, evidence}]`) and misses (`missing: [{requirement, why_it_matters}]`)
  plus `suggestions`. Result cached in `learnings` as `LearningKind.EXPLANATION`; re-run skipped
  unless `force=True`.
- **`skill_gap(limit=20)`** — aggregates `missing` fields across all stored `EXPLANATION` learnings,
  counts frequency, returns ranked `{gaps: [{skill, count}], considered: int}`.
- **`next_best_action(job_id)`** — a first-match-wins rule ladder evaluating the job's current state,
  related email category, score, and age. Returns `{action: reply|negotiate|prep|follow_up|wait|
  apply|review|score|none, reason: str}`. Pure read — no writes.
- **`similar_successful(job_id)`** — pgvector cosine-distance query over jobs that reached
  `INTERVIEW`, `HR`, or `OFFER` state — outcome-aware similarity for inspiration.

Modules: `services/intelligence.py`, `embed/embedder.py`, `scoring/match.py`.

### Search prefs from Markdown

`set_search_prefs(content)` stores a freeform Markdown preferences file and calls the LLM to
parse it into structured `search_profiles` rows (keywords, location, remote-only, pages). This
means the user writes natural-language preferences and the system extracts search parameters
without a form UI.

### Semantic search

`embed_jobs(limit)` embeds unembedded jobs via Ollama's `nomic-embed-text` model; `semantic_match(query)`
embeds the query and performs a cosine-distance search over all job embeddings via pgvector.
Postgres-only; gracefully returns `{error: "…"}` on SQLite.

---

## 9. Entrypoints reference

### 9.1 CLI commands (`hunt <command>`)

Entrypoint: `job_hunt/cli/main.py::main` → registered as `hunt` script in `pyproject.toml`.

| Command | Key arguments | What it does |
|---|---|---|
| `selfcheck` | — | Probe DB, Ollama liveness, installed models, round-trip for each LLM task |
| `parse-resume` | — | Parse all files in `data/resumes/` into the résumé variant vault |
| `login` | `site` (naukri\|foundit) | One-time interactive browser login; persists cookies |
| `discover-naukri` | `--keyword`, `--location`, `--pages`, `--headless`, `--dry-run` | Playwright Naukri crawl |
| `discover` | `--source`, `--keyword`, `--location`, `--pages`, `--dry-run` | Generic source discovery |
| `enrich` | `--limit`, `--headless` | Fetch full JD for discovered jobs |
| `score` | `--verbose` | LLM-score all pending (job × variant) pairs |
| `top` | `--min-score`, `--limit` | Print top-scoring live jobs |
| `ready` | `--limit` | Print jobs passing the apply policy |
| `tailor` | `job_id` | Generate a tailored résumé for a job |
| `cover` | `job_id` | Generate a cover letter for a job |
| `brief` | `job_id` | Generate an interview-prep brief |
| `next` | `job_id` | Show the recommended next action (advisory) |
| `explain` | `job_id`, `--force` | Show per-requirement score breakdown |
| `skill-gap` | `--limit` | Aggregate missing skills across all scored jobs |
| `draft` | `kind` (thank_you\|follow_up\|negotiation), `job_id` | Generate a message draft |
| `apply-fill` | `job_id` | ATS auto-fill (stops at review screen) |
| `applicant` | `--set key=value ...` | Set/show standing applicant profile fields |
| `profiles` | — | List search profiles |
| `add-profile` | `--name`, `--keyword`, `--location`, `--pages` | Add a search profile |
| `run-cycle` | `--headless` | Run discovery+scoring for all active profiles |
| `embed` | `--limit` | Embed jobs for semantic search (Postgres only) |
| `semantic` | `query`, `--limit` | Semantic job search (Postgres only) |
| `report` | `--send` | Print daily report; optionally send to notification channel |
| `notify-test` | — | Send a test message via configured channel |
| `worker` | — | Start the APScheduler worker (long-running) |
| `serve-api` | `--host`, `--port` | Start the FastAPI REST API (bound to 127.0.0.1:8000 by default) |
| `serve-mcp` | — | Start the MCP server over stdio |
| `naukri-refresh` | — | Draft optimized Naukri headline/summary/skills for manual paste |
| `post` | `--topic` | Draft a new tech post |
| `posts` | `--status` | List stored post drafts |
| `watch add` | `company`, `ats`, `board_token` | Add a company to the ATS watchlist |
| `watch list` | — | List watchlist entries |
| `watch rm` | `id` | Remove a watchlist entry |
| `email sync` | `--mailbox`, `--limit`, `--structure-limit` | IMAP sync + LLM structure pass |
| `email list` | `--category`, `--state`, `--limit` | List triaged emails |
| `email show` | `email_id` | Show a single email |
| `email action` | `email_id`, `--kind`, `--label`, `--confirm` | Propose or confirm an email action |
| `email dismiss` | `email_id` | Dismiss a proposed email action |
| `context` | `file`, `--format` | Set/show career context blob |
| `search-prefs` | `file` | Set/show job-search preferences (parsed into search profiles) |
| `db` | `sql` | Ad-hoc read-only SQL against the active backend |

### 9.2 REST API routes (`job_hunt/api/app.py`)

All routes except `/health` require `Authorization: Bearer <token>` and are under prefix `/api`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Unauthenticated; probes DB; returns datastore, sources, LLM config summary |
| GET | `/api/jobs` | Top-scoring live jobs (`?min_score=70&limit=20`) |
| GET | `/api/board` | All jobs for the Kanban board (`?limit=200`) with best score |
| GET | `/api/jobs/{job_id}` | Full job detail with all variant scores and reasoning |
| GET | `/api/resume-variants` | List all résumé variants (full data) |
| GET | `/api/variants` | List variants (slug, company, tags, has_body summary) |
| GET | `/api/variants/{slug}` | Single variant full detail |
| POST | `/api/variants` | Parse + upsert a text-authored variant |
| GET | `/api/search-profiles` | List search profiles |
| POST | `/api/search-profiles` | Create a search profile |
| PATCH | `/api/search-profiles/{profile_id}` | Enable/disable a profile |
| POST | `/api/score` | Trigger scoring pass (background task) |
| POST | `/api/discover` | Trigger discovery run (background task) |
| GET | `/api/runs` | List recent runs |
| GET | `/api/runs/{run_id}` | Get a single run |
| POST | `/api/runs/{run_id}/cancel` | Request cooperative cancel of a run |
| POST | `/api/jobs/{job_id}/tailor` | Generate tailored résumé |
| POST | `/api/jobs/{job_id}/cover` | Generate cover letter |
| POST | `/api/jobs/{job_id}/brief` | Generate interview-prep brief |
| GET | `/api/jobs/{job_id}/drafts` | List all drafts for a job |
| POST | `/api/jobs/{job_id}/draft` | Generate thank-you / follow-up / negotiation message |
| POST | `/api/jobs/{job_id}/outreach` | Generate recruiter outreach draft |
| GET | `/api/companies/{name}/history` | Company engagement history |
| GET | `/api/contacts` | List contacts (optional `?company=`) |
| POST | `/api/contacts` | Add a contact |
| POST | `/api/apply/review` | AI pre-submit review (never submits) |
| GET | `/api/context` | Get career context |
| POST | `/api/context` | Set career context |
| GET | `/api/search-prefs` | Get search preferences |
| POST | `/api/search-prefs` | Parse + store search preferences → creates profiles |
| GET | `/api/apply-policy` | Get apply policy |
| GET | `/api/ready-to-apply` | Jobs passing the apply policy (`?limit=50`) |
| GET | `/api/applicant` | Get applicant personal-details profile |
| POST | `/api/applicant` | Set applicant profile fields |
| POST | `/api/jobs/{job_id}/fill` | ATS form-fill (background; stops at review screen) |
| GET | `/api/answer-templates` | List answer templates |
| POST | `/api/answer-templates` | Add answer template |
| GET | `/api/answer-templates/suggest` | Suggest answer for a question (`?q=`) |
| GET | `/api/analytics` | Dashboard: funnel metrics + LLM cost summary |
| POST | `/api/embed` | Embed jobs for semantic search |
| GET | `/api/semantic` | Semantic job search (`?q=&limit=10`) |
| GET | `/api/jobs/{job_id}/similar-successful` | Find similar jobs that reached interview/offer |
| POST | `/api/jobs/{job_id}/learn-rejection` | LLM-analyze a rejection, store learning |
| GET | `/api/jobs/{job_id}/next-action` | Rule-based next-best-action (advisory) |
| GET | `/api/jobs/{job_id}/explain` | Explainable score breakdown (`?force=false`) |
| GET | `/api/skill-gap` | Aggregated skill gaps across all scored jobs |
| PATCH | `/api/applications/{job_id}/stage` | Advance interview pipeline stage |
| POST | `/api/applications` | Log an application (applied/skipped/saved) |
| GET | `/api/emails` | List triaged inbox emails |
| GET | `/api/emails/{email_id}` | Get one email with full detail |
| POST | `/api/emails/{email_id}/propose` | Propose an email action for human review |
| POST | `/api/emails/{email_id}/action` | Confirm or gate a proposed email action |
| POST | `/api/emails/{email_id}/dismiss` | Dismiss a proposed email action |
| POST | `/api/emails/sync` | IMAP sync + structure pass (background) |
| GET | `/api/posts` | List content post drafts |
| POST | `/api/posts` | Generate a new content post |
| PATCH | `/api/posts/{post_id}` | Transition post status |
| GET | `/api/watchlist` | List company watchlist entries |
| POST | `/api/watchlist` | Add a company to the watchlist |
| DELETE | `/api/watchlist/{watch_id}` | Remove a watchlist entry |
| PATCH | `/api/watchlist/{watch_id}` | Enable/disable a watchlist entry |

**Error handling**: `_unwrap(result)` maps `{"error": "…"}` from services to HTTP 404 (if the
message contains "no job with id", "no run", or "not found") or HTTP 400 (all others). Infra errors
bubble up as HTTP 500.

### 9.3 MCP tools (`job_hunt/mcp_server/server.py`)

Started via `hunt serve-mcp` (stdio). FastMCP server named `"job-hunt"`. All tools are thin wrappers
over `services.*`.

| Tool | Parameters | Purpose |
|---|---|---|
| `discover_naukri` | `keyword`, `location`, `pages=1` | Playwright Naukri crawl |
| `score_pending` | `verbose=False` | Score all pending (job × variant) pairs |
| `next_best_action` | `job_id` | Rule-based next action (advisory) |
| `explain_score` | `job_id`, `force=False` | Per-requirement score breakdown |
| `skill_gap` | `limit=20` | Aggregated skill gaps |
| `list_new_jobs` | `min_score=70`, `limit=10` | Top-scoring jobs awaiting review |
| `show_job` | `job_id` | Full job record with all scores |
| `list_resume_vault` | — | List résumé variants |
| `ready_to_apply` | `limit=50` | Jobs passing apply policy (human review only) |
| `log_application` | `job_id`, `variant_slug`, `cover_letter`, `status="applied"` | Record an application |
| `fill_application` | `job_id` | ATS auto-fill (stops at review screen) |
| `email_sync` | — | IMAP sync + structure pass |
| `email_list` | `category=""`, `action_state=""` | List triaged emails with optional filter |
| `email_get` | `email_id` | Get one email |
| `tailor` | `job_id` | Generate tailored résumé |
| `cover` | `job_id` | Draft a cover letter |
| `draft` | `job_id`, `kind` | Draft a thank_you / follow_up / negotiation message |
| `job_brief` | `job_id` | Interview-prep brief |
| `list_drafts` | `job_id` | List all drafts for a job |
| `top_matches` | `min_score=70`, `limit=10` | Top-scoring matched jobs |
| `similar_successful` | `job_id`, `limit=5` | Similar jobs that reached interview/offer |
| `company` | `name` | Company history and info |
| `list_watchlist` | — | All company watchlist entries |
| `generate_post` | `topic=""` | Draft a tech post (auto-topic if blank) |
| `list_posts` | `status=""` | List stored post drafts |

### 9.4 Worker scheduled jobs (`worker/scheduler.py`)

| Job ID | Schedule | What it does | Gate |
|---|---|---|---|
| `discovery` | Every `DISCOVERY_INTERVAL_MIN` min (default 180) | Runs all active search profiles via browser + configurable sources | `WORKER_ACTIVE_START`–`WORKER_ACTIVE_END` time gate; `WORKER_DAILY_CAP` run cap |
| `dispatch` | Every `DISPATCH_INTERVAL_SEC` s (default 30) | Drains the event outbox (`dispatch_pending`) | None |
| `api_discovery` | Every `API_DISCOVERY_INTERVAL_MIN` min (default 20) | Polls API sources in `WORKER_API_SOURCES` (no browser, no active-hours gate) | None |
| `daily_report` | Cron: 20:00 daily | Sends daily report to configured notification channel | `NOTIFY_CHANNEL` |
| `content_post` | Every 3 days | Generates a tech post draft, sends notification | `NOTIFY_CHANNEL` |
| `naukri_refresh` | Cron: Monday 09:00 | Sends weekly Naukri profile refresh reminder | `NOTIFY_CHANNEL` |

---

## 10. Frontend

### Pages and routing

The frontend is a React 19 SPA with a custom History-API client router in `src/lib/router.tsx`.
There are no hash routes. Navigation uses `<Link to="/board">` and `navigate()` from the same module.
The `App.tsx` shell renders one top-level tab at a time, keyed by the SCREEN constant so sub-route
changes (e.g. `/board → /board/42`) do not remount the whole tree.

| Screen key | URL | Component | Purpose |
|---|---|---|---|
| `board` | `/board` (default) | `pages/Board/` | Kanban by `JobState`; job cards with score; tailor/cover/fill/draft actions |
| `inbox` | `/inbox` | `pages/Inbox/` | Triaged email list; propose/confirm/dismiss actions; full email detail |
| `content` | `/content` | `pages/Content/` | Tech post draft management (generate / post / dismiss) |
| `resumes` | `/resumes` | `pages/Resumes/` | Résumé variant management; text editor for text-authored variants |
| `runs` | `/runs` | `pages/Runs.tsx` | Background run history; cancel button |
| `analytics` | `/analytics` | `pages/Analytics.tsx` | Application funnel chart; LLM cost dashboard |
| `settings` | `/settings` | `pages/Settings.tsx` | API token; applicant profile; user context; search prefs; apply policy; watchlist; notification test |

### State model

| State type | Mechanism |
|---|---|
| Server state (all remote data) | TanStack Query `useQuery` / `useMutation`; query keys in `src/lib/constants.ts::QUERY_KEYS` |
| URL / navigation state | Custom History API router (`src/lib/router.tsx`) |
| Local UI state (modals, tabs, form values) | `useState` |
| Theme | localStorage-persisted dark/light toggle; `.dark` class on `<html>` |

Invalidation is precise — mutations invalidate only the affected query keys.
401 responses are caught once in `src/lib/api.ts::req()` and redirect to Settings.

### Styling standard

Tailwind CSS v4 + shadcn/ui component library (Radix primitives, vendored in `src/components/ui/`).
CSS-variable tokens (shadcn's palette contract: `--background`, `--foreground`, `--card`,
`--primary`, `--muted`, `--border`, `--destructive`) defined in `src/styles.css` for `:root` (light)
and `.dark`. No CSS Modules, no SCSS, no inline hex values in components. Every app `.tsx` file is
≤ 150 lines. Loading/error/empty states use the three shared primitives: `<LoadingView>`,
`<ErrorView>`, `<EmptyView>`.

---

## 11. Configuration

All env vars are in `backend/.env.example` (copy to `backend/.env.local` to override). In Docker
Compose, `API_TOKEN` is auto-generated by `make up` and shared between the `api` and `frontend`
(nginx) containers. All other vars come from `backend/.env.local` (optional, `required: false`).

### API server

| Variable | Default | Purpose |
|---|---|---|
| `API_TOKEN` | ephemeral random (printed at startup) | Bearer token required on all `/api/*` requests; `make up` generates a shared token |

### Datastore

| Variable | Default | Purpose |
|---|---|---|
| `DB_BACKEND` | `sqlite` | `sqlite` for local dev/tests; `postgres` for production |
| `DATABASE_URL` | `postgresql://jobhunt:jobhunt@localhost:55432/jobhunt` | Postgres connection string (used when `DB_BACKEND=postgres`) |

### LLM

| Variable | Default | Purpose |
|---|---|---|
| `OLLAMA_URL` | `http://localhost:11434` | Ollama base URL |
| `LLM_SCORING_PROVIDER` | `ollama` | Provider for the scoring task |
| `LLM_SCORING_MODEL` | `qwen2.5:7b` | Model for scoring |
| `LLM_DRAFTING_PROVIDER` | `ollama` | Provider for drafting (cover, outreach, messages, AI review) |
| `LLM_DRAFTING_MODEL` | `qwen2.5:7b` | Model for drafting |
| `LLM_EMAIL_STRUCTURE_PROVIDER` | `ollama` | Provider for email category/field extraction |
| `LLM_EMAIL_STRUCTURE_MODEL` | `qwen2.5:7b` | Model for email structuring |
| `LLM_TAILORING_PROVIDER` | `ollama` | Provider for résumé tailoring |
| `LLM_TAILORING_MODEL` | `qwen2.5:7b` | Model for tailoring |
| `LLM_<TASK>_FALLBACK_PROVIDER` | (unset) | Fallback provider tried once after primary exhausted |
| `LLM_<TASK>_FALLBACK_MODEL` | same as task model | Fallback model |
| `OPENAI_API_KEY` | (unset) | Required when any task uses `LLM_*_PROVIDER=openai` |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | OpenAI-compatible base URL |
| `GEMINI_API_KEY` | (unset) | Required when any task uses `LLM_*_PROVIDER=gemini` |
| `GEMINI_BASE_URL` | `https://generativelanguage.googleapis.com/v1beta/openai` | Gemini v1beta OpenAI-compat endpoint |
| `GROQ_API_KEY` | (unset) | Single Groq key |
| `GROQ_API_KEYS` | (unset) | Comma-separated Groq keys; rotated on 429/401 |
| `OLLAMA_TIMEOUT_S` | `120` | Per-call timeout for Ollama (increase after model swap) |
| `LLM_MAX_ATTEMPTS` | `2` | Retry attempts per chat call |
| `LLM_BACKOFF_BASE_S` | `0.5` | Exponential backoff base (seconds) |
| `LLM_COST_TABLE` | (built-in table) | JSON override for per-model pricing `{"model": [p_per_1k, c_per_1k]}` |
| `OLLAMA_SCORING_MODEL` / `OLLAMA_DRAFTING_MODEL` | `qwen2.5:7b` | Legacy aliases (honored as fallbacks) |

### Email

| Variable | Default | Purpose |
|---|---|---|
| `EMAIL_IMAP_HOST` | `imap.gmail.com` | IMAP server hostname |
| `EMAIL_ADDRESS` | (unset) | Your email address |
| `EMAIL_APP_PASSWORD` | (unset) | Gmail App Password (or equivalent); never logged |

All three must be set or none — settings validation fails fast if only some are provided.

### Notifications

| Variable | Default | Purpose |
|---|---|---|
| `NOTIFY_CHANNEL` | `none` | `telegram` \| `discord` \| `none` |
| `TELEGRAM_BOT_TOKEN` | (unset) | Telegram bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | (unset) | Target chat ID |
| `DISCORD_WEBHOOK_URL` | (unset) | Discord incoming webhook URL |

### Semantic search / embeddings

| Variable | Default | Purpose |
|---|---|---|
| `EMBED_PROVIDER` | `ollama` | `ollama` \| `stub` |
| `EMBED_MODEL` | `nomic-embed-text` | Embedding model; must match `EMBED_DIM` |
| `EMBED_DIM` | `768` | Vector dimension; must match the `vector(N)` column in migration 0008 |

### Worker schedule

| Variable | Default | Purpose |
|---|---|---|
| `WORKER_ACTIVE_START` | `09:30` | Start of discovery active window (local HH:MM) |
| `WORKER_ACTIVE_END` | `21:00` | End of discovery active window |
| `WORKER_DAILY_CAP` | `30` | Max discovery runs per day |
| `WORKER_DISCOVERY_INTERVAL_MIN` | `180` | Minutes between browser-source discovery runs |
| `WORKER_DISPATCH_INTERVAL_SEC` | `30` | Seconds between event-outbox drain passes |
| `WORKER_API_DISCOVERY_INTERVAL_MIN` | `20` | Minutes between API-source discovery runs |
| `WORKER_API_SOURCES` | `remoteok,adzuna,weworkremotely,workingnomads,jobspresso,amazon,google` | Comma-separated API sources for the fast loop |

### Job-source credentials

| Variable | Default | Purpose |
|---|---|---|
| `ADZUNA_APP_ID` | (unset) | Adzuna API app ID (free registration) |
| `ADZUNA_APP_KEY` | (unset) | Adzuna API app key |
| `ADZUNA_COUNTRY` | `in` | Adzuna market code (`in`, `gb`, `us`, `au`, …) |

### Advanced / tuning

| Variable | Default | Purpose |
|---|---|---|
| `LOG_LEVEL` | `INFO` | Python logging level |
| `SCRAPE_MIN_INTERVAL_S` | `2.0` | Minimum seconds between browser scrape requests per source |

---

## 12. Security and boundaries

### Human-in-the-loop (by design)

Every action that has real-world effect requires an explicit human step:

- **ATS auto-fill** (`prepare_form_fill`): fills the form, opens the review screen, and blocks
  waiting for the human to close the tab. Submit button is never clicked by the system.
- **Email actions** (draft reply, apply label, archive): require `confirm=True` in the API call
  or `--confirm` in the CLI. The `propose_action` step stores a `PROPOSED` row for review first.
- **Content posts**: stored as `DRAFT`; the user transitions to `POSTED` manually.
- **Naukri profile**: the system drafts the text and notifies; the user pastes it.
- **Application logging**: `log_application` records the decision the human already made.

### Prompt-injection containment

Email bodies and job descriptions are **untrusted input** treated as data, never instructions:

- The email structuring prompt is hardened: the LLM is instructed to extract only named fields
  from the email body, not to follow any instructions embedded in it.
- Cover letters and messages are grounded in **extracted structured fields** (company name, role,
  JD requirements), not raw email bodies.
- No model output can trigger an IMAP write — the confirmation gate is enforced at the service
  level, not by the model.

### What the system never does

- No auto-apply. No auto-post to LinkedIn/X. No auto-send email.
- No scraping of LinkedIn, Glassdoor, or any site that prohibits scraping.
- No anti-bot evasion beyond standard browser fingerprint normalization (Playwright stealth).
- No credential storage: Gmail App Password, provider API keys, and `API_TOKEN` live only in
  `backend/.env.local` — never in the database, never in any LLM prompt, never logged.

### API token

The FastAPI app requires `Authorization: Bearer <token>` on every `/api` route. If `API_TOKEN` is
not set, an ephemeral `secrets.token_hex(16)` token is generated and printed at startup. In Docker
Compose, `make up` writes a stable `secrets.token_urlsafe(32)` token to a root `.env` file, which
is injected into both the `api` container and nginx's `envsubst` template so the browser never needs
to set a token — nginx injects it on every `/api` request transparently.

### Secrets handling

`EMAIL_APP_PASSWORD` is read from the environment and passed directly to the IMAP connection. It
is never stored in the database, never written to any log line, and never placed in an LLM prompt.
Provider API keys follow the same rules. The `.env.local` file is gitignored.

---

## 13. Deployment

### Docker Compose topology

```mermaid
flowchart TB
    subgraph Docker["docker compose up (make up)"]
        FE["frontend\nnginx :8770\nserves built React app\nproxies /api/* → api:8000\nenvsubst injects API_TOKEN\ninto every /api request"]
        API["api\n:8000\nFastAPI + uvicorn\nruns migrations on start\nDB_BACKEND=postgres"]
        WK["worker\nAPScheduler\nhunt worker\nDB_BACKEND=postgres"]
        DB["db\npgvector/pgvector:pg16\n:55432 (host) → :5432 (container)\npersistent volume: jobhunt_pgdata"]
    end

    subgraph Host["Host — not containerized (by design)"]
        OL["Ollama\nlocalhost:11434\n(GPU/Metal passthrough painful in Docker on macOS)"]
        BROW["Browser features\nNaukri crawl · ATS auto-fill\n(need screen + user session)"]
    end

    FE -->|"HTTP"| API
    API -->|"psycopg3"| DB
    WK -->|"psycopg3"| DB
    API -->|"host.docker.internal:11434"| OL
    WK -->|"host.docker.internal:11434"| OL
    API & WK -.->|"shared data volume\njobhunt_data"| DATA[("data/\njobhunt.db (SQLite fallback)\nresumes/\nsessions/")]
```

### Key deployment details

- **Port 8770**: the nginx frontend (chosen to avoid clashing with other local services on 8080/8443).
- **Port 8000**: the FastAPI backend (exposed directly for host-native development; proxied by nginx in stack mode).
- **Port 55432**: Postgres (host-side; avoids clashing with a local Postgres on 5432 or another project's container on 5433).
- **Migrations auto-apply**: the `api` container runs `python -c 'from job_hunt.storage import repo; repo.init_db()'` before starting uvicorn. `init_db()` applies all `migrations/00NN_*.sql` idempotently.
- **nginx token injection**: the `frontend` Dockerfile uses `envsubst` on an nginx config template at container startup. `API_TOKEN` from the environment is written into the nginx config so it is included in the `Authorization: Bearer …` header on every proxied request.
- **`make up`** calls `ensure-token` first, which appends `API_TOKEN=<random>` to the root `.env` if one isn't already set.
- **Ollama** and **browser features** are documented as host-only in the Makefile and README. `host.docker.internal` resolves to the host gateway from inside both the `api` and `worker` containers.
- **`jobhunt_data` volume** is shared between `api` and `worker` for the `data/` directory (resume files, session cookies, and the SQLite file when `DB_BACKEND=sqlite`).

### Makefile targets

| Target | Description |
|---|---|
| `up` | `ensure-token` + `docker compose up --build -d` |
| `down` | Stop the stack (keeps the Postgres volume) |
| `restart` | Restart `api`, `worker`, `frontend` containers only |
| `build` | Rebuild images without starting |
| `logs` | Follow all container logs |
| `ps` | Show container status |
| `db` | Start only Postgres (for host-native `uv run hunt ...` dev) |
| `host-cli CMD=...` | Run a host CLI command, e.g. `make host-cli CMD="apply-fill 12"` |
| `notify-test` | Send a test notification (host CLI) |
| `test` | `uv run pytest -q` + `npx vitest run` |
| `clean` | `docker compose down -v` — destroys the Postgres volume |

---

## 14. Testing and conventions

### Testing

**Backend**: pytest, function-based (`def test_*`), no `class Test*`. 70 test files in
`backend/tests/`. Shared fixtures in `backend/tests/conftest.py`. Key hermetic patterns:
- `tmp_db` fixture: monkeypatches `db.DB_PATH` to a `tmp_path`-based SQLite file; every test gets
  a fresh empty database.
- LLM tests: monkeypatch `llm.client._call` or inject `StubProvider` to avoid network calls.
- Plugin/fetcher tests: monkeypatch module-level `_fetch` functions (per-plugin naming convention).
- Helper fakes named `_FakeX` / `_FlakyX` / `_StubX`.
- `@pytest.mark.parametrize` for tables of similar cases.

**Frontend**: vitest, co-located with source files (`Board.tsx` → `Board.test.ts`). Non-trivial
logic is tested; trivial presentational components are not required to have tests.

Run both: `make test`.

### Backend conventions digest (from `backend/CLAUDE.md`)

| Rule | Summary |
|---|---|
| Type hints | Every signature fully typed; modern syntax (`list[X] \| None`, not `Optional[List[X]]`); no `Any` at boundaries |
| Enums | `JobState.SCORED` not `"scored"` — raw strings only in SQL `IN (...)` lists and Pydantic HTTP boundary models |
| Services | Return `dict` or `list`; `{"error": "…"}` on user-fixable failure; never raise for user errors; `_unwrap()` maps to HTTP 4xx |
| SQL | All parameterized (`?` SQLite, `%s` Postgres); all inside `with connect() as conn:` |
| Dual-backend mirror | Every raw SQL helper lives in both `db.py` and `pg.py`; a new table gets both a `SCHEMA` entry and a migration |
| File size | Service files ≤ 400 lines; `db.py`/`pg.py` exempt; `cli/main.py` exempt |
| Logging | `get_logger(__name__)` everywhere; `print()` only in `cli/*.py` and `verbose`-gated paths |
| Imports | `from __future__ import annotations` first; stdlib → third-party → `job_hunt.*`; absolute only |
| Frontend contract | Backend DTO changes go in `frontend/src/lib/api.ts` in the same PR; `JobState` changes go in `Board.tsx::COLUMNS` in the same PR |
| Revisit triggers | `api/app.py` > 500 lines → split into routers; `storage/db.py` or `pg.py` > 1200 lines → split by domain; `services/` at 27 files — subfolder grouping pending |

### Frontend conventions digest (from `frontend/CLAUDE.md`)

| Rule | Summary |
|---|---|
| Strict TypeScript | No `any`; no leaked `unknown`; `strict: true` non-negotiable |
| Types mirror DTOs | `src/lib/api.ts` interfaces 1:1 with `api/dto.py` Pydantic models |
| No hardcoded values | Routes → `ROUTES`; endpoints → `API_ENDPOINTS`; query keys → `QUERY_KEYS`; state strings → `JOB_STATE`; all in `src/lib/constants.ts` |
| Size cap | Every app `.tsx` ≤ 150 lines; `src/components/ui/` (shadcn primitives) exempt |
| State management | TanStack Query for server state; History API router for URL state; `useState` for local UI; no Redux/Zustand |
| Four loading states | Every data-loading view uses `<LoadingView>`, `<ErrorView>`, `<EmptyView>`, and the data render |
| 401 handling | Owned once in `src/lib/api.ts::req()`; individual callers never handle auth failure |
| Styling | Tailwind utilities + shadcn/ui only; no CSS-in-JS, no SCSS, no inline hex; plain CSS requires a `/* why: */` comment |
| Responsive | No horizontal scroll at 375/768/1024/1440px; touch targets ≥ 40px |
