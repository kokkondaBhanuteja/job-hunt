# Operations runbook

How this job search runs day to day: what runs where, how it is configured, and how to
fix the usual problems. Secrets are never written here — only their names.

## The two parts

| Part | Repo | Runs | Does |
|---|---|---|---|
| **job-hunt** (this repo) | `kokkondaBhanuteja/job-hunt` | GitHub Actions 3x/day + the laptop CLI | Finds jobs, keeps India / open-remote only, scores them, sends Telegram alerts, stores and sends cold emails, drafts follow-ups |
| **ai-job-search** | a local-only copy (never pushed) at `~/Documents/ai-job-search` | Claude Code on the laptop | Tailored CV + cover letter (`/apply`), interview prep (`/interview`), writing cold emails (`/cold-email`) |

They talk through job-hunt's MCP server, registered in ai-job-search with:

```bash
claude mcp add job-hunt -s local -- uv run --directory ~/Documents/job-hunt/backend hunt serve-mcp
```

**Daily loop:** Telegram alert → open Claude Code in `~/Documents/ai-job-search` →
"show my new matches from job-hunt" → `/apply <link>` or `/cold-email …` → you submit /
you send (`hunt outreach send <id> --confirm`).

## Scheduled job (`.github/workflows/discover-jobs.yml`)

- Runs at 08:47, 14:47, 20:47 IST (GitHub may start scheduled runs late), or by hand: Actions → discover-jobs → Run workflow
  (`gh workflow run discover-jobs -R kokkondaBhanuteja/job-hunt --ref developer`).
- Order: score anything left queued → discover → score new jobs → draft due follow-ups.
- Limit 45 minutes; a failure **or timeout** sends a Telegram alert with the run link.
- No email credentials in CI — it can never send email.

### GitHub configuration (Settings → Secrets and variables → Actions)

| Kind | Name | Purpose |
|---|---|---|
| Secret | `DATABASE_URL` | Neon Postgres (Singapore), direct connection, `?sslmode=require` |
| Secret | `GROQ_API_KEY` | Main scoring model |
| Secret | `GEMINI_API_KEY` | Fallback when Groq rate-limits |
| Secret | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Alerts |
| Variable | `GROQ_MODEL` | `openai/gpt-oss-120b` |
| Variable | `GEMINI_MODEL` | `gemini-flash-lite-latest` |
| Variable | `API_SOURCES` | `remoteok,weworkremotely,workingnomads,amazon,himalayas,instahyre` |

Set secrets in the browser or with `gh secret set -f <file>`. **Never** use
`gh secret set NAME` through a non-interactive shell (e.g. Claude Code's `!`): it cannot
prompt, so it saves an empty secret. Never paste a secret into a chat.

## Laptop configuration (`backend/.env.local`, git-ignored)

Each name once (the first occurrence wins), `NAME=value`:

```
DB_BACKEND=postgres
DATABASE_URL=            # same Neon string as the GitHub secret
GROQ_API_KEY=
GEMINI_API_KEY=
LLM_SCORING_PROVIDER=groq
LLM_SCORING_MODEL=openai/gpt-oss-120b
LLM_SCORING_FALLBACK_PROVIDER=gemini
LLM_SCORING_FALLBACK_MODEL=gemini-flash-lite-latest
NOTIFY_CHANNEL=telegram
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
# Cold email (laptop only):
EMAIL_IMAP_HOST=imap.gmail.com
EMAIL_ADDRESS=
EMAIL_APP_PASSWORD=
EMAIL_SMTP_HOST=smtp.gmail.com
```

Quick checks: `uv run hunt notify-test` (Telegram), `uv run hunt profiles`,
`uv run hunt watch list`.

## Job sources and the location filter

| Source | Notes |
|---|---|
| Himalayas | Search API with `country=IN` — India-eligible jobs only |
| Instahyre | India-only; the site's own search endpoint, used politely (3 pages x 35, 1.5 s apart, stops on first error) |
| Watchlist (48 companies) | Greenhouse / Lever / Ashby / Workable / Workday boards; Workday filtered to India + "software engineer" and paged |
| We Work Remotely, Working Nomads, Remote OK | Remote boards; each job's real region is stored |
| Amazon | Keyword search |
| Not used | Google (public API retired, 404), Jobspresso (403 from GitHub runners), NoDesk (no location data), LinkedIn/Glassdoor (terms forbid scraping), Naukri in CI (needs login — laptop only) |

`backend/job_hunt/sources/location.py` keeps a job only if it is in India (or an Indian
city), or remote with no non-Indian restriction ("Remote", "Worldwide", "APAC",
"Remote - Asia Only"). It runs before saving, so dropped jobs are never scored.
`JOB_LOCATION_FILTER=off` disables it.

Watchlist: `~/job-hunt-watchlist.py` (idempotent) —
`uv run --directory ~/Documents/job-hunt/backend python ~/job-hunt-watchlist.py`.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Run times out, nothing scored | Slow saves | Fixed by per-thread connection reuse in `storage/pg.py`; the next run scores the backlog first |
| `403 model_permission_blocked_org` (Groq) | Models blocked at the Groq org level | console.groq.com/settings/limits → enable the model |
| `402 prepayment credits are depleted` (Gemini) | Prepaid project with zero balance | Use a free-tier project key, or add credit |
| `404` for a model | Model retired | Set `GROQ_MODEL` / `GEMINI_MODEL` to a listed model |
| `429` from Workday | Too many requests from one IP | Wait; the cloud job's 4 runs/day are well under the limit |
| A source 403s only in CI | Site blocks datacenter IPs | Remove it from `API_SOURCES`; run it from the laptop if needed |
| App on laptop still uses SQLite | `DB_BACKEND=postgres` missing in `.env.local` | Add it (see above) |

## Security notes

- In August 2026 a worm with access to this GitHub account rewrote a commit and added a
  hidden `.vscode/tasks.json` that ran a JavaScript payload disguised as a font
  (`public/fonts/fa-solid-500.woff2`) whenever the folder was opened in VS Code. It was
  removed on 2026-11-24. Other repos on the account need the same cleanup.
- Before opening any repo in VS Code — especially "take-home assignment" repos — check
  `.vscode/tasks.json` for `"runOn": "folderOpen"` and `.vscode/settings.json` for
  `task.allowAutomaticTasks`.
- Keep 2FA on; review SSH keys, tokens and OAuth apps if anything looks off; rotate any
  key that was ever pasted into a chat.

## Open items (2026-11-25)

- Confirm the first run after the connection fix scores the queued backlog and sends alerts.
- Clean the remaining infected repos on the account (after securing the account).
- Optional: phone access to review/approve cold emails would need an always-on server
  (e.g. Oracle free tier) running the API + web UI behind Cloudflare Tunnel.
