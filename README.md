# job-hunt — a personal "Career OS"

A self-hosted, quality-first job-hunt platform. It discovers jobs across boards, scores
each against your résumés with an LLM, enriches to the full JD, **tailors your résumé and
drafts cover letters / recruiter outreach**, runs an **AI pre-submit review**,
**auto-fills ATS application forms** (Greenhouse/Lever — for *you* to submit),
**triages your inbox into pipeline signal**, tracks the interview pipeline, and reports
analytics — driven from a **React web UI**, a REST API, a CLI, or any MCP host.

Everything the AI does is grounded in **your context** — paste your résumé/background once
(Settings → Career context) and it's injected into every score, tailor, cover letter, and review.

**Product thesis:** be a *highly efficient human, not a bot* — 20–40 targeted, tailored
applications beat 300 generic ones. Every automation saves time, improves quality, or aids a
decision **while you keep control of what matters** (review before submit).

Runs on your machine. Local LLM (Ollama) by default = **$0**; any task can be pointed at an
API key instead. **Groq** (free tier, LPU hardware) is a zero-cost cloud option for heavy
tasks — set `GROQ_API_KEY` and route drafting/structuring there; the client rotates across
keys on rate-limit and falls back to local Ollama automatically.

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

## Run it all with Docker

```bash
# From the repo root — generates a shared API token (into ./.env, gitignored),
# builds all images, and starts db + api + worker + frontend
make up
```

- **UI:** http://localhost:8770 — nothing to configure: nginx injects the shared token, so
  there's no token to paste (leave the "API base" field blank; it proxies `/api/*` automatically).
- **API (direct):** http://localhost:8000 (also exposed for debugging/CLI tools).

Two features are intentionally host-only (no GPU/browser passthrough in containers):

- **Ollama** runs on your Mac; containers reach it via `http://host.docker.internal:11434`.
- **Naukri crawl** and **headful ATS auto-fill** (`uv run hunt discover --source naukri`,
  `uv run hunt apply-fill <id>`) must be run on the host with `cd backend && uv run hunt …`.

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
`API_TOKEN`, `DB_BACKEND`, `DATABASE_URL`, per-task `LLM_<TASK>_PROVIDER/MODEL`
(+ `OPENAI_API_KEY` etc.), `NOTIFY_CHANNEL`, `EMBED_PROVIDER`.

**Inbox triage (optional):** to read/structure your own Gmail, enable 2-Step Verification,
create an [App Password](https://myaccount.google.com/apppasswords), and set all three of
`EMAIL_IMAP_HOST` / `EMAIL_ADDRESS` / `EMAIL_APP_PASSWORD` in `backend/.env.local`. The app
password is only ever sent to your mail server — never logged, stored, or put in an LLM prompt.

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
| `context <file>` | set/show the career context injected into every AI call |
| `applicant --set key=value …` | standing application answers (name, notice period, CTC…) used by auto-fill |
| `apply-fill <job_id>` | open the job's ATS form, auto-fill it from your data, stop for you to submit |
| `email sync` / `email list` / `email show <id>` | pull + structure your inbox, browse triaged mail |
| `email action <id> --kind draft_reply\|apply_label\|archive [--confirm]` / `email dismiss <id>` | propose then confirm a reversible mail action |
| `outreach add --company … --name … --email … --subject … --body-file <file\|->` | save a cold email as a draft (never sends) |
| `outreach list [--status]` / `outreach show <id>` / `outreach edit <id> …` / `outreach cancel <id>` | review and manage cold emails |
| `outreach send <id> [--confirm]` | without `--confirm`: preview only; with it: send once over SMTP |
| `outreach followups` | draft the one follow-up for emails with no reply after 6 days |
| `profiles` / `add-profile …` | saved searches |
| `run-cycle` / `worker` | one discovery+scoring cycle / the long-running scheduler |
| `report [--send]` | daily summary (Telegram/Discord if configured) |
| `embed` / `semantic "query"` | pgvector semantic search (Postgres only) |
| `serve-api` / `serve-mcp` | REST API / MCP stdio server |
| `db "SELECT …"` | ad-hoc read query against the active backend |

## Cold email (SMTP)

Write the email in Claude Code (ai-job-search's `/cold-email`, or any MCP host via the
`outreach_save_draft` tool), review it here, and send it yourself. Agents can save and list
drafts but **cannot send** — there is no MCP send tool.

**One-time setup** (laptop only — never put the app password in CI):

1. Gmail → turn on 2-Step Verification → create an [App Password](https://myaccount.google.com/apppasswords).
2. In `backend/.env.local` set the inbox trio **and** SMTP (sending requires the inbox,
   because replies are checked before any follow-up):
   ```bash
   EMAIL_IMAP_HOST=imap.gmail.com
   EMAIL_ADDRESS=you@gmail.com
   EMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
   EMAIL_SMTP_HOST=smtp.gmail.com     # port 465 (implicit TLS) is the only supported port
   ```
3. Set your name, phone and LinkedIn once — they form the signature appended to every
   email, so contact details are never AI-written:
   `uv run hunt applicant --set first_name=… last_name=… phone=… linkedin_url=…`

**Day to day**

```bash
uv run hunt outreach add --company Acme --name "Priya Sharma" --email priya@acme.com \
    --subject "Backend engineer, NestJS/PostgreSQL" --body-file note.txt
uv run hunt outreach send 7             # preview only
uv run hunt outreach send 7 --confirm   # sends once
uv run hunt email sync                  # a reply marks it replied and cancels its follow-up
uv run hunt outreach followups          # after 6 days with no reply: one short follow-up draft
```

**Guardrails:** plain text only; 80–120 words is the target (a warning above 150);
unfilled placeholders such as `[Name]` block sending; each email is sent at most once,
even if `send` runs twice; at most 15 sends in any rolling 24 hours (start with ~5/day for
a new address); exactly one follow-up, threaded under the original; any reply stops it.
The scheduled GitHub Actions job (`.github/workflows/discover-jobs.yml`) only *drafts* due
follow-ups and pings Telegram — it has no email credentials.

**Writing rules** (checked by `check_email_text`): one line on who you are, one real,
specific result from your résumé, one line on why this company, one clear ask (a short
call, or the right person to talk to). No "I hope this email finds you well", no
"passionate", no inflated claims.

## Testing

```bash
cd backend && uv run pytest -q      # SQLite fast path; Postgres-gated tests run if the DB is up
```

## Layout

```
backend/                Python. All backend code + its data/config/scripts/tests.
├── job_hunt/           services/ · llm/ · storage/ (db.py sqlite, pg.py postgres, repo.py façade)
│                        plugins/ · browser/ · events/ · states.py · enrich/ · scoring/
│                        resume/ · draft/ · apply/ (ATS auto-fill) · learn/ · embed/ · notify/
│                        email/ (stdlib IMAP reader + SMTP sender) · worker/ · api/ · mcp_server/ · cli/
├── migrations/         numbered .sql (Postgres); SQLite schema is in storage/db.py
├── tests/              pytest suite
├── scripts/            one-off tools (SQLite→PG migration, naukri debug, launchd install)
├── config/             CSS selectors etc.
├── data/               runtime data (SQLite DB, logs, resume vault) — mostly gitignored
├── pyproject.toml      Python deps + `hunt` CLI entrypoint
└── uv.lock

frontend/               React + TS + Vite + TanStack Query (Board · Inbox · Content · Runs · Analytics · Settings)
docs/                   career-os-plan.md (architecture + build status), engineering-standards.md
docker-compose.yml      Boots the Postgres+pgvector container
```

## Cost & privacy

$0 by default (local Ollama, local Postgres). Point any hard task at an API key when you
want more quality; `llm_calls` tracks every token and dollar. The API binds to `127.0.0.1`
and requires a token even locally — it can spend credits and submit applications.

**Inbox triage** reads over IMAP with an app password that never leaves your machine. Email
content is treated as **untrusted data** (never executed as instructions), and every mailbox
action — draft reply / label / archive, **never send or delete** — requires your explicit
confirmation. Auto-fill likewise stops at the review screen for you to submit.

**Cold email** is the one place mail is sent, and only by you: `outreach send <id> --confirm`
(or the API with `{"confirm": true}`). Logs record ids and outcomes only — never the
password, the body or the recipient.
