# Email Actions v2 — CLI + API + Frontend DTO Mirror

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `propose_action / confirm_action / dismiss_action` to CLI, FastAPI routes, and TS lib; fix cosmetic help-text bugs in CLI and MCP.

**Architecture:** All three new service functions are already implemented in `job_hunt.services.email_triage` and re-exported from `job_hunt.services`. This task is purely additive surface work: CLI subcommands, FastAPI routes + DTO, TS constants + api methods, and tests. No new storage or business logic.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, argparse, TypeScript 5, Vitest, uv, npm/Vite.

## Global Constraints

- `print()` only in `cli/main.py`; everywhere else use `get_logger(__name__)`.
- All new backend functions: `from __future__ import annotations`, fully type-hinted, one-line imperative docstring.
- `uv run ruff check .` must stay green (line ≤ 100 soft, 112 hard).
- No `any` / leaked `unknown` in TypeScript; all constants in `constants.ts`.
- Do NOT hit real IMAP or LLM in tests — monkeypatch service layer.
- Do NOT add any action tool to `mcp_server/server.py` — it stays read-only.
- Report: `/Users/BackendIntern/Documents/job-hunt/.superpowers/sdd/email-v2t3-report.md`.

---

### Task 1: Backend DTO — `EmailActionProposal`

**Files:**
- Modify: `backend/job_hunt/api/dto.py`

**Interfaces:**
- Produces: `dto.EmailActionProposal` — `action_id: int, kind: str, payload: dict[str, Any] | None, state: str`

- [ ] **Step 1: Add `from typing import Any` import and `EmailActionProposal` class**

  Append to `backend/job_hunt/api/dto.py` (after the `Applicant` class):

  ```python
  from typing import Any

  class EmailActionProposal(BaseModel):
      """Proposed email action awaiting human confirmation."""

      action_id: int
      kind: str
      payload: dict[str, Any] | None = None
      state: str
  ```

  (`from typing import Any` goes in the imports block at top, after `from pydantic import BaseModel`.)

- [ ] **Step 2: Run ruff**

  ```bash
  cd /Users/BackendIntern/Documents/job-hunt/backend && uv run ruff check job_hunt/api/dto.py
  ```
  Expected: no output (clean).

---

### Task 2: API routes + `EmailActionIn` request model

**Files:**
- Modify: `backend/job_hunt/api/app.py`

**Interfaces:**
- Consumes: `dto.EmailActionProposal` (Task 1), `services.propose_action`, `services.confirm_action`, `services.dismiss_action`
- Produces: three new POST routes under `/api/emails/`

- [ ] **Step 1: Add `ProposeIn` and `EmailActionIn` request models** (after the last existing request model `ApplicantIn`):

  ```python
  class ProposeIn(BaseModel):
      kind: str
      label: str | None = None


  class EmailActionIn(BaseModel):
      kind: str
      action_id: int | None = None
      confirm: bool = False
      label: str | None = None
  ```

- [ ] **Step 2: Add three routes** (after the `email_detail` route, before `sync_emails`):

  ```python
  @api.post("/emails/{email_id}/propose", response_model=dto.EmailActionProposal)
  def propose_email_action(email_id: int, body: ProposeIn) -> dict[str, Any]:
      """Propose an email action for human review and return the stored proposal."""
      return _unwrap(services.propose_action(email_id, body.kind, label=body.label))


  @api.post("/emails/{email_id}/action")
  def execute_email_action(email_id: int, body: EmailActionIn) -> dict[str, Any]:
      """Execute or gate a proposed email action; requires confirm=True to open IMAP."""
      return _unwrap(
          services.confirm_action(email_id, action_id=body.action_id, confirm=body.confirm)
      )


  @api.post("/emails/{email_id}/dismiss")
  def dismiss_email_action(email_id: int) -> dict[str, Any]:
      """Dismiss the pending proposed action on an email."""
      return _unwrap(services.dismiss_action(email_id))
  ```

- [ ] **Step 3: Run ruff**

  ```bash
  cd /Users/BackendIntern/Documents/job-hunt/backend && uv run ruff check job_hunt/api/app.py
  ```
  Expected: clean.

---

### Task 3: CLI — `email action` + `email dismiss` + fix help text

**Files:**
- Modify: `backend/job_hunt/cli/main.py`

**Interfaces:**
- Consumes: `services.propose_action`, `services.confirm_action`, `services.dismiss_action`

- [ ] **Step 1: Add `cmd_email_action` function** (after `cmd_email_show`, before `build_parser`):

  ```python
  def cmd_email_action(args: argparse.Namespace) -> int:
      """Propose or confirm an email action (IMAP write requires --confirm)."""
      if args.confirm:
          result = services.confirm_action(args.email_id, confirm=True)
      else:
          result = services.propose_action(args.email_id, args.kind, label=args.label)
      if "error" in result:
          print(f"!! {result['error']}")
          return 1
      print(json.dumps(result, indent=2, default=str))
      return 0


  def cmd_email_dismiss(args: argparse.Namespace) -> int:
      """Dismiss the pending proposed action on an email."""
      result = services.dismiss_action(args.email_id)
      if "error" in result:
          print(f"!! {result['error']}")
          return 1
      print(json.dumps(result, indent=2, default=str))
      return 0
  ```

- [ ] **Step 2: Add parsers in `build_parser()`** (after the `esh` / `show` sub-parser, before `return p`):

  ```python
  ea = em_sub.add_parser("action", help="Propose or confirm an email action")
  ea.add_argument("email_id", type=int, help="email ID")
  ea.add_argument(
      "--kind",
      choices=["draft_reply", "apply_label", "archive"],
      required=True,
      help="action kind: draft_reply, apply_label, or archive",
  )
  ea.add_argument("--label", help="label name (required for apply_label kind)")
  ea.add_argument(
      "--confirm",
      action="store_true",
      help="confirm and execute the proposed action (opens IMAP for write)",
  )
  ea.set_defaults(func=cmd_email_action)

  edm = em_sub.add_parser("dismiss", help="Dismiss the pending action on an email")
  edm.add_argument("email_id", type=int, help="email ID")
  edm.set_defaults(func=cmd_email_dismiss)
  ```

- [ ] **Step 3: Fix the `email list --category` help text**

  Change:
  ```python
  el.add_argument("--category", help="filter by category (e.g., offer, rejection, other)")
  ```
  To:
  ```python
  el.add_argument(
      "--category",
      help="filter by category (e.g., recruiter_outreach, rejection, other)",
  )
  ```

- [ ] **Step 4: Run ruff**

  ```bash
  cd /Users/BackendIntern/Documents/job-hunt/backend && uv run ruff check job_hunt/cli/main.py
  ```
  Expected: clean.

---

### Task 4: MCP docstring cosmetic fix

**Files:**
- Modify: `backend/job_hunt/mcp_server/server.py`

- [ ] **Step 1: Fix `email_list` docstring**

  Change the `category` arg description from:
  ```
  category: filter by category (e.g., "offer", "rejection", "other") — empty = no filter
  ```
  To:
  ```
  category: filter by category (e.g., "recruiter_outreach", "rejection", "other") — empty = no filter
  ```

- [ ] **Step 2: Run ruff**

  ```bash
  cd /Users/BackendIntern/Documents/job-hunt/backend && uv run ruff check job_hunt/mcp_server/server.py
  ```
  Expected: clean.

---

### Task 5: Frontend — constants + api client

**Files:**
- Modify: `frontend/src/lib/constants.ts`
- Modify: `frontend/src/lib/api.ts`

**Interfaces:**
- Produces: `EmailActionProposal` TS interface, `api.proposeAction`, `api.confirmAction`, `api.dismissAction`

- [ ] **Step 1: Add endpoints to `constants.ts`** (inside `API_ENDPOINTS`, after `emailsSync`):

  ```typescript
  emailPropose: (id: number) => `/api/emails/${id}/propose`,
  emailAction: (id: number) => `/api/emails/${id}/action`,
  emailDismiss: (id: number) => `/api/emails/${id}/dismiss`,
  ```

- [ ] **Step 2: Add `EmailActionProposal` interface to `api.ts`** (after `EmailDetail`):

  ```typescript
  // Mirrors backend dto.EmailActionProposal.
  export interface EmailActionProposal {
    action_id: number;
    kind: string;
    payload: Record<string, string | null | undefined> | null;
    state: string;
  }
  ```

- [ ] **Step 3: Add three api methods to `api.ts`** (inside the `api` object, after `syncEmails`):

  ```typescript
  proposeAction: (id: number, kind: string, label?: string | null) =>
    req<EmailActionProposal>(API_ENDPOINTS.emailPropose(id), {
      method: "POST",
      body: JSON.stringify({ kind, label: label ?? null }),
    }),
  confirmAction: (
    id: number,
    body: { kind: string; action_id?: number; confirm: boolean; label?: string | null },
  ) =>
    req<{ action_id: number; kind: string; state: string; executed_at: string }>(
      API_ENDPOINTS.emailAction(id),
      { method: "POST", body: JSON.stringify(body) },
    ),
  dismissAction: (id: number) =>
    req<{ action_id: number; state: string }>(
      API_ENDPOINTS.emailDismiss(id),
      { method: "POST" },
    ),
  ```

- [ ] **Step 4: Build check**

  ```bash
  cd /Users/BackendIntern/Documents/job-hunt/frontend && npm run build
  ```
  Expected: exit 0 with no TypeScript errors.

---

### Task 6: E2E tests

**Files:**
- Modify: `backend/tests/test_e2e_api.py`

**Interfaces:**
- Consumes: `client`, `AUTH`, `tmp_db` fixtures (existing); `app_module.services` (existing monkeypatch target)

- [ ] **Step 1: Add three test functions** (after `test_email_inbox_read_and_sync`):

  ```python
  def test_email_action_propose(client, tmp_db, monkeypatch):
      """POST /api/emails/{id}/propose returns EmailActionProposal without calling LLM."""
      eid = repo.upsert_email_message(
          mailbox="INBOX", uid=20, message_id="<m20@acme>", thread_id=None,
          from_addr="recruiter@lever.co", from_name="Acme HR",
          subject="Next steps", received_at="2026-07-01T10:00:00+00:00",
          snippet="Let us schedule", body_text="Let us schedule a call.",
      )
      monkeypatch.setattr(
          app_module.services,
          "propose_action",
          lambda email_id, kind, *, label=None: {
              "action_id": 1,
              "kind": kind,
              "payload": {},
              "state": "proposed",
          },
      )
      resp = client.post(
          f"/api/emails/{eid}/propose", headers=AUTH, json={"kind": "archive"}
      )
      assert resp.status_code == 200
      body = resp.json()
      assert body["action_id"] == 1 and body["state"] == "proposed"


  def test_email_action_gate_returns_400_without_confirm(client, tmp_db):
      """POST /api/emails/{id}/action with confirm=false must return 400 — the gate check."""
      eid = repo.upsert_email_message(
          mailbox="INBOX", uid=21, message_id="<m21@acme>", thread_id=None,
          from_addr="hr@acme.com", from_name="HR", subject="Follow up",
          received_at="2026-07-01T11:00:00+00:00",
          snippet="Following up", body_text="Following up.",
      )
      resp = client.post(
          f"/api/emails/{eid}/action",
          headers=AUTH,
          json={"kind": "archive", "confirm": False},
      )
      assert resp.status_code == 400


  def test_email_action_confirm_succeeds(client, tmp_db, monkeypatch):
      """POST /api/emails/{id}/action with confirm=true returns 200; no real IMAP called."""
      eid = repo.upsert_email_message(
          mailbox="INBOX", uid=22, message_id="<m22@acme>", thread_id=None,
          from_addr="hr@acme.com", from_name="HR", subject="Confirm",
          received_at="2026-07-01T12:00:00+00:00",
          snippet="Please confirm", body_text="Please confirm availability.",
      )
      monkeypatch.setattr(
          app_module.services,
          "confirm_action",
          lambda email_id, *, action_id=None, confirm=False: {
              "action_id": 1,
              "kind": "archive",
              "state": "executed",
              "executed_at": "2026-07-01T12:05:00+00:00",
          },
      )
      resp = client.post(
          f"/api/emails/{eid}/action",
          headers=AUTH,
          json={"kind": "archive", "confirm": True},
      )
      assert resp.status_code == 200
      assert resp.json()["state"] == "executed"
  ```

- [ ] **Step 2: Run targeted tests**

  ```bash
  cd /Users/BackendIntern/Documents/job-hunt/backend && uv run pytest tests/test_e2e_api.py -q
  ```
  Expected: all passing (including 3 new tests).

- [ ] **Step 3: Run full suite**

  ```bash
  cd /Users/BackendIntern/Documents/job-hunt/backend && uv run pytest -q
  ```
  Expected: all green.

---

### Task 7: Verify and Report

- [ ] **Step 1: Full ruff**

  ```bash
  cd /Users/BackendIntern/Documents/job-hunt/backend && uv run ruff check .
  ```
  Expected: clean.

- [ ] **Step 2: Frontend build + vitest**

  ```bash
  cd /Users/BackendIntern/Documents/job-hunt/frontend && npm run build && npx vitest run
  ```
  Expected: both pass.

- [ ] **Step 3: Write report to `.superpowers/sdd/email-v2t3-report.md`**

  Include: files modified, test output (pytest -q + ruff), build output, confirm 400-on-unconfirmed behavior, confirm MCP server unchanged.
