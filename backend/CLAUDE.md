# backend/ — engineering standards (MANDATORY)

> **AI agents — Claude Code, Cursor, Codex, Copilot, and any other tool:**
> This file is your contract for every change under `backend/`. Read it *before*
> proposing edits. Following it is not optional. If a rule blocks the change you
> were asked to make, stop and ask the user — do not silently break the rule.

Scope: everything under `backend/`. Python 3.12+ + FastAPI + Postgres/SQLite (raw
SQL, no ORM) + APScheduler worker + MCP server + CLI. Single Python package
`job_hunt` at `backend/job_hunt/`.

This doc is our tailored subset of authoritative Python guidance grounded in the
actual codebase:

- **PEP 8** — style (imports, naming, line length, whitespace)
- **PEP 20** — Zen of Python (explicit > implicit; errors never pass silently)
- **PEP 257** — docstrings (triple-quoted, imperative, module + public function)
- **Django coding style** — informed choices where useful (line length, imports)
- **FastAPI large-application pattern** — informed choices for `api/` layout
- **The audit of `backend/job_hunt/`** — every rule below matches what the code
  already does, so nothing is aspirational

---

## Agent quick-check (run through this on every change)

Before you finalize any edit under `backend/`:

- [ ] Every function signature is fully type-hinted. Modern syntax: `list[X] | None`,
      not `Optional[List[X]]`. No `Any` at boundaries unless narrowed immediately.
- [ ] Every module you create has a docstring. Every public function you add has
      a one-line imperative docstring ("Return the top matches…" not "Returns…").
- [ ] `from __future__ import annotations` is the first non-docstring line of
      any module that contains code.
- [ ] Imports are grouped: stdlib → third-party → `job_hunt.*` local, blank line
      between groups. Absolute imports only.
- [ ] Line length ≤ 100 (soft target). Hard ceiling 112.
- [ ] Enums, not raw strings, for enumerated values: `JobState.SCORED`, not
      `"scored"`. Exceptions: enum definitions themselves, SQL list-in-clauses,
      Pydantic request models at the HTTP boundary.
- [ ] Every service function returns a plain dict or list. On expected failure
      it returns `{"error": "<human message>"}`. `api/app.py::_unwrap` converts
      that to 404/400. Services **never raise** for user-fixable failures.
- [ ] Every SQL query is parameterized (`?` for SQLite, `%s` for Postgres) and
      wrapped in a `with connect() as conn:` block.
- [ ] `get_logger(__name__)` for operational/diagnostic logging.
      `print()` is allowed only in `cli/*.py`, in interactive prompts
      (`sources/login.py`), and in library code gated by an explicit `verbose`
      flag threaded from a CLI caller.
- [ ] Backend DTO shape changes are mirrored in `frontend/src/lib/api.ts` in the
      **same PR**. Backend `JobState` / `states.py` changes are mirrored in
      `frontend/src/pages/Board/Board.tsx::COLUMNS` in the **same PR**.
- [ ] `uv run pytest -q` passes locally.
- [ ] `uv run ruff check .` passes (or you've documented an explicit `# noqa`).

If you cannot check every applicable box, do not claim the change is complete.

---

## Rules we follow (the source of truth)

### Correctness

1. **Type hints on every signature.** Modern syntax (`list[X] | None`). No `Any`
   at boundaries unless narrowed immediately with a type guard.
2. **Every module has a docstring.** Imperative mood, describes what the module
   owns. First statement in the file after `from __future__ import annotations`.
3. **Every public function has a one-line imperative docstring.** "Return X",
   "Insert Y", "Emit Z". Storage helpers whose behavior is fully captured by
   their name (`insert_job_if_new`) are exempt. Service functions and API
   handlers are not.
4. **`from __future__ import annotations`** at the top of every module that
   contains code. Skipped only in bare re-export `__init__.py` files.
5. **Enums for enumerated values.** Compare against `JobState.SCORED`,
   `DraftKind.COVER`, `RunStatus.FAILED` — never raw strings. Allowed exceptions:
   inside enum definitions, in SQL constants like
   `WHERE state IN ('scored', 'enriched')`, and Pydantic request models at the
   HTTP boundary where `status: str = "applied"` is idiomatic.

### Structure & style

6. **Import order:** future → stdlib → third-party → `job_hunt.*` local.
   Blank line between groups. Absolute imports only.
7. **Naming:** `snake_case` for functions, variables, modules, packages;
   `PascalCase` for classes and Pydantic models; `UPPER_SNAKE_CASE` for
   module-level constants; single leading underscore for module-private helpers
   (`_call`, `_parse_json`).
8. **Line length ≤ 100 (soft target), 112 (hard ceiling).** Break *before*
   binary operators, not after. Enforced by ruff (see rule 18).
   The following categories are exempt from the soft target (but still bound by
   the 112 hard ceiling), because forcing a break hurts readability more than it
   helps:
   - **Prompt template strings** (`llm/prompts.py`, `scoring/match.py`) — breaking
     mid-string changes what the LLM sees.
   - **SQL statements** inside triple-quoted `SCHEMA` strings — column
     definitions align to a grid; breaking breaks the grid.
   - **Single-line docstrings** (PEP 257 says one-liners stay on one line).
9. **File size:** service files ≤ 400 lines. `storage/db.py` and `storage/pg.py`
   are exempt (they mirror each other and every table's CRUD lives together —
   splitting hurts more than it helps at this size). `cli/main.py` is exempt
   (subcommand catalog).

### Data & safety

10. **All SQL is parameterized.** `?` for SQLite, `%s` for Postgres. F-string
    SQL is allowed *only* for interpolating trusted internal column-name
    constants (`_PROFILE_COLS`, etc.), never user input.
11. **Every DB query uses `with connect() as conn:`** — never a bare cursor.
    Transactions commit via the context manager's exit.
12. **Services never raise for user-fixable failures.** Return
    `{"error": "human message"}`. `api/app.py::_unwrap` maps that to 404/400.
    Raise only for infrastructure failures (LLM provider down, DB unreachable);
    those become 500s at the API boundary.

### Logging

13. **Every log line goes through `get_logger(__name__)`** from
    `job_hunt.logging_config`. Configuration is lazy and idempotent.
14. **`print()` is a CLI-only tool.** Allowed in `cli/*.py`, in interactive
    prompts (`sources/login.py`), and in library code gated by an explicit
    `verbose` flag threaded from a CLI caller. Everywhere else, use the logger.

### Cross-boundary (frontend contract)

15. **Backend DTO changes are mirrored in `frontend/src/lib/api.ts`** in the
    same PR. `api/dto.py` and the TS interfaces stay 1:1. See `frontend/CLAUDE.md`
    rule 2 for the mirror obligation.
16. **`states.py` transitions or `enums.py::JobState` value changes must be
    mirrored in `frontend/src/pages/Board/Board.tsx::COLUMNS`** in the same PR.
    Backend adds a state → frontend adds (or maps into) a column.

### Process

17. **Testing:** pytest, function-based (`def test_*`), module docstring on
    every test file, shared fixtures in `backend/tests/conftest.py`. No
    `class Test*` collections. Helper fakes named `_FakeX` / `_FlakyX` /
    `_StubX`. `@pytest.mark.parametrize` for tables of similar cases.
18. **Every PR runs `uv run pytest -q` and `uv run ruff check .` locally**
    from `backend/`. No merging on red.

---

## Rules we explicitly do NOT follow (and why)

| Rule | Source | Why we skip |
|---|---|---|
| Line length 88 (Black default) | Django | Codebase practices ~100 already; forcing 88 = mass reflow for zero readability win. Ruff configured to 100. |
| `#NOQA` for backwards-compat imports | Django | Not a compat-heavy codebase. Delete unused imports; don't preserve them. |
| Split `api/app.py` into `api/routers/*.py` per feature | FastAPI large-app | `app.py` is ~300 lines. Splitting 20 routes is ceremony. **Revisit at 500 lines.** |
| Class-based tests + `unittest.TestCase` | Django, stdlib | pytest function-based is the standard here. |
| Docstring on every private helper | Google style | Would drown `storage/*.py` in boilerplate for pure SQL CRUD. |
| Split storage into `storage/<domain>/` | Growth | 1086 + 783 lines is heavy but flat and readable. Revisit at 1200. |
| ORM (SQLAlchemy, Django ORM) | Common Python | Raw SQL is the intentional style — see `docs/career-os-plan.md`. |
| `from __future__ import annotations` in bare `__init__.py` re-export files | PEP 8 style | Adds nothing when the module has no runtime code. |
| Structural pattern matching (`match`) | PEP 634 | The current `if/elif` chains are clearer for the small number of branches we have. |

Every declined rule is a *deferral*, not a rejection. When a "Revisit at N" trigger fires, promote the rule.

---

## Revisit thresholds

- `api/app.py` > **500 lines** → split into `api/routers/*.py` per FastAPI's
  large-application pattern.
- `storage/db.py` or `storage/pg.py` > **1200 lines** → split by domain
  (`storage/jobs.py`, `storage/resumes.py`, `storage/drafts.py`), keeping the
  SQLite/Postgres pair together per domain.
- **15+** files in `services/` → consider `services/<domain>/` subfolders
  (discovery, drafting, apply, ...).
- A second contributor joins → adopt `CLAUDE.md` per subfolder for boundary docs.
- Public function docstring coverage drops below **60%** → make rule 3
  mandatory across storage too.

---

## Where things go

| Adding… | Put it in… |
|---|---|
| A REST endpoint | `job_hunt/api/app.py` (until 500 lines; then `api/routers/`) |
| A response DTO | `job_hunt/api/dto.py` (Pydantic BaseModel) |
| A Pydantic request model | `job_hunt/api/app.py` (top of file, above routes) |
| Business logic (called by API + CLI + MCP + worker) | `job_hunt/services/<domain>.py` |
| Raw SQL query | matching `storage/db.py` **and** `storage/pg.py` (mirror both) |
| A repository façade export | `storage/repo.py` (one line per symbol) |
| A CLI subcommand | `job_hunt/cli/main.py` |
| An MCP tool | `job_hunt/mcp_server/server.py` |
| A background job handler | `job_hunt/worker/handlers.py` |
| A source plugin | `job_hunt/plugins/<name>.py` + `register()` in that file |
| An LLM provider | `job_hunt/llm/providers/<name>.py` |
| An enum value | `job_hunt/enums.py` (mirror in frontend if it's a state) |
| A state machine transition | `job_hunt/states.py::ALLOWED_TRANSITIONS` |
| An event type | `job_hunt/enums.py::EventType` + emit site |
| A migration | `backend/migrations/00NN_<name>.sql` (Postgres only) |
| A SQLite schema change | Update inline `SCHEMA` string in `storage/db.py` |
| A test | `backend/tests/test_<subject>.py` |
| A shared fixture | `backend/tests/conftest.py` |
| A one-off dev script | `backend/scripts/<name>.py` or `<name>.sh` |
| A config selector | `backend/config/selectors/<source>.json` |

---

## PR checklist

Automated (CI/build):

- [ ] `uv run pytest -q` passes.
- [ ] `uv run ruff check .` passes.

Review judgment:

- [ ] Every new function is fully type-hinted; no `Any` at boundaries.
- [ ] Every new module has a docstring; every new public function has a one-line
      imperative docstring.
- [ ] No raw string literals for enumerated values (rule 5).
- [ ] Services return dicts, `{"error": …}` on failure; no raise for user-fixable
      failures (rule 12).
- [ ] All SQL parameterized (rule 10); every query inside `with connect() as conn:` (rule 11).
- [ ] Backend DTO changes mirrored in `frontend/src/lib/api.ts` (rule 15).
- [ ] `JobState` / `states.py` changes mirrored in Board `COLUMNS` (rule 16).
- [ ] Names explain the *what*; comments explain the *why*.
- [ ] New tests are function-based, live in `tests/`, and have a module docstring.

---

## Extended rules for AI assistants

These are the same rules restated imperatively for AI tools:

1. **Reuse before creating.** Search `job_hunt/` for an existing service /
   storage helper / plugin before adding one. If a close match exists, extend
   it via parameters, not by copying.
2. **Follow the folder layout** in "Where things go" above. Do not invent new
   top-level folders. If you think one is genuinely needed, ask the user first.
3. **Read this file at the start of every session** that touches `backend/`.
   Do not rely on memory of a previous session.
4. **Update this file in the same change** whenever the scope, rule set, or a
   "revisit threshold" changes.
5. **Types are strict.** Do not add `Any` to silence a type checker. If you
   need `Any`, narrow it immediately with a type guard — never let it leak into
   an exported signature.
6. **Do not hardcode enumerated values.** State strings, event types, ATS
   platforms, provider names — all live in `enums.py`.
7. **Service functions return dicts.** Do not raise for user-fixable failures.
   If your new service needs to signal an expected error, return
   `{"error": "human message"}` — never `raise ValueError`.
8. **Do not add dependencies without asking.** The current dep list is
   deliberate and reviewed. If a task needs a new library, stop and ask.
9. **Do not disable ruff rules, mypy checks, or tests to make CI pass.** If a
   rule is wrong, propose a change to this file — don't bypass.
10. **Verify before claiming done.** Run `uv run pytest -q` and
    `uv run ruff check .` from `backend/`. Report the actual output; do not
    assume.

---

## Governance

If a rule stops helping, propose a change in a PR against this file — same
review bar as code. Silent exceptions are not fine; documented ones are.
Revisit this doc quarterly (or when a "revisit threshold" fires).
