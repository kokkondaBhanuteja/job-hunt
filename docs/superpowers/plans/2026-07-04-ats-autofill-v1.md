# ATS Auto-Fill v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user open a Greenhouse/Lever application form that gets auto-filled from their stored data, stopping at the review screen so they submit by hand.

**Architecture:** A generic, ATS-agnostic filler (`apply/formfill.py`) reads a declarative per-ATS profile (`config/formfill/<ats>.json`) and maps stored data — a new `applicant_profile` singleton, the best résumé variant, the User Context, and any existing cover draft — onto form fields via a small `FormPage` protocol. A `_FakePage` makes fill logic hermetically testable; a Playwright adapter drives the real browser. Exposed by CLI + MCP + API/UI as thin adapters. Never auto-submits.

**Tech Stack:** Python 3.12, FastAPI, Playwright (existing `browser/`), SQLite + Postgres (raw SQL), pytest, React 19 + TanStack Query (frontend).

## Global Constraints

Every task implicitly includes these (from `backend/CLAUDE.md` / `frontend/CLAUDE.md`):

- `from __future__ import annotations` is the first non-docstring line of every Python module with code.
- Full modern type hints (`list[X] | None`); module + public-function imperative docstrings.
- Imports grouped stdlib → third-party → `job_hunt.*`; absolute imports only.
- Enums not raw strings for enumerated values; Pydantic request models at the HTTP boundary may use `str`.
- Service functions return plain dicts / lists; `{"error": "<msg>"}` on user-fixable failure; never raise for those.
- All SQL parameterized (`?` SQLite, `%s` Postgres) inside `with connect() as conn:`.
- `get_logger(__name__)` for logging; `print()` only in `cli/*`.
- Backend DTO changes mirrored in `frontend/src/lib/api.ts` in the same task; no hardcoded endpoints/keys in frontend (use `src/lib/constants.ts`); every `.tsx` ≤ 150 lines.
- `cd backend && uv run pytest -q` and `uv run ruff check .` pass before each commit. Frontend: `npm run build` + `npx vitest run`.
- Next Postgres migration number is **0016**.
- **Never** auto-submit, create accounts, handle passwords, or bypass CAPTCHAs.

---

## File Structure

**Backend (create):**
- `backend/migrations/0016_applicant_profile.sql` — Postgres table.
- `backend/job_hunt/services/applicant.py` — set/get applicant profile (dicts).
- `backend/job_hunt/apply/formfill_profiles.py` — load + validate `config/formfill/*.json`.
- `backend/job_hunt/apply/formfill.py` — `FormPage` protocol, `_resolve`, `_fill_page`, `prepare_form_fill`.
- `backend/config/formfill/greenhouse.json`, `backend/config/formfill/lever.json` — declarative field maps.
- `backend/tests/test_applicant_profile.py`, `test_formfill_profiles.py`, `test_formfill_resolve.py`, `test_formfill_engine.py`.

**Backend (modify):**
- `backend/job_hunt/storage/db.py` — `applicant_profile` SCHEMA + repo fns.
- `backend/job_hunt/storage/pg.py` — same, Postgres.
- `backend/job_hunt/storage/repo.py` — re-export the two repo fns.
- `backend/job_hunt/services/__init__.py` — export applicant + fill services.
- `backend/job_hunt/cli/main.py` — `hunt apply-fill`, `hunt applicant`.
- `backend/job_hunt/mcp_server/server.py` — `fill_application` tool.
- `backend/job_hunt/api/app.py` + `api/dto.py` — `POST /api/jobs/{id}/fill`, `GET/POST /api/applicant`.

**Frontend (modify):**
- `frontend/src/lib/constants.ts`, `frontend/src/lib/api.ts` — endpoints, keys, types, calls.
- `frontend/src/pages/ApplicantPanel.tsx` (create) + `frontend/src/pages/Settings.tsx` — applicant profile form.
- `frontend/src/pages/Board/…` — "Auto-fill" action on a job (wire to the fill call).

---

## Task 1: `applicant_profile` storage + migration

**Files:**
- Create: `backend/migrations/0016_applicant_profile.sql`
- Modify: `backend/job_hunt/storage/db.py` (SCHEMA + two fns), `backend/job_hunt/storage/pg.py`, `backend/job_hunt/storage/repo.py`
- Test: `backend/tests/test_applicant_profile.py`

**Interfaces:**
- Produces: `repo.set_applicant_profile(*, fields: dict[str, Any]) -> None`, `repo.get_applicant_profile() -> Row | dict | None` (singleton row id=1). Columns: `first_name,last_name,email,phone,location,linkedin_url,github_url,portfolio_url,work_authorization,needs_sponsorship,willing_to_relocate,notice_period,expected_ctc,current_ctc,years_experience,referral_source,extra` (`extra` = JSON text), `updated_at`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_applicant_profile.py
"""applicant_profile singleton: store the standing answers forms re-ask."""
from __future__ import annotations

from job_hunt.storage import repo


def test_set_and_get_applicant_profile(tmp_db):
    repo.set_applicant_profile(fields={"first_name": "Bhanu", "email": "a@b.in",
                                        "notice_period": "30 days"})
    row = repo.get_applicant_profile()
    assert row["first_name"] == "Bhanu" and row["notice_period"] == "30 days"


def test_get_applicant_profile_none_when_unset(tmp_db):
    assert repo.get_applicant_profile() is None


def test_set_applicant_profile_upserts_single_row(tmp_db):
    repo.set_applicant_profile(fields={"first_name": "A"})
    repo.set_applicant_profile(fields={"first_name": "B", "phone": "+91"})
    row = repo.get_applicant_profile()
    assert row["first_name"] == "B" and row["phone"] == "+91"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_applicant_profile.py -q`
Expected: FAIL (`AttributeError: module 'job_hunt.storage.repo' has no attribute 'set_applicant_profile'`).

- [ ] **Step 3: Add the SCHEMA table in `db.py`**

In `backend/job_hunt/storage/db.py`, add after the `user_context` table in the `SCHEMA` string:

```sql
-- Standing application answers a résumé does not carry (single active row).
CREATE TABLE IF NOT EXISTS applicant_profile (
    id                  INTEGER PRIMARY KEY CHECK (id = 1),
    first_name          TEXT,
    last_name           TEXT,
    email               TEXT,
    phone               TEXT,
    location            TEXT,
    linkedin_url        TEXT,
    github_url          TEXT,
    portfolio_url       TEXT,
    work_authorization  TEXT,
    needs_sponsorship   INTEGER,
    willing_to_relocate INTEGER,
    notice_period       TEXT,
    expected_ctc        TEXT,
    current_ctc         TEXT,
    years_experience    TEXT,
    referral_source     TEXT,
    extra               TEXT,          -- JSON: {question_pattern: answer}
    updated_at          TEXT NOT NULL
);
```

- [ ] **Step 4: Add repo fns in `db.py`**

Add near `set_user_context` in `backend/job_hunt/storage/db.py`:

```python
_APPLICANT_COLS = (
    "first_name", "last_name", "email", "phone", "location", "linkedin_url",
    "github_url", "portfolio_url", "work_authorization", "needs_sponsorship",
    "willing_to_relocate", "notice_period", "expected_ctc", "current_ctc",
    "years_experience", "referral_source", "extra",
)


def set_applicant_profile(*, fields: dict[str, Any]) -> None:
    """Upsert the single applicant-profile row (only known columns are written)."""
    cols = [c for c in _APPLICANT_COLS if c in fields]
    assignments = ", ".join(f"{c} = excluded.{c}" for c in cols)
    placeholders = ", ".join("?" for _ in cols)
    with connect() as conn:
        conn.execute(
            f"INSERT INTO applicant_profile (id, {', '.join(cols)}, updated_at) "
            f"VALUES (1, {placeholders}, ?) "
            f"ON CONFLICT(id) DO UPDATE SET {assignments}, updated_at = excluded.updated_at",
            (*[fields[c] for c in cols], now_iso()),
        )


def get_applicant_profile() -> sqlite3.Row | None:
    """Return the single applicant-profile row, or None if unset."""
    with connect() as conn:
        return conn.execute("SELECT * FROM applicant_profile WHERE id = 1").fetchone()
```

(`_APPLICANT_COLS` is a trusted internal constant — the f-string interpolates only column names from it, never user input, per rule 10.)

- [ ] **Step 5: Add the Postgres migration + `pg.py` fns**

Create `backend/migrations/0016_applicant_profile.sql`:

```sql
-- 0016 — standing application answers a résumé does not carry (single active row).
CREATE TABLE IF NOT EXISTS applicant_profile (
    id                  INTEGER PRIMARY KEY CHECK (id = 1),
    first_name          TEXT,
    last_name           TEXT,
    email               TEXT,
    phone               TEXT,
    location            TEXT,
    linkedin_url        TEXT,
    github_url          TEXT,
    portfolio_url       TEXT,
    work_authorization  TEXT,
    needs_sponsorship   BOOLEAN,
    willing_to_relocate BOOLEAN,
    notice_period       TEXT,
    expected_ctc        TEXT,
    current_ctc         TEXT,
    years_experience    TEXT,
    referral_source     TEXT,
    extra               JSONB,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Add to `backend/job_hunt/storage/pg.py` (near `set_user_context`), reusing the same column tuple:

```python
_APPLICANT_COLS = (
    "first_name", "last_name", "email", "phone", "location", "linkedin_url",
    "github_url", "portfolio_url", "work_authorization", "needs_sponsorship",
    "willing_to_relocate", "notice_period", "expected_ctc", "current_ctc",
    "years_experience", "referral_source", "extra",
)


def set_applicant_profile(*, fields: dict[str, Any]) -> None:
    """Upsert the single applicant-profile row (only known columns are written)."""
    cols = [c for c in _APPLICANT_COLS if c in fields]
    assignments = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols)
    placeholders = ", ".join("%s" for _ in cols)
    with connect() as conn:
        conn.execute(
            f"INSERT INTO applicant_profile (id, {', '.join(cols)}, updated_at) "
            f"VALUES (1, {placeholders}, now()) "
            f"ON CONFLICT (id) DO UPDATE SET {assignments}, updated_at = now()",
            tuple(fields[c] for c in cols),
        )


def get_applicant_profile() -> dict[str, Any] | None:
    """Return the single applicant-profile row, or None if unset."""
    with connect() as conn:
        return conn.execute(
            "SELECT *, extra::text AS extra, updated_at::text AS updated_at "
            "FROM applicant_profile WHERE id = 1"
        ).fetchone()
```

- [ ] **Step 6: Re-export in `repo.py`**

Add to `backend/job_hunt/storage/repo.py` near the `user_context` exports:

```python
set_applicant_profile = _impl.set_applicant_profile
get_applicant_profile = _impl.get_applicant_profile
```

- [ ] **Step 7: Run tests + ruff**

Run: `cd backend && uv run pytest tests/test_applicant_profile.py -q && uv run ruff check .`
Expected: PASS, ruff clean.

- [ ] **Step 8: Commit**

```bash
git add backend/migrations/0016_applicant_profile.sql backend/job_hunt/storage backend/tests/test_applicant_profile.py
git commit -m "feat(backend): applicant_profile singleton store (mig 0016, both backends)"
```

---

## Task 2: `services/applicant.py`

**Files:**
- Create: `backend/job_hunt/services/applicant.py`
- Modify: `backend/job_hunt/services/__init__.py`
- Test: extend `backend/tests/test_applicant_profile.py`

**Interfaces:**
- Consumes: `repo.set_applicant_profile`, `repo.get_applicant_profile`.
- Produces: `set_applicant(fields: dict[str, Any]) -> dict[str, Any]` (returns `{"ok": True, "fields": n}` or `{"error": …}`), `get_applicant() -> dict[str, Any]` (row as dict, or all-null dict if unset).

- [ ] **Step 1: Write the failing test** (append to `tests/test_applicant_profile.py`)

```python
def test_service_set_and_get_applicant(tmp_db):
    from job_hunt import services
    r = services.set_applicant({"first_name": "Bhanu", "email": "a@b.in"})
    assert r["ok"] is True and r["fields"] == 2
    got = services.get_applicant()
    assert got["first_name"] == "Bhanu"


def test_service_set_applicant_rejects_unknown_field(tmp_db):
    from job_hunt import services
    assert "error" in services.set_applicant({"nope": "x"})


def test_service_get_applicant_all_null_when_unset(tmp_db):
    from job_hunt import services
    assert services.get_applicant()["first_name"] is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/test_applicant_profile.py::test_service_set_and_get_applicant -q`
Expected: FAIL (`AttributeError: … 'set_applicant'`).

- [ ] **Step 3: Write `services/applicant.py`**

```python
"""Applicant-profile services — the standing application answers, injected into form fills."""
from __future__ import annotations

from typing import Any

from job_hunt.logging_config import get_logger
from job_hunt.storage import repo
from job_hunt.storage.db import _APPLICANT_COLS

logger = get_logger(__name__)

_ALLOWED = set(_APPLICANT_COLS)


def set_applicant(fields: dict[str, Any]) -> dict[str, Any]:
    """Store/replace applicant-profile fields. Return {ok, fields} or {error}."""
    repo.init_db()
    clean = {k: v for k, v in fields.items() if k in _ALLOWED}
    unknown = set(fields) - _ALLOWED
    if unknown:
        return {"error": f"unknown field(s): {', '.join(sorted(unknown))}"}
    if not clean:
        return {"error": "no fields to set"}
    repo.set_applicant_profile(fields=clean)
    return {"ok": True, "fields": len(clean)}


def get_applicant() -> dict[str, Any]:
    """Return the applicant profile as a dict (all-null dict if unset)."""
    repo.init_db()
    row = repo.get_applicant_profile()
    if row is None:
        return {c: None for c in _APPLICANT_COLS}
    return dict(row)
```

- [ ] **Step 4: Export in `services/__init__.py`**

Add the import next to the `context` import and add both names to `__all__`:

```python
from job_hunt.services.applicant import get_applicant, set_applicant
```
```python
    "set_applicant",
    "get_applicant",
```

- [ ] **Step 5: Run tests + ruff**

Run: `cd backend && uv run pytest tests/test_applicant_profile.py -q && uv run ruff check .`
Expected: PASS, ruff clean.

- [ ] **Step 6: Commit**

```bash
git add backend/job_hunt/services/applicant.py backend/job_hunt/services/__init__.py backend/tests/test_applicant_profile.py
git commit -m "feat(backend): applicant-profile service (set/get, dict returns)"
```

---

## Task 3: Form-profile loader + Greenhouse/Lever configs

**Files:**
- Create: `backend/job_hunt/apply/formfill_profiles.py`, `backend/config/formfill/greenhouse.json`, `backend/config/formfill/lever.json`
- Test: `backend/tests/test_formfill_profiles.py`

**Interfaces:**
- Produces: `load_profile(ats: str) -> dict | None` (parsed JSON for `config/formfill/<ats>.json`, or None if absent), `validate_profile(p: dict) -> str | None` (returns an error string or None). Profile shape: `{"ats": str, "match": {...}, "fields": [{"selector","source","kind"?,"optional"?}], "submit": {"selector","action"}}`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_formfill_profiles.py
"""Form-profile loading + validation for the ATS autofill engine."""
from __future__ import annotations

from job_hunt.apply.formfill_profiles import load_profile, validate_profile


def test_load_greenhouse_profile_is_valid():
    p = load_profile("greenhouse")
    assert p is not None and p["ats"] == "greenhouse"
    assert validate_profile(p) is None


def test_load_lever_profile_is_valid():
    p = load_profile("lever")
    assert p is not None and validate_profile(p) is None


def test_load_unknown_ats_returns_none():
    assert load_profile("workday") is None


def test_validate_rejects_missing_fields_key():
    assert validate_profile({"ats": "x", "match": {}}) is not None
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/test_formfill_profiles.py -q`
Expected: FAIL (`ModuleNotFoundError: … formfill_profiles`).

- [ ] **Step 3: Write `apply/formfill_profiles.py`**

```python
"""Load + validate declarative ATS form profiles from config/formfill/<ats>.json."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_PROFILE_DIR = Path(__file__).resolve().parents[2] / "config" / "formfill"


def load_profile(ats: str) -> dict[str, Any] | None:
    """Return the parsed form profile for an ATS, or None if there is no profile file."""
    path = _PROFILE_DIR / f"{ats}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def validate_profile(p: dict[str, Any]) -> str | None:
    """Return an error message if the profile is malformed, else None."""
    if not isinstance(p.get("ats"), str):
        return "profile missing string 'ats'"
    fields = p.get("fields")
    if not isinstance(fields, list) or not fields:
        return "profile missing non-empty 'fields' list"
    for i, f in enumerate(fields):
        if not isinstance(f.get("selector"), str) or not isinstance(f.get("source"), str):
            return f"field[{i}] needs string 'selector' and 'source'"
    return None
```

- [ ] **Step 4: Write `config/formfill/greenhouse.json`**

```json
{
  "ats": "greenhouse",
  "match": { "url_contains": ["greenhouse.io", "boards.greenhouse.io"] },
  "fields": [
    { "selector": "input#first_name", "source": "applicant.first_name" },
    { "selector": "input#last_name", "source": "applicant.last_name" },
    { "selector": "input#email", "source": "applicant.email" },
    { "selector": "input#phone", "source": "applicant.phone", "optional": true },
    { "selector": "input#job_application_answers_attributes_0_text_value",
      "source": "applicant.work_authorization", "optional": true },
    { "selector": "input[type='file'][name*='resume']",
      "source": "file.resume_variant", "kind": "file" },
    { "selector": "textarea[id*='cover_letter']",
      "source": "draft.cover", "kind": "text", "optional": true }
  ],
  "submit": { "selector": "input[type='submit'], button[type='submit']", "action": "highlight_only" }
}
```

- [ ] **Step 5: Write `config/formfill/lever.json`**

```json
{
  "ats": "lever",
  "match": { "url_contains": ["jobs.lever.co", "lever.co"] },
  "fields": [
    { "selector": "input[name='name']", "source": "applicant.full_name" },
    { "selector": "input[name='email']", "source": "applicant.email" },
    { "selector": "input[name='phone']", "source": "applicant.phone", "optional": true },
    { "selector": "input[name='urls[LinkedIn]']", "source": "applicant.linkedin_url", "optional": true },
    { "selector": "input[name='urls[GitHub]']", "source": "applicant.github_url", "optional": true },
    { "selector": "input[type='file'][name='resume']",
      "source": "file.resume_variant", "kind": "file" }
  ],
  "submit": { "selector": "button[type='submit']", "action": "highlight_only" }
}
```

- [ ] **Step 6: Run tests + ruff**

Run: `cd backend && uv run pytest tests/test_formfill_profiles.py -q && uv run ruff check .`
Expected: PASS, ruff clean.

- [ ] **Step 7: Commit**

```bash
git add backend/job_hunt/apply/formfill_profiles.py backend/config/formfill backend/tests/test_formfill_profiles.py
git commit -m "feat(backend): declarative form-profile loader + greenhouse/lever configs"
```

---

## Task 4: Value resolver

**Files:**
- Create: `backend/job_hunt/apply/formfill.py` (resolver portion only)
- Test: `backend/tests/test_formfill_resolve.py`

**Interfaces:**
- Produces: `_resolve(source: str, data: dict[str, Any]) -> str | None`. `data` shape:
  `{"applicant": dict, "resume": dict, "context": str|None, "draft": {"cover": str|None}, "file": {"resume_variant": str|None}}`.
  Grammar: `applicant.<key>` (with synthetic `full_name`), `resume.<key>`, `context`, `draft.cover`, `file.resume_variant`. Unknown/missing → None.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_formfill_resolve.py
"""Value resolution for form fields: applicant → resume → context → draft → file."""
from __future__ import annotations

from job_hunt.apply.formfill import _resolve

DATA = {
    "applicant": {"first_name": "Bhanu", "last_name": "T", "email": "a@b.in"},
    "resume": {"headline": "Backend Engineer"},
    "context": "Prefers remote roles.",
    "draft": {"cover": "Dear team,"},
    "file": {"resume_variant": "/vault/backend.pdf"},
}


def test_resolve_applicant_field():
    assert _resolve("applicant.first_name", DATA) == "Bhanu"


def test_resolve_synthetic_full_name():
    assert _resolve("applicant.full_name", DATA) == "Bhanu T"


def test_resolve_resume_context_draft_file():
    assert _resolve("resume.headline", DATA) == "Backend Engineer"
    assert _resolve("context", DATA) == "Prefers remote roles."
    assert _resolve("draft.cover", DATA) == "Dear team,"
    assert _resolve("file.resume_variant", DATA) == "/vault/backend.pdf"


def test_resolve_missing_or_unknown_returns_none():
    assert _resolve("applicant.phone", DATA) is None
    assert _resolve("bogus.thing", DATA) is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/test_formfill_resolve.py -q`
Expected: FAIL (`ModuleNotFoundError: … formfill`).

- [ ] **Step 3: Write `apply/formfill.py` (module docstring + `_resolve`)**

```python
"""ATS form auto-fill: resolve stored data onto a declarative profile, fill, stop at review.

The engine never submits: it fills every field it can and hands a highlighted (unsubmitted)
form to the human. Fill logic runs against a `FormPage` protocol so it is testable without a
real browser; the Playwright adapter is the production `FormPage`.
"""
from __future__ import annotations

from typing import Any


def _resolve(source: str, data: dict[str, Any]) -> str | None:
    """Resolve a profile field's `source` string to a value, or None if unavailable."""
    if source == "context":
        return data.get("context") or None
    if source == "draft.cover":
        return (data.get("draft") or {}).get("cover") or None
    if source == "file.resume_variant":
        return (data.get("file") or {}).get("resume_variant") or None
    if "." not in source:
        return None
    ns, key = source.split(".", 1)
    if ns == "applicant":
        applicant = data.get("applicant") or {}
        if key == "full_name":
            parts = [applicant.get("first_name"), applicant.get("last_name")]
            joined = " ".join(p for p in parts if p)
            return joined or None
        return applicant.get(key) or None
    if ns == "resume":
        return (data.get("resume") or {}).get(key) or None
    return None
```

- [ ] **Step 4: Run tests + ruff**

Run: `cd backend && uv run pytest tests/test_formfill_resolve.py -q && uv run ruff check .`
Expected: PASS, ruff clean.

- [ ] **Step 5: Commit**

```bash
git add backend/job_hunt/apply/formfill.py backend/tests/test_formfill_resolve.py
git commit -m "feat(backend): form-fill value resolver (applicant/resume/context/draft/file)"
```

---

## Task 5: `_fill_page` engine + `FormPage` protocol

**Files:**
- Modify: `backend/job_hunt/apply/formfill.py`
- Test: `backend/tests/test_formfill_engine.py`

**Interfaces:**
- Consumes: `_resolve`, `validate_profile`.
- Produces: `class FormPage(Protocol)` with `has(selector) -> bool`, `fill_text(selector, value)`, `select_option(selector, value)`, `set_file(selector, path)`, `set_checkbox(selector, checked)`, `highlight(selector)`; `_fill_page(page: FormPage, profile: dict, data: dict) -> dict` returning `{"filled": list[str], "unfilled": list[str]}`.

- [ ] **Step 1: Write the failing test (fake page, no browser)**

```python
# backend/tests/test_formfill_engine.py
"""_fill_page drives a FormPage: fills what it can, records what it can't, never submits."""
from __future__ import annotations

from job_hunt.apply.formfill import _fill_page


class _FakePage:
    """Records fills; only selectors in `present` 'exist'; submit selector is never clicked."""

    def __init__(self, present: set[str]):
        self.present = present
        self.text: dict[str, str] = {}
        self.files: dict[str, str] = {}
        self.highlighted: list[str] = []
        self.submitted = False

    def has(self, selector: str) -> bool:
        return selector in self.present

    def fill_text(self, selector: str, value: str) -> None:
        self.text[selector] = value

    def select_option(self, selector: str, value: str) -> None:
        self.text[selector] = value

    def set_file(self, selector: str, path: str) -> None:
        self.files[selector] = path

    def set_checkbox(self, selector: str, checked: bool) -> None:
        self.text[selector] = str(checked)

    def highlight(self, selector: str) -> None:
        self.highlighted.append(selector)


PROFILE = {
    "ats": "greenhouse", "match": {}, "fields": [
        {"selector": "#first_name", "source": "applicant.first_name"},
        {"selector": "#email", "source": "applicant.email"},
        {"selector": "#phone", "source": "applicant.phone", "optional": True},
        {"selector": "#resume", "source": "file.resume_variant", "kind": "file"},
        {"selector": "#missing_required", "source": "applicant.years_experience"},
    ],
    "submit": {"selector": "#submit", "action": "highlight_only"},
}
DATA = {"applicant": {"first_name": "Bhanu", "email": "a@b.in"}, "resume": {},
        "context": None, "draft": {"cover": None}, "file": {"resume_variant": "/r.pdf"}}


def test_fill_page_fills_present_fields_and_records_unfilled():
    page = _FakePage(present={"#first_name", "#email", "#resume",
                              "#missing_required", "#submit"})
    result = _fill_page(page, PROFILE, DATA)
    assert page.text["#first_name"] == "Bhanu" and page.text["#email"] == "a@b.in"
    assert page.files["#resume"] == "/r.pdf"
    # required field with no data → unfilled; optional #phone → NOT unfilled
    assert "#missing_required" in result["unfilled"]
    assert "#phone" not in result["unfilled"]
    assert set(result["filled"]) == {"#first_name", "#email", "#resume"}


def test_fill_page_never_submits_and_highlights_submit():
    page = _FakePage(present={"#first_name", "#email", "#resume",
                              "#missing_required", "#submit"})
    _fill_page(page, PROFILE, DATA)
    assert page.submitted is False
    assert page.highlighted == ["#submit"]


def test_fill_page_skips_absent_selectors():
    page = _FakePage(present={"#email"})  # only email exists on the page
    result = _fill_page(page, PROFILE, DATA)
    assert result["filled"] == ["#email"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/test_formfill_engine.py -q`
Expected: FAIL (`ImportError: cannot import name '_fill_page'`).

- [ ] **Step 3: Add `FormPage` + `_fill_page` to `apply/formfill.py`**

Add these imports at the top of `formfill.py` (keeping the module docstring first):

```python
from typing import Any, Protocol

from job_hunt.apply.formfill_profiles import validate_profile
from job_hunt.logging_config import get_logger

logger = get_logger(__name__)
```

Then add:

```python
class FormPage(Protocol):
    """Minimal browser-page surface the filler needs (real impl wraps Playwright)."""

    def has(self, selector: str) -> bool: ...
    def fill_text(self, selector: str, value: str) -> None: ...
    def select_option(self, selector: str, value: str) -> None: ...
    def set_file(self, selector: str, path: str) -> None: ...
    def set_checkbox(self, selector: str, checked: bool) -> None: ...
    def highlight(self, selector: str) -> None: ...


def _fill_page(page: FormPage, profile: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    """Fill every resolvable, present field; collect unfilled required fields; never submit."""
    err = validate_profile(profile)
    if err:
        raise ValueError(f"invalid form profile: {err}")

    filled: list[str] = []
    unfilled: list[str] = []
    for field in profile["fields"]:
        selector = field["selector"]
        value = _resolve(field["source"], data)
        if value is None:
            if not field.get("optional"):
                unfilled.append(selector)
            continue
        if not page.has(selector):
            if not field.get("optional"):
                unfilled.append(selector)
            continue
        kind = field.get("kind", "text")
        if kind == "file":
            page.set_file(selector, value)
        elif kind == "select":
            page.select_option(selector, value)
        elif kind == "checkbox":
            page.set_checkbox(selector, value.lower() in ("true", "yes", "1"))
        else:
            page.fill_text(selector, value)
        filled.append(selector)

    submit = profile.get("submit") or {}
    if submit.get("selector") and page.has(submit["selector"]):
        page.highlight(submit["selector"])  # highlight only — never click
    return {"filled": filled, "unfilled": unfilled}
```

- [ ] **Step 4: Run tests + ruff**

Run: `cd backend && uv run pytest tests/test_formfill_engine.py -q && uv run ruff check .`
Expected: PASS (3 tests), ruff clean.

- [ ] **Step 5: Commit**

```bash
git add backend/job_hunt/apply/formfill.py backend/tests/test_formfill_engine.py
git commit -m "feat(backend): _fill_page engine over FormPage protocol (fills, records unfilled, never submits)"
```

---

## Task 6: `prepare_form_fill` orchestration + Playwright adapter

**Files:**
- Modify: `backend/job_hunt/apply/formfill.py`, `backend/job_hunt/services/__init__.py`
- Test: `backend/tests/test_formfill_engine.py` (add orchestration test with injected page + data)

**Interfaces:**
- Consumes: `repo.get_job`, `repo.get_applicant_profile`, `services.context.context_preamble` (for `context`), the best résumé variant (`repo.best_scored_variant` / `repo.list_resume_variants`), `apply.ats.detect_ats`, `load_profile`, `_fill_page`.
- Produces: `prepare_form_fill(job_id: int, *, page_factory: Callable[[str], FormPage] | None = None) -> dict[str, Any]`. Returns `{"error": …}` (no ATS profile / no job / challenge) or `{"ats", "review_url", "filled", "unfilled"}`. `page_factory` is injectable so tests pass a fake; production default builds the Playwright adapter.

- [ ] **Step 1: Write the failing orchestration test** (append to `test_formfill_engine.py`)

```python
def test_prepare_form_fill_uses_profile_and_returns_summary(tmp_db, monkeypatch):
    from job_hunt.apply import formfill
    from job_hunt.storage import repo

    jid = tmp_db.insert_job_if_new(
        dedup_hash="gh", source="greenhouse", source_job_id=None, title="BE",
        company="Acme", location="remote", description="d",
        apply_url="https://boards.greenhouse.io/acme/jobs/1", posted_date=None,
        emit_discovered=False,
    )
    repo.set_applicant_profile(fields={"first_name": "Bhanu", "email": "a@b.in"})

    captured = {}

    class _FakePage:
        def __init__(self): self.text = {}
        def has(self, s): return True
        def fill_text(self, s, v): self.text[s] = v
        def select_option(self, s, v): self.text[s] = v
        def set_file(self, s, p): self.text[s] = p
        def set_checkbox(self, s, c): self.text[s] = str(c)
        def highlight(self, s): captured["highlighted"] = s

    def factory(url):
        captured["url"] = url
        return _FakePage()

    result = formfill.prepare_form_fill(jid, page_factory=factory)
    assert result["ats"] == "greenhouse"
    assert "a@b.in" in captured["url"] or result["review_url"].startswith("https://boards")
    assert "input#email" in result["filled"] or "input#first_name" in result["filled"]


def test_prepare_form_fill_unknown_ats_errors(tmp_db):
    from job_hunt.apply import formfill
    from job_hunt.storage import repo
    jid = tmp_db.insert_job_if_new(
        dedup_hash="nk", source="naukri", source_job_id=None, title="BE", company="Acme",
        location="blr", description="d", apply_url="https://naukri.com/j/1",
        posted_date=None, emit_discovered=False,
    )
    assert "error" in formfill.prepare_form_fill(jid)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/test_formfill_engine.py::test_prepare_form_fill_unknown_ats_errors -q`
Expected: FAIL (`AttributeError: … 'prepare_form_fill'`).

- [ ] **Step 3: Add orchestration + Playwright adapter to `formfill.py`**

Add imports:

```python
import json
from collections.abc import Callable

from job_hunt.apply.ats import detect_ats
from job_hunt.apply.formfill_profiles import load_profile
from job_hunt.storage import repo
```

Add the assembler + entrypoint:

```python
def _gather_data(job: Any) -> dict[str, Any]:
    """Assemble the data bundle a form profile resolves against for one job."""
    from job_hunt.services.context import context_preamble  # local: avoid import cycle

    applicant_row = repo.get_applicant_profile()
    applicant = dict(applicant_row) if applicant_row else {}

    variants = repo.list_resume_variants()
    resume: dict[str, Any] = {}
    resume_path: str | None = None
    if variants:
        best = variants[0]
        resume = json.loads(best["parsed_json"]) if best["parsed_json"] else {}
        resume_path = best["source_path"]

    cover = None
    drafts = repo.list_drafts_for_job(int(job["id"])) if hasattr(repo, "list_drafts_for_job") else []
    for d in drafts:
        if d["kind"] == "cover":
            cover = d["body"]
            break

    return {
        "applicant": applicant,
        "resume": resume,
        "context": context_preamble() or None,
        "draft": {"cover": cover},
        "file": {"resume_variant": resume_path},
    }


def prepare_form_fill(
    job_id: int, *, page_factory: Callable[[str], FormPage] | None = None
) -> dict[str, Any]:
    """Open a job's ATS form, fill what we can, stop at review. Returns a summary or {error}."""
    repo.init_db()
    job = repo.get_job(job_id)
    if job is None:
        return {"error": f"no job with id={job_id}"}

    ats = str(detect_ats(job["apply_url"]))
    profile = load_profile(ats)
    if profile is None:
        return {"error": f"no form profile for '{ats}' yet"}

    data = _gather_data(job)
    factory = page_factory or _playwright_page_factory
    page = factory(job["apply_url"])
    summary = _fill_page(page, profile, data)
    return {"ats": ats, "review_url": job["apply_url"], **summary}


def _playwright_page_factory(url: str) -> FormPage:
    """Open `url` in the managed (headful) browser and return a Playwright-backed FormPage."""
    from job_hunt.browser.manager import managed_context

    ctx = managed_context("formfill", headless=False)
    page = ctx.new_page()
    page.goto(url, wait_until="domcontentloaded")
    return _PlaywrightPage(page)


class _PlaywrightPage:
    """FormPage backed by a live Playwright page. Fills fields; never clicks submit."""

    def __init__(self, page: Any):
        self._page = page

    def has(self, selector: str) -> bool:
        return self._page.query_selector(selector) is not None

    def fill_text(self, selector: str, value: str) -> None:
        self._page.fill(selector, value)

    def select_option(self, selector: str, value: str) -> None:
        self._page.select_option(selector, label=value)

    def set_file(self, selector: str, path: str) -> None:
        self._page.set_input_files(selector, path)

    def set_checkbox(self, selector: str, checked: bool) -> None:
        self._page.set_checked(selector, checked)

    def highlight(self, selector: str) -> None:
        self._page.eval_on_selector(
            selector, "el => el.style.outline = '3px solid #16A34A'"
        )
```

> Note for the implementer: confirm `managed_context`'s real signature in `browser/manager.py`
> and adapt the `headless=False` call to match (it may take a source key + options object).
> `list_drafts_for_job` may be named differently — grep `storage/repo.py` for the draft-listing
> fn and use the real name; the `hasattr` guard keeps the test green either way.

- [ ] **Step 4: Run tests + ruff**

Run: `cd backend && uv run pytest tests/test_formfill_engine.py -q && uv run ruff check .`
Expected: PASS, ruff clean.

- [ ] **Step 5: Export the service + commit**

Add to `services/__init__.py`:
```python
from job_hunt.apply.formfill import prepare_form_fill
```
```python
    "prepare_form_fill",
```

```bash
git add backend/job_hunt/apply/formfill.py backend/job_hunt/services/__init__.py backend/tests/test_formfill_engine.py
git commit -m "feat(backend): prepare_form_fill orchestration + Playwright FormPage adapter"
```

---

## Task 7: CLI — `hunt apply-fill` + `hunt applicant`

**Files:**
- Modify: `backend/job_hunt/cli/main.py`
- Test: manual (browser); the service logic is already covered by Task 6.

**Interfaces:**
- Consumes: `services.prepare_form_fill`, `services.set_applicant`, `services.get_applicant`.

- [ ] **Step 1: Add `cmd_apply_fill` + `cmd_applicant`** (near `cmd_context` in `cli/main.py`)

```python
def cmd_apply_fill(args: argparse.Namespace) -> int:
    """Open a job's ATS form, auto-fill it, and stop at the review screen."""
    result = services.prepare_form_fill(args.job_id)
    if "error" in result:
        print(f"!! {result['error']}")
        return 1
    print(f"[{result['ats']}] filled {len(result['filled'])} field(s); "
          f"{len(result['unfilled'])} need you: {result['unfilled']}")
    print(f"review & submit: {result['review_url']}")
    return 0


def cmd_applicant(args: argparse.Namespace) -> int:
    """Set an applicant-profile field (--set key=value ...) or show the current profile."""
    if args.set:
        fields = dict(pair.split("=", 1) for pair in args.set)
        result = services.set_applicant(fields)
        print(result.get("error") or f"set {result['fields']} field(s)")
        return 1 if "error" in result else 0
    for k, v in services.get_applicant().items():
        if v is not None:
            print(f"{k}: {v}")
    return 0
```

- [ ] **Step 2: Wire the parsers** (near the `context` parser)

```python
    af = sub.add_parser("apply-fill", help="Auto-fill a job's ATS form (stops at review)")
    af.add_argument("job_id", type=int)
    af.set_defaults(func=cmd_apply_fill)

    ap = sub.add_parser("applicant", help="Set/show standing application answers")
    ap.add_argument("--set", nargs="*", metavar="key=value", help="fields to set")
    ap.set_defaults(func=cmd_applicant)
```

- [ ] **Step 3: Verify + commit**

Run: `cd backend && uv run hunt applicant --set first_name=Bhanu email=a@b.in && uv run hunt applicant && uv run ruff check .`
Expected: prints the two fields; ruff clean.

```bash
git add backend/job_hunt/cli/main.py
git commit -m "feat(cli): hunt apply-fill + hunt applicant"
```

---

## Task 8: MCP tool — `fill_application`

**Files:**
- Modify: `backend/job_hunt/mcp_server/server.py`
- Test: manual via MCP host; logic covered by Task 6.

**Interfaces:**
- Consumes: `services.prepare_form_fill`.

- [ ] **Step 1: Add the tool** (mirror an existing `@mcp.tool()` in `server.py`)

```python
@mcp.tool()
def fill_application(job_id: int) -> dict:
    """Open a job's ATS form and auto-fill it from stored data, stopping before submit."""
    return services.prepare_form_fill(job_id)
```

- [ ] **Step 2: Verify import + commit**

Run: `cd backend && uv run python -c "import job_hunt.mcp_server.server" && uv run ruff check .`
Expected: no error; ruff clean.

```bash
git add backend/job_hunt/mcp_server/server.py
git commit -m "feat(mcp): fill_application tool"
```

---

## Task 9: API + DTO + frontend (applicant panel + Auto-fill action)

**Files:**
- Modify: `backend/job_hunt/api/app.py`, `backend/job_hunt/api/dto.py`, `backend/tests/test_e2e_api.py`
- Modify: `frontend/src/lib/constants.ts`, `frontend/src/lib/api.ts`
- Create: `frontend/src/pages/ApplicantPanel.tsx`; Modify: `frontend/src/pages/Settings.tsx`

**Interfaces:**
- Produces: `POST /api/jobs/{id}/fill` → fill summary; `GET /api/applicant` (`dto.Applicant`), `POST /api/applicant`.

- [ ] **Step 1: Write the failing API test** (append to `tests/test_e2e_api.py`)

```python
def test_applicant_and_fill_endpoints(client, tmp_db, monkeypatch):
    got = client.get("/api/applicant", headers=AUTH)
    assert got.status_code == 200 and got.json()["first_name"] is None

    posted = client.post("/api/applicant", headers=AUTH,
                         json={"first_name": "Bhanu", "email": "a@b.in"})
    assert posted.status_code == 200 and posted.json()["ok"] is True

    from job_hunt.apply import formfill
    monkeypatch.setattr(formfill, "prepare_form_fill",
                        lambda job_id: {"ats": "greenhouse", "review_url": "u",
                                        "filled": ["#email"], "unfilled": []})
    jid = _scored_job(tmp_db)
    fill = client.post(f"/api/jobs/{jid}/fill", headers=AUTH)
    assert fill.status_code == 200 and fill.json()["ats"] == "greenhouse"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/test_e2e_api.py::test_applicant_and_fill_endpoints -q`
Expected: FAIL (404 on `/api/applicant`).

- [ ] **Step 3: Add DTO + request model + endpoints**

`api/dto.py` — add:
```python
class Applicant(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    portfolio_url: str | None = None
    work_authorization: str | None = None
    needs_sponsorship: bool | None = None
    willing_to_relocate: bool | None = None
    notice_period: str | None = None
    expected_ctc: str | None = None
    current_ctc: str | None = None
    years_experience: str | None = None
    referral_source: str | None = None
    extra: str | None = None
    updated_at: str | None = None
```

`api/app.py` — add a request model near `ContextIn`:
```python
class ApplicantIn(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    portfolio_url: str | None = None
    work_authorization: str | None = None
    needs_sponsorship: bool | None = None
    willing_to_relocate: bool | None = None
    notice_period: str | None = None
    expected_ctc: str | None = None
    current_ctc: str | None = None
    years_experience: str | None = None
    referral_source: str | None = None
```
and the routes (near the `context` routes):
```python
@api.get("/applicant", response_model=dto.Applicant)
def get_applicant() -> dict[str, Any]:
    return services.get_applicant()


@api.post("/applicant")
def set_applicant(body: ApplicantIn) -> dict[str, Any]:
    return _unwrap(services.set_applicant(body.model_dump(exclude_none=True)))


@api.post("/jobs/{job_id}/fill")
def fill_job(job_id: int) -> dict[str, Any]:
    return _unwrap(services.prepare_form_fill(job_id))
```

- [ ] **Step 4: Run backend test + ruff**

Run: `cd backend && uv run pytest tests/test_e2e_api.py -q && uv run ruff check .`
Expected: PASS, ruff clean.

- [ ] **Step 5: Mirror to frontend constants + api**

`frontend/src/lib/constants.ts` — add to `API_ENDPOINTS`:
```typescript
  applicant: "/api/applicant",
  jobFill: (id: number) => `/api/jobs/${id}/fill`,
```
and to `QUERY_KEYS`:
```typescript
  applicant: ["applicant"] as const,
```

`frontend/src/lib/api.ts` — add the interface (mirror `dto.Applicant`) and calls:
```typescript
export interface Applicant {
  first_name: string | null; last_name: string | null; email: string | null;
  phone: string | null; location: string | null; linkedin_url: string | null;
  github_url: string | null; portfolio_url: string | null; work_authorization: string | null;
  needs_sponsorship: boolean | null; willing_to_relocate: boolean | null;
  notice_period: string | null; expected_ctc: string | null; current_ctc: string | null;
  years_experience: string | null; referral_source: string | null;
  extra: string | null; updated_at: string | null;
}
```
```typescript
  getApplicant: () => req<Applicant>(API_ENDPOINTS.applicant),
  setApplicant: (b: Partial<Applicant>) =>
    req<{ ok?: boolean }>(API_ENDPOINTS.applicant, { method: "POST", body: JSON.stringify(b) }),
  fillJob: (id: number) =>
    req<{ ats: string; review_url: string; filled: string[]; unfilled: string[] }>(
      API_ENDPOINTS.jobFill(id), { method: "POST" }),
```

- [ ] **Step 6: Applicant panel in Settings** (mirror `ContextPanel.tsx`, ≤150 lines)

Create `frontend/src/pages/ApplicantPanel.tsx` — a card of labelled `<input>`s for the string
fields (first_name, last_name, email, phone, location, linkedin_url, notice_period,
expected_ctc, work_authorization, referral_source) bound to `useState`, saved via
`api.setApplicant`, invalidating `QUERY_KEYS.applicant`; pre-filled from `api.getApplicant`.
Follow `ContextPanel.tsx` structure exactly (query + mutation + dirty flag + ErrorView).
Render `<ApplicantPanel />` in `Settings.tsx` after `<ContextPanel />`.

- [ ] **Step 7: "Auto-fill" action on a job**

In the job detail/actions component (grep `pages/` for the tailor/cover buttons — same place),
add a button:
```tsx
<button onClick={() => fill.mutate()} disabled={fill.isPending}>Auto-fill form</button>
```
backed by `useMutation({ mutationFn: () => api.fillJob(id) })`, and render the result
(`Filled {n}, {m} need you`) with the `review_url` as a link the user opens to submit.

- [ ] **Step 8: Build, test, commit**

Run: `cd frontend && npm run build && npx vitest run`
Expected: build passes, vitest green.

```bash
git add backend/job_hunt/api frontend/src backend/tests/test_e2e_api.py
git commit -m "feat: applicant profile + auto-fill API/DTO/UI (mirror), Auto-fill job action"
```

---

## Self-Review

**Spec coverage:** §4.1 engine → Tasks 4–6; §4.2 profiles → Task 3; §4.3 resolution order → Task 4; §5 applicant_profile → Tasks 1–2; §6 entry points → Tasks 7–9; §8 error handling (unknown ATS, unfilled, never-submit) → Tasks 5–6 tests; §9 testing → Tasks 1–6, 9. **§8 CAPTCHA-stop** is NOT yet implemented — the Playwright adapter should detect a challenge and raise/return an error; **added as Task 6 implementer note** (grep for existing `classify_scrape`/blocked-detection in `browser/` and reuse it before the fill loop). v2 queue + v3 Workday are out of scope by design.

**Placeholder scan:** Tasks 7–9 UI steps describe structure rather than full code for the panel/button (they explicitly say "mirror `ContextPanel.tsx`") — acceptable because the mirrored file is concrete and in-repo, but the implementer must keep each `.tsx` ≤150 lines.

**Type consistency:** `prepare_form_fill(job_id, *, page_factory)` and its `{ats, review_url, filled, unfilled}` return are used identically in Tasks 6–9 and the frontend `fillJob` type. `_APPLICANT_COLS` is defined once in `db.py` and imported by `services/applicant.py` (single source of truth). `FormPage` methods match between the protocol, `_FakePage`, and `_PlaywrightPage`.

**Known implementer checkpoints (verify against real code, don't assume):** `managed_context` signature; the draft-listing repo fn name; the résumé-variant "best" selection (`list_resume_variants` ordering vs a dedicated `best_scored_variant`); the exact selectors in the two ATS JSONs (they are best-effort starting points — refine against a real saved form).
