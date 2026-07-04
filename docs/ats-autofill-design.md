# ATS Auto-Fill — design spec

**Status:** proposed · **Date:** 2026-07-04 · **Owner:** you

## 1. Goal

Cut the repetitive grunt work out of applying: when you decide to apply to a job whose
apply link lands on a known ATS form, the tool **opens the form in a browser, fills every
field it can from your stored data, and stops at the review/submit screen** so you eyeball
it and click Submit yourself.

The engine is **ATS-agnostic**; each ATS is a **declarative config profile**, mirroring the
existing `config/selectors/<source>.json` scraper pattern. Adding a new ATS is a new JSON
file, not engine surgery.

## 2. Non-goals (explicit)

- **No auto-submit.** The human always clicks Submit. The tool never submits a form.
- **No account creation, no password handling.** Where an ATS (e.g. Workday) forces a
  per-employer account, *you* log in; the tool only fills the application fields after.
- **No CAPTCHA / bot-detection bypass.** If a challenge appears, the tool stops and tells you.
- **No Workday in v1.** Your pipeline currently has 0 Workday jobs; it's the hardest ATS.
  It becomes a config profile later, once a source produces Workday-hosted jobs.
- **No N8N / external workflow server.** The automation is the existing event-driven worker
  chain, in-process and version-controlled.

## 3. Why this shape (agility + cleanliness)

- **One codebase, one source of truth** — reuses `browser/` (managed Playwright session,
  fingerprint, rate-limiter), `apply/ats.py` (ATS detection), `apply/reviewer.py` (pre-submit
  AI check), résumé variants, and the User Context. No logic split across a second system.
- **New site = config, not code** — the proven `config/selectors/` pattern, applied to forms.
- **Fits the thin-adapter architecture** — engine in `apply/`, exposed by CLI + MCP + API/UI,
  each a thin wrapper (per `backend/CLAUDE.md`).

## 4. Architecture

```
                        ┌─────────────────────────────────────┐
  hunt apply-fill  ───► │                                     │
  MCP fill_application ►│  apply/formfill.py  (generic engine) │
  UI "Auto-fill" btn ──►│                                     │
                        └───────────────┬─────────────────────┘
                                        │ reads
                    ┌───────────────────┼────────────────────────┐
                    ▼                   ▼                         ▼
     config/formfill/<ats>.json   applicant_profile        résumé variant +
     (declarative field-map)      (standing answers)        User Context + cover draft
                    │                   │                         │
                    └──────── resolve each field's value ─────────┘
                                        │
                                        ▼
              managed Playwright browser (existing session/fingerprint)
                                        │
                                        ▼
                    fill fields → STOP at submit → hand to human
```

### 4.1 The generic engine — `apply/formfill.py`

`prepare_form_fill(job_id) -> dict` (a **service-style** function returning a dict / `{"error": …}`):

1. Load the job; `detect_ats(apply_url)` → pick `config/formfill/<ats>.json`. If no profile
   exists for that ATS, return `{"error": "no form profile for <ats> yet"}` (never guess).
2. Open the apply URL in a `managed_context` (reuses the saved login session + fingerprint +
   rate-limiter). **Headful** (visible) so you can watch and take over.
3. For each field in the profile, **resolve its value** (§4.3) and fill it. File-upload fields
   attach the best-matching résumé variant. Fields with no resolvable value are left blank and
   **collected into an `unfilled` list**.
4. **Stop at the review point.** Highlight the Submit button, do **not** click it. Return a
   summary: `{filled: [...], unfilled: [...], review_url, ats}`.

### 4.2 Declarative form-profile — `config/formfill/<ats>.json`

```json
{
  "ats": "greenhouse",
  "match": { "url_contains": ["greenhouse.io", "boards.greenhouse.io"] },
  "fields": [
    { "selector": "input#first_name", "source": "applicant.first_name" },
    { "selector": "input#last_name",  "source": "applicant.last_name" },
    { "selector": "input#email",      "source": "applicant.email" },
    { "selector": "input#phone",      "source": "applicant.phone" },
    { "selector": "input[autocomplete='off'][name*='resume']",
      "source": "file.resume_variant", "kind": "file" },
    { "selector": "textarea[id*='cover_letter']", "source": "draft.cover", "optional": true },
    { "selector": "select[id*='work_authorization']",
      "source": "applicant.work_authorization", "kind": "select" }
  ],
  "submit": { "selector": "button[type='submit']", "action": "highlight_only" }
}
```

- `source` grammar: `applicant.<key>` · `resume.<key>` · `context` · `draft.cover` ·
  `file.resume_variant`. Unknown source → treated as unfilled (logged), never crashes.
- `kind` (default `text`): `text` | `select` | `file` | `checkbox`.
- `optional` fields never appear in `unfilled`.

### 4.3 Value resolution order

For a given `source`, resolve deterministically:

1. `applicant.<key>` → the `applicant_profile` store (§5).
2. `resume.<key>` → the best-matching résumé variant's parsed JSON.
3. `context` → the User Context blob (last resort free-text).
4. `draft.cover` → the saved cover-letter draft for this job (generate on demand if missing).
5. `file.resume_variant` → the résumé file path for the best variant.

No value found → field is skipped and added to `unfilled` (surfaced to you, never invented).

## 5. Data model — `applicant_profile` (migration 0016)

The standing answers every form re-asks that a résumé does **not** contain. Single-row
singleton (like `user_context`), both backends.

| column | example | notes |
|---|---|---|
| `first_name`, `last_name` | | |
| `email`, `phone` | | |
| `location`, `linkedin_url`, `github_url`, `portfolio_url` | | |
| `work_authorization` | "Indian citizen, needs visa for US" | free text |
| `needs_sponsorship` | bool | |
| `willing_to_relocate` | bool | |
| `notice_period` | "30 days" | |
| `expected_ctc`, `current_ctc` | | |
| `years_experience` | | |
| `referral_source` | "company website" | the "how did you hear about us" answer |
| `extra` | JSON | overflow map of `question_pattern → answer` for anything else |

**Sensitive EEO/demographic fields (gender, race, veteran, disability)** are **not** stored by
default. If ever added, they default to **"decline to answer"** and are opt-in only.

Service: `services/applicant.py` — `set_applicant_profile(**fields)`, `get_applicant_profile()`
(dict returns; `{"error": …}` on bad input). Repo fns mirror `user_context`.

## 6. Entry points (thin adapters)

- **CLI:** `hunt apply-fill <job_id>` → prints the fill summary + the `unfilled` list + the
  review URL.
- **MCP:** tool `fill_application(job_id)` → same summary, so you can drive it from chat.
- **API/UI:** `POST /api/jobs/{id}/fill` → an **"Auto-fill"** button on the job card. The UI
  shows *"Filled 9 fields · 2 need you: [Expected CTC], [How did you hear] · Open form to
  review & submit."*

## 7. The "N8N feel" — worker chain (v2)

Extend the existing `worker/handlers.py` chain. When a job reaches high fit **and** its ATS has
a profile, auto-prepare it to the review point (tailor + fill draft) and drop it into a
**"Ready to review & submit"** queue (a job state / board column). You open the queue, glance,
submit. No new infrastructure — it's the outbox/worker you already have.

## 8. Error handling & safety

- **Unknown ATS / no profile** → `{"error": …}`, nothing opened.
- **Selector miss (form changed)** → that field goes to `unfilled` with a note "profile
  `<ats>.json` may need updating"; the run does not crash.
- **CAPTCHA / bot-challenge detected** → stop immediately, return `{"error": "challenge
  present — please continue manually"}`. Never attempt to solve or bypass.
- **Missing required data** → left blank + surfaced in `unfilled`; never fabricated.
- **Always headful, never auto-submit** — the human is the last step by construction.

## 9. Testing (`backend/tests/`)

- `test_formfill_resolver.py` — the value-resolution order (§4.3) against fake profile + fake
  applicant/résumé/context data; unknown-source handling; `unfilled` collection.
- `test_formfill_profile.py` — profile load + validation (bad JSON, missing `match`, etc.).
- `test_applicant_profile.py` — set/get on both backends (contract style), like `user_context`.
- `test_formfill_engine.py` — drive a **saved static HTML fixture** of a Greenhouse form (no
  live site): assert fields receive the right values, file field gets the résumé path, and the
  engine **stops before submit** (submit never clicked).
- API round-trip: `POST /api/jobs/{id}/fill` on a stubbed engine returns the summary shape.
- No test ever hits a live ATS.

## 10. Phasing

- **v1** — `applicant_profile` (store + service + CLI + UI panel), the generic engine, and
  **Greenhouse + Lever** profiles. Fill-to-review via CLI + MCP + UI button. Static-fixture tests.
- **v2** — the worker chain + "Ready to review & submit" queue (the hands-off feel).
- **v3** — add `workday.json` / `naukri.json` profiles once those jobs exist in the pipeline;
  no engine changes expected (proves the config-driven design).

## 11. Risks & open questions

- **Form drift** — ATS forms change; profiles need occasional selector updates. Mitigation:
  graceful `unfilled` reporting names the profile to fix. Acceptable for a personal tool.
- **Greenhouse/Lever field variability** — custom questions differ per company. The `extra`
  map + `optional` fields + `unfilled` surfacing handle the long tail without breaking.
- **Getting ATS jobs into the pipeline** — v1 value depends on running
  `hunt discover greenhouse --keyword <company>` for boards you care about. Worth confirming
  you'll seed a few company slugs.
- **Open:** do you want the cover letter auto-attached by default, or only when you've already
  generated/approved one for that job?
