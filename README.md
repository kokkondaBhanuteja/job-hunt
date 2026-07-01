# job-hunt

Personal job-hunt automation. Lives on your Mac, runs entirely on local LLM (Ollama),
stores everything in one SQLite file, driven from any MCP host (Claude Code / Goose /
Cherry Studio / Continue.dev). Zero APIs, zero cloud, zero recurring cost.

## What it does (v0)

1. **Parses resumes from a vault.** Drop `.tex` or `.pdf` files in `data/resumes/`.
   Each one becomes a "variant" — the toolkit picks which variant best fits each job.
2. **Discovers jobs on Naukri.com.** Playwright crawls the public listing pages
   with a persisted session (log in manually once, reused after).
3. **Scores every job × every variant** with `qwen2.5:7b` running locally on Ollama.
4. **Exposes everything as MCP tools** — talk to any MCP host:
   - *"What's worth applying to today?"*
   - *"Show me job 42"*
   - *"Log that I applied to #2 with the backend-node variant"*

No HTML dashboard. The MCP host is the UI.

## Setup (one-time, ~10 min)

```bash
# 1. Ollama (the LLM)
brew install ollama
brew services start ollama
ollama pull qwen2.5:7b

# 2. The project
cd ~/Documents/job-hunt
uv sync
uv run playwright install chromium

# 3. Seed the resume vault (drop .tex / .pdf files in)
ls data/resumes/   # backend-node.tex etc.

# 4. Smoke-test that everything is wired
uv run hunt selfcheck
```

## Daily flow (the value)

```bash
# Overnight (launchd will run this for you, see scripts/install-schedule.sh)
uv run hunt discover-naukri --keyword "nestjs backend" --location bangalore --pages 3
uv run hunt score

# Morning
uv run hunt top --min-score 70 --limit 10
# … or, more naturally:
# (in your MCP host) "what's worth applying to today?"
```

## Wiring the MCP server into a host

The MCP server speaks stdio. Add this to your host's config:

### Claude Code (`.mcp.json` in any project)

```json
{
  "mcpServers": {
    "job-hunt": {
      "command": "uv",
      "args": ["--directory", "/Users/BackendIntern/Documents/job-hunt", "run", "hunt", "serve-mcp"]
    }
  }
}
```

### Goose / Cherry Studio / Continue.dev

Same command + args, dropped into their MCP-server config. All of them speak the
same stdio protocol.

## Layout

```
job-hunt/
  job_hunt/
    llm/ollama.py            chat() helper, model-by-task (scoring vs drafting)
    resume/parser.py         pdf/latex → structured JSON via qwen
    sources/naukri.py        Playwright crawler with persisted session
    scoring/match.py         qwen scores each (job, variant) pair
    storage/db.py            SQLite — single file at data/jobhunt.db
    mcp_server/server.py     FastMCP server exposing the workflow as tools
    cli/main.py              `uv run hunt …` subcommands
  config/
    selectors/naukri.json    Hot-patchable CSS selectors (override defaults)
  data/
    resumes/                 Your hand-maintained .tex / .pdf vault
    jobhunt.db               All state (open in DB Browser for SQLite)
    sessions/naukri/         Persistent Playwright profile (login state)
```

## Cost

$0/month. No keys, no cloud, no expiring tokens. Just your Mac and Ollama.

## Adding a new source (Foundit, Greenhouse, ...)

1. Add `job_hunt/sources/<name>.py` modeled on `naukri.py`
2. Add a `discover_<name>` MCP tool in `mcp_server/server.py`
3. Add a `discover-<name>` CLI subcommand in `cli/main.py`

Everything else (scoring, top-matches, application logging) is source-agnostic.
