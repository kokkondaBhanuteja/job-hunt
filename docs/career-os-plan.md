# Job-Hunt → "Career OS" Platform — Architecture & Build Plan

_Last updated: 2026-06-30 · **Status: architecture frozen — next step is implementing Phase 0.** Further additions go to "Future considerations", not the core design._

## Context

A working **v0 personal job-hunt toolkit** exists in `job_hunt/` (Python, Ollama, SQLite,
Playwright Naukri crawler, MCP server, CLI). It discovers Naukri listings, scores each job ×
resume-variant locally, and exposes everything as MCP tools — the MCP host is the only UI.
Gaps: it scores against the **listing snippet, not the full JD**; never **tailors** resumes;
the `contacts`/`outreach`/`runs` tables exist but are **unused**; there's **no web UI**, no
multi-source discovery, no apply step, and **no tests**.

The goal is to evolve this into a **properly-architected platform** with a **React web UI**
to manage everything, covering all phases of the "Career OS" vision (discover → enrich → score
→ tailor → draft → apply → track → learn). Built in **vertical slices**, each slice shippable,
nothing duplicated — and **never losing a green, working tool along the way** (there are no tests
today, so we add them first).

## Product thesis

Be a **highly efficient human, not a bot**. A system that submits **20–40 highly-targeted,
tailored applications/day** beats one that blindly fires 300+ generic ones — better response
rates *and* it looks like normal user behavior.

More precisely: **augment the user's judgment instead of replacing it.** Every automation must
either *save time*, *improve application quality*, or *enable a better decision* — while keeping
the user in control of the choices that matter. This single principle is what justifies
review-before-submit, quality scoring, the AI pre-submit reviewer, and learning from outcomes.

## Confirmed decisions

1. **Datastore:** Postgres + pgvector (Docker).
2. **Auto-apply:** review-before-submit — agent fills the form, user approves in the React UI, then submit.
3. **LLM:** pluggable provider, **configurable as local model OR API key**, per task. $0 by default.

**Deliberate calls (open to change):**
- **No ORM.** Keep the lightweight raw-SQL repository style, ported to Postgres via `psycopg3` +
  numbered `.sql` migrations. Pydantic only at the API boundary.
- **Event bus = in-DB transactional outbox**, *not* an external broker. An `events` table the worker
  drains gives event-driven decoupling without Kafka/Redis ops. (Reviewer #16, scoped to single-user reality.)
- **Scheduler = APScheduler cron + internal event triggers.** Full *reactive* scheduling (wake on external
  site change) is **future**, not foundation. (Reviewer #9.)
- **Plugin/Source contract defined now (P1), real plugins implemented later (P5)** — define the interface
  early, don't build the abstraction before the 2nd source exists. (Reviewer #6.)
- **Existing SQLite data:** throwaway dev data → fresh start on Postgres (copy script kept available).
- **Ollama stays native** (host), not Docker — Metal passthrough on macOS is painful. Only Postgres is dockerized.

## Operating principles (quality-first, anti-detection)

Guardrails the architecture *enforces*, not just advice. Each maps to where it lives.

| # | Principle | Enforced by |
|---|---|---|
| 1 | No robotic bursts — randomized delays, occasional long pauses, varied order | pacing layer + scheduler (P6) |
| 2 | Realistic interaction, *not* fake mouse-sim — variable scroll, slight click jitter | Browser Manager humanizer (P6) |
| 3 | Tailor the resume to every JD — weave the role's tech, invent nothing | resume `tailor/` (P4) |
| 4 | Fresh, short, specific cover letter — company + role + stack + recent product + why | `draft/` + company research (P4) |
| 5 | Answer-template library with truthful variation | `answer_templates` + apply fill (P6) |
| 6 | Score every job; only act above a threshold (≥80%) | scoring + threshold gate (P1) |
| 7 | Never apply twice — canonical `company+role+location` (+URL) dedup across sources | dedup key in `jobs` (P1) |
| 8 | Detect the ATS (Greenhouse/Lever/Workday/Ashby/SmartRecruiters/iCIMS) → per-platform flow | `apply/ats/` (P6) |
| 9 | One stable browser profile — no VPN/IP/device churn | Browser Manager single profile (P1) |
| 10 | Marquee companies → manual review (notify, hold, never auto-submit) | `jobs.priority` + notify-and-hold (P6) |
| 11 | Humans sleep — activity in realistic local hours, with breaks; no 24/7 | worker active-hours window + cap (P1/P6) |
| 12 | Favor fresh, low-applicant listings | `applicant_count`/`posted_at` → prioritization (P1) |
| 13 | Company research before applying | company enrichment + memory (P4) |
| 14 | Track every interview stage (Applied→OA→Interview→HR→Offer) | `applications.stage` pipeline (P7) |
| 15 | Learn from outcomes — rejection→missing-keyword; up-weight winning variants | analytics + learning loop (P7) |

**Pacing model (concrete):** configurable per-day submission cap (default ~30), active-hours window
(e.g. 09:30–21:00 local), randomized inter-action delays with occasional long pauses, varied order.
The worker simply *stops* queueing submissions once the cap/window is hit — the top anti-detection lever.

## Architectural keystone

A single **`services/` layer** is the backbone. Every entrypoint — React (via FastAPI), MCP server,
CLI, worker — calls the *same* service functions. Services own transactions and business logic
(dedup, enrichment gating, scoring orchestration, state transitions); they must **not** import
FastAPI/argparse/FastMCP types; entrypoints pass plain args and get plain DTOs. `api/`, `worker/`,
`mcp_server/` are thin adapters.

## Core cross-cutting modules

These are shared infrastructure that many phases depend on — defined early so nothing is retrofitted.

- **Browser Manager** (`browser/`) — *the only* place Playwright is instantiated. Owns the single
  persistent profile, cookies/session, per-platform **Rate Limiter**, optional proxy, captcha/login-wall
  detection, and humanized pacing helpers. Every scraper/apply flow borrows a managed context. (Reviewer #7, #8.)
- **Event bus** (`events/`) — in-DB **transactional outbox**: state changes append an `events` row in the
  same transaction; the worker drains and dispatches (`job.scored → tailor`, `application.submitted → notify`).
  Decouples pipeline stages; new features subscribe without touching producers. (Reviewer #16.)
  **Kept deliberately small:** emit only the ~7 **major domain transitions** (`JobDiscovered`, `JobEnriched`,
  `JobScored`, `ResumeTailored`, `DraftGenerated`, `ApplicationSubmitted`, `InterviewUpdated`) — *not* every
  micro-state-change. Events carry a `class` of **domain** (analytics/automation) vs **infra**
  (`WorkerStarted`/`CaptchaDetected`/`RateLimitReached` → monitoring only), so the two never get tangled.
- **Job state machine** — every job moves through explicit states with allowed transitions; each transition
  emits an event. States: `DISCOVERED → ENRICHED → SCORED →` (`ARCHIVED` if below threshold | `OPPORTUNITY` if above)
  `→ TAILORING_READY → DRAFTED → REVIEW_PENDING → READY_TO_APPLY → APPLIED → {OA → INTERVIEW → HR → OFFER | REJECTED}`,
  plus `DEFERRED` (wait/referral/salary-unknown) and `WITHDRAWN`. (Reviewer #1, #2.)
- **Opportunity / decision queue** — a job that passes the score threshold becomes an *opportunity* with
  decision metadata (`defer_until`, `waiting_for` referral/recruiter/salary, manual-only). This is the
  decision engine between *scored* and *applied* — "don't apply yet / wait for morning / wait for referral". (Reviewer #1.)
- **Search profiles** — first-class, toggleable: keywords, exclusions, salary, locations, target/avoid
  companies, remote policy, YOE. Discovery runs *per active profile*. (Reviewer #10.)
- **AI Gateway** (`llm/`) — the ONE path for every AI call; no service calls a provider directly. It already
  provides the **model router** (`registry.py`: task→provider/model), **cost + latency tracking** (`llm_calls`),
  and **response validation** (`chat_json` + jsonschema with a prompt-and-parse fallback). Being extended with a
  **Prompt Library** (versioned prompts + schemas in one place, out of the services), **retries + provider
  fallback**, and an **optional response cache** keyed by `(prompt_hash, provider_model)`.
- **LLM call log** — every model call records prompt, response, provider, model, tokens, latency, cost.
  Powers debugging, the cost dashboard, and per-task quality tuning. (Reviewer #4, #15.)
- **Plugin/Source contract** — uniform `discover()/login()/crawl()/enrich()/apply()` per site; the registry
  makes adding a board trivial. Contract defined P1, plugins implemented P5. (Reviewer #6.)

## Cross-cutting conventions (architecture consistency)

Rules the code already follows — stated so they stay consistent as the system grows.

- **AI Gateway is the only path to a model.** No service calls a provider directly; everything goes through
  `llm/` (router `registry.py` + validation `chat_json` + logging `llm_calls` + **Prompt Library `prompts.py`**
  + retries/fallback in `client.py`). Prompts/schemas live *only* in the Prompt Library, versioned; services
  render per-call data but never define prompts inline.
- **Service = domain module.** `services/` is split by domain (`discovery/scoring/review/applications/
  resumes/profiles/runs`); new domains get their own module (`enrich`, `draft`, `apply`, `analytics`). Keep each focused.
- **Package = domain.** New packages are domain-named. We do **not** reorganize working code into a `career/`
  namespace — that's churn without payoff for a single-user tool (see Future considerations).
- **Pipeline orchestration = outbox + state machine + handler registry** — this *is* the "workflow engine":
  a `transition_job()` emits an event; the worker's `dispatch_pending` routes it to a handler that advances the
  next step. Add `events.retry_count` + `events.priority` **when** heavy AI steps (tailoring/enrichment) land in
  P4 — not before. No Temporal/Airflow for one user.
- **Observability = structured logging + existing tables**, not a tracing stack: `llm_calls` (AI cost/latency),
  `runs` (heartbeat/log = worker health), `audit_log` (user/AI actions), `events` (domain vs infra).
- **Caching = DB-backed**: idempotent scoring (`input_hash`+`provider_model`), the `companies` research cache,
  and an optional `llm_cache(prompt_hash, provider_model, …)`. Redis only if this ever goes multi-user.

## Target monorepo layout

```
job-hunt/
├─ backend/
│  ├─ job_hunt/
│  │   ├─ browser/    ★ Browser Manager: profile/session/rate-limiter/captcha/pacing
│  │   ├─ events/     ★ in-DB outbox + dispatcher (event bus)
│  │   ├─ plugins/    per-site: discover/login/crawl/enrich/apply (naukri first; contract in P1)
│  │   ├─ enrich/     full JD text + company research (size/funding/tech/blog/Glassdoor) (NEW)
│  │   ├─ scoring/    job × variant fit + confidence; idempotent; freshness prioritization
│  │   ├─ resume/     parse (exists) + tailor-per-JD + version snapshots (NEW)
│  │   ├─ draft/      cover letters + outreach + answer-template library (NEW)
│  │   ├─ apply/      ats/ (detect+adapters) + AI pre-submit reviewer + checkpoint/resume (NEW)
│  │   ├─ llm/        pluggable provider registry + call logging
│  │   ├─ services/   ★ shared service layer (the keystone)
│  │   └─ storage/    psycopg3 repository fns + numbered .sql migrations
│  ├─ api/            FastAPI: REST (127.0.0.1, token-authed); clients poll runs/events
│  ├─ worker/         APScheduler + event dispatcher + on-demand jobs
│  └─ mcp_server/     chat-driven control (re-pointed at services/)
├─ frontend/          React + TS + Vite + Tailwind + shadcn/ui + TanStack Query
└─ docker-compose.yml postgres(+pgvector) only
```

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Scraping / LLM engine | **Python** (existing) | Playwright + Ollama already written |
| API | **FastAPI** | async, auto OpenAPI for the React client |
| DB access | **psycopg3 + `.sql` migrations** | keeps existing clean raw-SQL style; no ORM rewrite |
| DB | **Postgres + pgvector** (Docker) | concurrency, JSONB, semantic matching later |
| Eventing | **in-DB outbox + worker dispatcher** | event-driven, zero extra infra |
| Scheduler | **APScheduler + event triggers** | cron + reactive-on-events; no broker |
| Frontend | **React + TS + Vite + Tailwind + shadcn + TanStack Query** | the management UI |
| LLM | **provider registry** (Ollama / OpenAI-compat / Anthropic) + call log | local-default, API-key-pluggable per task |
| Notifications | **Telegram/Discord webhook** | daily report + priority alerts |

## Pluggable LLM layer (configurable local model OR API key)

Generalize `llm/ollama.py` into a **capability-based** provider registry; keep `chat()`/`chat_json()`
call sites unchanged. `provider.py` Protocol carries a capability flag (schema-constrained output?
Ollama `format` / OpenAI `response_format`) with a **prompt-and-parse + jsonschema-validate fallback**
for partial providers (e.g. Gemini). Ship **Ollama + one OpenAI-compat provider** first; Anthropic later.
A deterministic **stub provider** is injected in tests. **Every call is logged** (prompt/response/tokens/
latency/cost/provider/model).

Config — env-driven, per task:
```
LLM_SCORING_PROVIDER=ollama   LLM_SCORING_MODEL=qwen2.5:7b      # $0 default
LLM_DRAFTING_PROVIDER=ollama  LLM_DRAFTING_MODEL=qwen2.5:7b
# opt a hard task into the cloud:
# LLM_DRAFTING_PROVIDER=openai   OPENAI_API_KEY=...   (Gemini via openai-compat base_url)
# LLM_TAILORING_PROVIDER=anthropic   ANTHROPIC_API_KEY=...
```

## Data model (Postgres, ported + extended)

**Core / dedup**
- Canonical dedup key now: normalized `company + title + location` (+ URL canonicalizer) — cross-source safe.
- `jobs.description_full` + `jobs.enriched_at` (full JD; `description` stays the snippet).
- **State machine:** `jobs.state` (enum above) + `job_transitions(job_id, from, to, at, reason)` audit trail.

**Prioritization**
- `jobs.applicant_count`, `jobs.posted_at`/`freshness`, `jobs.ats_platform`, `jobs.priority` (marquee→manual).

**Scoring (idempotent + confidence)**
- `scores`: `fit_score`, **`confidence`** (low when JD incomplete → flag for enrichment/review),
  `scored_against` ('snippet'|'full'), `input_hash`, `provider_model`. Re-score only when input/model changes.

**Opportunity / decision**
- `opportunities(job_id, decision, defer_until, waiting_for, notes, updated_at)` — the decision engine.
- **`rules` as data** (Reviewer #4): `rules(condition, action, priority, enabled)` — e.g. *company=Google → manual-only*,
  *salary<15L → archive*, *location≠remote → skip*. The opportunity/decision step evaluates rules instead of
  hardcoded `if score > 80`. Their output is a **recommendation** (apply-now / wait / need-referral / low-chance / manual).

**Artifacts + versioning** (Reviewer #3, #5)
- `resume_variants` (exists) → `tailored_resumes(job_id, variant_id, content, created_at)` →
  **`submitted_resumes`** (immutable snapshot of exactly what was sent). Answers "which resume got interviews?".
- `drafts(job_id, kind['cover'|'outreach'], body, status, created_at)`; `answer_templates(question_pattern, answer_text, tags)`.
- **AI proposes, the user owns the source.** AI-generated edits to any artifact (resume/cover/answer/recruiter
  message) are stored as **suggestions** (`origin='ai'`, `status='proposed'`) and never overwrite user content
  until accepted (`origin='user'` content is the source of truth).

**Company memory + recruiter CRM** (Reviewer #11, #12)
- `companies` (research cache: size, funding_stage, tech, eng_blog, glassdoor, hiring_activity, fetched_at)
  + historical link to applications → per-company memory over years.
- `contacts` (exists) → recruiter CRM; `outreach` (exists) → messages/follow-ups/last_contact.

**Pipeline + observability**
- `applications.stage` ('applied'|'oa'|'interview'|'hr'|'offer'|'rejected') + timestamps + sent artifacts.
- `runs` first-class: status (queued/running/cancelled/failed/done), heartbeat, cancel flag, log.
- `events` (outbox: type, **class** ['domain'|'infra'], payload, created_at, processed_at) — the event bus.
- **`audit_log`** (Reviewer #2): immutable who-did-what-when on artifacts/decisions (user *and* AI actions) —
  distinct from `events` (automation) and `job_transitions` (state). Answers "why did this application look different?".
- `llm_calls` (prompt, response, provider, model, tokens, latency_ms, cost, task, at).
- **`apply_checkpoints`** (Reviewer #13): per-step progress of a multi-page application so a crash can resume.
- `embedding vector(768)` + index **deferred to P7**.

**Storage & security boundaries** (Reviewer #8, #10) — keep four storage concerns separate, never commingled:
**secrets** (API keys, login cookies/session — gitignored `.env` + `data/sessions/`), **settings** (LLM routing,
profiles, rules), **user data** (resumes, recruiter messages), **generated data** (scores, drafts, tailored
artifacts — reproducible/disposable). Services depend on **repository functions, never embedded SQL**.

## Phased build plan (each phase ends green & shippable)

### Phase 0 — Pin & refactor (stay on SQLite, stay green)
- **Characterization tests** for current behavior (storage, dedup, scoring with stub LLM, parsing) — the regression net.
- **Pluggable LLM provider registry** (capability-based; Ollama + one API provider; stub for tests) behind existing
  signatures, **with `llm_calls` logging + `confidence` in the score schema**.
- Carve out the **`services/` layer** over existing SQLite; re-point CLI + MCP. Behavior unchanged.
- Proper **enums + constants** (`job_hunt/enums.py`): `StrEnum`s for status/outcome/reply/LLM task+provider;
  schema `CHECK` constraints derived from them via `sql_in_list()` so DB and code can't drift; SQL kept in
  storage repository fns (services call them, never embed SQL).
- Verify login cookies aren't already in git history; scrub if so.

_Status: Phase 0 DONE except the directory move — deferred to P1 (see below). 27 tests green; CLI + MCP
behavior preserved; existing `data/jobhunt.db` migrated in place (added `llm_calls`, `scores.confidence`).
The test net surfaced a real bug — the LaTeX stripper discarded `\\cmd{arg}` content (bolded titles/sections
vanished before the LLM saw them) — now **FIXED**: `_read_latex` slices to the document body and preserves
command-argument text, so scoring runs against the full resume._

### Phase 1 — Postgres + foundations
- **Mechanical directory move** into `backend/` (deferred from P0) as the first commit — done alongside `api/`/`worker/`.
- Postgres+pgvector; `psycopg3` repo + `.sql` migrations; canonical dedup key. **SQLite→Postgres copy script
  is required, not optional** — the existing `data/jobhunt.db` holds real scored jobs worth preserving.

_Status (datastore slice DONE): `docker-compose.yml` runs pgvector pg16 on host **port 55432** (5432/5433
were taken locally). `storage/repo.py` switches backend via `DB_BACKEND` (sqlite=tests, postgres=prod);
`storage/pg.py` mirrors the SQLite repo, returning JSON/timestamps as text for parity. `migrations/0001_init.sql`
+ an in-code migration runner. Canonical dedup key now `company|title|location`. `scripts/sqlite_to_postgres.py`
copied the real data (19 jobs / 19 scores / 1 variant) with FK remapping. 33 tests green (2 gated Postgres tests)._
- **Browser Manager** + per-platform **Rate Limiter** (refactor `naukri.py`/`login.py` onto it; captcha/login-wall detection).
- **Job state machine** + `job_transitions`; **event bus** (`events` outbox + worker dispatcher).

_Status (state/events/runs slice DONE): `job_hunt/enums.py` gained JobState/RunStatus/EventType/EventClass;
`job_hunt/states.py` holds the transition graph + validated `transition_job()` (audits + emits); `events/bus.py`
is the in-DB outbox (`emit`/`dispatch_pending`). `jobs.state` + `job_transitions` + `events` + run-lifecycle
columns added to BOTH backends (SQLite SCHEMA/_migrate + Postgres `0002`). Scoring transitions jobs→SCORED;
discovery marks DISCOVERED. Verified on SQLite (39 tests) and Postgres (smoke). Worker dispatch loop = slice ④._
- **Search profiles** entity; discovery runs per active profile. Capture `applicant_count`/`posted_at`/`ats_platform`.
- `runs` state machine + heartbeat + cooperative cancel + scrape-health. **Idempotent re-scoring** gate.
- Worker (**APScheduler + event triggers**): active-hours window + per-day cap config (enforced at apply in P6).
- Define the abstract **plugin/Source contract** (Naukri the only impl).

_Status (worker slice DONE): `search_profiles` table + repo + service + CLI (`add-profile`/`profiles`) on both
backends (Postgres `0003`). `plugins/` defines the `Source` contract + registry (`NaukriSource` adapts the
crawler). `worker/`: pure `pacing` (active-hours incl. midnight-wrap + daily cap), `runner.run_discovery_cycle`
(wraps each cycle in a run: running→done/failed/cancelled + log + cancel-check + scoring), `scheduler` (APScheduler:
hours-gated discovery + event-dispatch loop). CLI `run-cycle`/`worker`. 48 tests green; Postgres verified.
NOTE: applicant_count/posted_at/ats_platform capture deferred to when enrichment lands (P4)._

### Phase 2 — FastAPI (local, authed)
- FastAPI over `services/`. **Bind 127.0.0.1; single-user token auth.** REST for jobs/scores/variants/runs/
  search-profiles/opportunities/events/settings; OpenAPI for the client. Clients poll `runs`/`events`.

_Status (API slice DONE): `job_hunt/api/app.py` — FastAPI over the services layer. `/health` (open) reports
datastore + LLM routing; all `/api/*` require a bearer token (`API_TOKEN` env, else ephemeral printed at startup),
CORS for the Vite dev origin. Endpoints: jobs (list/detail), resume-variants, search-profiles (list/create/enable),
score + discover (202, background), runs (list/detail/cancel), applications. `hunt serve-api` (uvicorn, 127.0.0.1).
54 tests green (TestClient); booted against Postgres and served real data with auth enforced.
DECISION: built as the `job_hunt/api/` subpackage (beside cli/worker/mcp_server); the physical top-level
`backend/` folder move is deferred to Phase 3 when `frontend/` lands and the split earns its keep._

### Phase 3 — React management UI (thin first)
- Vite+React+TS+TanStack Query + generated client. Ship **thin**: **Kanban driven by the job state machine** +
  Job detail (JD + scores + confidence + reasoning) first; then Resume vault, Runs/logs, **Settings**
  (LLM config: local model OR API key per task; **search profiles**; cost view).

_Status (UI slice DONE): `frontend/` at repo root (no disruptive package move). Vite + React 19 + TS + TanStack
Query + hand-written dark-dashboard CSS. `src/api.ts` typed client (bearer token + base in localStorage). Pages:
**Board** (Kanban by job state; score-band cards; click → detail panel with JD + variant scores + confidence +
"mark applied"), **Runs** (polling table + Discover/Score buttons), **Settings** (token/base, health, search-profile
list/add/enable). New `GET /api/board`. `npm run build` passes (tsc + vite). Run: `hunt serve-api` +
`cd frontend && npm run dev` → localhost:5173, paste the API token. (Browser screenshot skipped — Chrome extension
not connected.)_

### Phase 4 — Deepen the loop

_Status (enrichment slice DONE): migration `0004` + sqlite — `jobs.description_full`/`enriched_at`,
`scores.scored_against`/`input_hash`/`provider_model`. Scoring is now **idempotent + JD-aware**: a (job,variant)
pair re-scores only when the JD text or model changed (re-score-once after enrichment; plain re-run bills
nothing). `enrich/` service (fetcher-injectable) + Naukri `fetch_job_description` + `hunt enrich`. **Event
handlers wired** (`worker/handlers.py`): `JOB_DISCOVERED → enrich → JOB_ENRICHED → re-score` — the pipeline
now auto-advances through `dispatch_pending`. Fixed a `pg.get_job` schema-drift bug (missing state/full-JD cols).
63 tests green (idempotency, enrich, and end-to-end pipeline auto-advance verified on both backends).
Still to do in P4: resume tailoring, cover letters/outreach, company research, prioritization rank._

- **JD enrichment** → re-score (idempotent). **Company research** enrichment + **company memory**.
- **Prioritization rank** = score × freshness × low-applicant-count. **Opportunity queue** decisions
  (apply / defer / wait-for-referral).
- Resume **tailoring** + **version snapshots**; **fresh cover letters** + outreach (**recruiter CRM**); seed **answer-template library**. UI review/edit.

_Status (drafting slice DONE): migration `0005` + sqlite — `tailored_resumes` + `drafts` (kind: cover|outreach).
`DraftKind` enum. `RESUME_TAILOR` + `COVER_LETTER` prompts (prose, invent-nothing) in the Prompt Library.
`resume/tailor.py` (tailoring task) + `draft/cover.py` (drafting task) via the AI Gateway. `repo.best_scored_variant`
+ save/get tailored + drafts (both backends; apply service refactored to reuse it). `services.tailor_for_job` /
`draft_cover_for_job` / `list_drafts`; `POST /api/jobs/{id}/tailor|cover`, `GET …/drafts`; `hunt tailor|cover`.
82 tests green. Still open in P4: recruiter outreach/CRM, company research, answer-template library, prioritization rank._

### Phase 5 — More sources (plugins)
- Implement the plugin contract for LinkedIn / Wellfound / RemoteOK / Greenhouse / Lever. Cross-source dedup via the
  P1 key; per-source search profiles + rate limits + scrape-health.

_Status (RemoteOK slice DONE): canonical dedup moved to shared `sources/dedup.py`. `plugins/remoteok.py` —
public-JSON-API source (injectable `_fetch`), keyword-filtered, ships full JDs so jobs land already-ENRICHED
(skip the browser enrich step) and enter the scoring pipeline; cross-source dedup collapses the same role found on
Naukri. Generic `services.discover(source, …)` + `hunt discover --source`. 67 tests green; verified live end-to-end
(19 real RemoteOK jobs → Postgres, all enriched). LinkedIn/Wellfound (browser+auth) and Greenhouse/Lever
(per-company boards) remain — the point is proven: a new source = one file + register()._

### Phase 6 — Apply (review-before-submit, humanized, recoverable)

_Status (quality-gate slice DONE): `ATSPlatform` enum + `apply/ats.py` `detect_ats(url)` (greenhouse/lever/
workday/ashby/smartrecruiters/icims/naukri/remoteok/unknown, pure). **AI pre-submit reviewer** (`apply/reviewer.py`
+ `APPLICATION_REVIEW` prompt): compares resume + cover letter + answers vs the JD → `{ready, issues[severity,
field,message]}` via the AI Gateway (drafting task, stub-testable). `services.review_application(job_id, …)`
pulls full JD + best-variant resume + ATS; `POST /api/apply/review` backs the review queue. It NEVER submits.
79 tests green. Remaining: Playwright per-ATS form-fill + humanized pacing, checkpoint/resume, the React apply
review queue, submitted-snapshot recording, marquee notify-and-hold._

- **ATS detection** + per-platform adapters; form-fill from the **answer-template library** (truthful variation).
- **Humanized pacing** via Browser Manager; hard-enforce **per-day cap + active-hours**.
- **AI pre-submit reviewer** (Reviewer #17): an agent checks the filled application vs JD/resume and flags problems
  (missing keywords, contradictions, empty fields) *before* the human review queue.
- **Checkpoint/resume failure recovery** (`apply_checkpoints`) for multi-page flows.
- **Marquee/priority → notify-and-hold** (never auto-fill-submit).
- Pause → React **apply review queue** (preview/screenshot → approve → submit). Record the **submitted snapshot**;
  handle page-changed / submit-failed with replay + idempotency. Update the tracker.

### Phase 7 — Track, learn, notify + semantic

_Status (analytics slice DONE): `ApplicationStage` enum + `applications.stage` (migration `0006` + sqlite).
`repo.set_application_stage` + `services.advance_stage`. `services.analytics.dashboard()` — funnel, jobs-by-
state/source, LLM cost/tokens by task, source effectiveness (param-free `raw_select`, both backends).
`GET /api/analytics`, `PATCH /api/applications/{id}/stage`. React **Analytics tab** (funnel, cost metrics,
mini-tables). Frontend job detail also now surfaces **tailor / cover / AI-review** (JobActions). 86 tests green.
Still open in P7: learning loop, Telegram/Discord notifications, pgvector semantic match._

- **Interview-stage pipeline** (Applied→OA→Interview→HR→Offer→Rejected) + timestamps.
- **Metrics & analytics** (Reviewer #9, #18): jobs/day, match rate, response/interview/offer rates, avg recruiter
  response time, **source effectiveness & offer rate**, **resume-variant performance**, **company conversion rate**,
  **which prompt/model produced better resumes/tailoring** (joins `llm_calls` ↔ outcomes), tailoring time.
  **Cost dashboard** (from `llm_calls`).
- **Learning loop**: rejection → JD-vs-resume keyword-gap → future tailoring weight; interview → up-weight winning variant.
- Telegram/Discord daily report + priority alerts.
- Add `embedding` column + index + model + backfill → pgvector semantic job↔resume matching.

_Status (notifications slice DONE): `notify/` — `Notifier` protocol + Telegram + Discord (webhook, injectable
transport) + `NullNotifier`; `get_notifier()` from `NOTIFY_CHANNEL` env. `report.build_daily_report()` composes a
summary from the analytics dashboard (jobs by state, funnel, LLM spend); `send_daily_report()`. `hunt report [--send]`
+ a 20:00 worker cron job (no-op unless a channel is configured). 95 tests green; live report verified on real data.
Still open in P7: learning loop, pgvector semantic match._

## Verification

- **P0:** `pytest` green; `hunt selfcheck` validates each task's provider both local and with an API key swapped in;
  `llm_calls` rows appear; CLI + MCP unchanged.
- **P1:** `docker compose up -d db`; migrations apply; a discovery run creates a `runs` row running→done; a state
  transition writes an `events` row the worker consumes; cancel mid-run stops it; unchanged jobs don't re-score.
- **P2:** `uvicorn` on 127.0.0.1; unauthenticated request rejected; entities queryable.
- **P3:** `vite dev`; Kanban reflects job states; trigger discovery from UI → progress via `runs`/`events` polling;
  Settings flips a task Ollama↔API-key and toggles a search profile.
- **P4+:** enriched JD + company research visible; tailored resume + cover letter generate, are versioned, editable;
  (P6) AI reviewer flags a deliberately-weak application; a killed mid-apply flow resumes from its last checkpoint;
  submitted snapshot recorded.
- Every phase keeps prior CLI/MCP/tests green.

## Future considerations (deferred — NOT Phase 0; revisit when real use reveals the need)

Recorded so they aren't lost, but explicitly out of scope now — adding them speculatively is the
over-abstraction trap. Build first; let real usage justify each.

- **Feature flags** (Reviewer #3) — a simple config/table to toggle capabilities (company research, AI reviewer,
  semantic search) during dev. Add when a half-built feature needs to ship dark; trivial to retrofit.
- **Notification preferences** (Reviewer #6) — channel × priority × delivery matrix (Telegram/Discord/email/desktop).
  P7 ships one channel; generalize when a second is actually wanted.
- **Recommendation engine surface** (Reviewer #7) — the rules/opportunity layer already *produces* a recommendation
  label; a richer "AI career advisor" UI on top of it is a later UX layer, not new core.
- **Backup & export** (Reviewer #11) — `pg_dump` + CSV/JSON export of applications/recruiters/resumes. Low effort;
  add once there's data worth losing.
- **Knowledge-graph queries** (Reviewer #12) — *no graph DB*; the relational FKs (job↔company↔recruiter↔resume↔
  application) already encode the relationships. Add graph-style query views ("which Kafka companies interviewed me?",
  "which resume wins for fintech?") when the analytics need them.

_Scaling refinements from the 2nd review — deferred until scale actually demands them:_
- **Priority task queue** — `events.priority` so user-facing work (apply) preempts background work (embeddings).
  Add columns when heavy AI steps land (P4); no separate broker.
- **Read models / CQRS** — for fast dashboards (today's applications, best companies, AI cost), use **Postgres
  materialized views / summary tables** refreshed off domain events. NOT full CQRS — that's overkill for one user.
- **Redis cache** — only if multi-user; until then caching stays DB-backed (idempotent scores, `companies`, `llm_cache`).
- **Dedicated workflow engine** (Temporal/Airflow) — only if the outbox+state-machine+handlers pipeline outgrows
  in-DB orchestration. It won't for a single user.
- **`career/` domain-package reorg** — grouping packages under a `career/` namespace; deferred as pure churn on
  working, tested code.

## Risks / notes

- **No tests today** → P0's characterization net is non-negotiable.
- **Over-abstraction** is the new risk after this review: event bus stays an in-DB outbox, plugins stay one impl
  until P5, scheduler stays cron+events. Don't build broker/reactive infra speculatively.
- **Cost blowup** — idempotency gate + `llm_calls` cost tracking + cost dashboard keep paid providers honest.
- **Scraper fragility / ToS** — `config/selectors/naukri.json` referenced by code doesn't exist yet (dead fallback);
  scrape-health detects blocked/expired sessions; review-before-submit limits account-flag risk.
- **Checkpoint complexity** — apply-resume is the trickiest engineering; keep checkpoints coarse (per page/step), and
  always re-validate page state on resume rather than trusting a stale checkpoint.
- **Secrets** — login cookies + API keys in `.env`; 127.0.0.1 + local auth keep the credit-spending, submitting app off the LAN.
- **Scope** — large; build + review one phase at a time.
