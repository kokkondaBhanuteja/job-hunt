"""Email action pipeline — propose, confirm, and dismiss human-reviewed email actions.

Responsibilities:
  - ``propose_action``: create a human-review proposal for a mailbox mutation (NO IMAP).
  - ``confirm_action``: the security gate — performs IMAP mutation ONLY when confirm=True.
  - ``dismiss_action``: mark a proposed action dismissed.

No mailbox mutations occur without an explicit confirm=True from the caller.
The v1 triage pipeline (sync/structure/list/get) lives in ``email_triage``.
"""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Any

from job_hunt.email import reader
from job_hunt.enums import EmailActionKind, EmailActionState, LLMTask
from job_hunt.llm import chat
from job_hunt.logging_config import get_logger
from job_hunt.services.context import context_preamble
from job_hunt.storage import repo

logger = get_logger(__name__)


def propose_action(
    email_id: int,
    kind: str,
    *,
    label: str | None = None,
) -> dict[str, Any]:
    """Propose an email action for human review; store it and return {action_id, kind, payload, state}.

    Performs NO IMAP call and NO mailbox mutation — output is for human review only.
    For draft_reply, the reply body is generated from extracted structured fields +
    context_preamble() only; raw body_text is never fed to the LLM to prevent injection.
    """
    repo.init_db()

    # Validate kind — ValueError for unknown values.
    try:
        action_kind = EmailActionKind(kind)
    except ValueError:
        valid = [k.value for k in EmailActionKind]
        return {"error": f"invalid kind '{kind}'; must be one of {valid}"}

    # Load email row.
    row = repo.get_email_message(email_id)
    if row is None:
        return {"error": f"email {email_id} not found"}

    row_dict = dict(row)

    # Build payload per action kind.
    if action_kind is EmailActionKind.DRAFT_REPLY:
        # Parse structured (LLM-extracted) metadata — never use raw body_text.
        extracted_raw = row_dict.get("extracted") or "{}"
        try:
            extracted: dict[str, Any] = (
                json.loads(extracted_raw) if isinstance(extracted_raw, str) else {}
            )
        except (json.JSONDecodeError, TypeError):
            extracted = {}

        # Build the draft prompt from structured extracted fields ONLY.
        # Raw headers (subject, from_name, from_addr, body_text) are never
        # interpolated here — they are attacker-controlled and must not reach
        # the LLM to prevent prompt-injection attacks.
        preamble = context_preamble()
        recruiter_name = extracted.get("recruiter_name") or ""
        company = extracted.get("company") or ""
        role = extracted.get("role") or ""
        summary = extracted.get("summary") or ""
        category = extracted.get("category") or ""

        greeting = f"Hi {recruiter_name}" if recruiter_name else "Hi"
        prompt = (
            f"{preamble}"
            "Draft a concise, professional reply to a recruiter email.\n\n"
            f"Greeting: {greeting}\n"
        )
        if company:
            prompt += f"Company: {company}\n"
        if role:
            prompt += f"Role: {role}\n"
        if summary:
            prompt += f"Summary: {summary}\n"
        if category:
            prompt += f"Category: {category}\n"

        reply_body = chat(prompt, task=str(LLMTask.DRAFTING))
        payload: dict[str, Any] = {"reply_body": reply_body}

    elif action_kind is EmailActionKind.APPLY_LABEL:
        payload = {"label": label or "JobHunt"}

    else:  # EmailActionKind.ARCHIVE
        payload = {}

    action_id = repo.create_email_action(email_id=email_id, kind=kind, payload=payload)
    repo.set_email_action_state(email_id, str(EmailActionState.PROPOSED))

    return {
        "action_id": action_id,
        "kind": kind,
        "payload": payload,
        "state": str(EmailActionState.PROPOSED),
    }


def confirm_action(
    email_id: int,
    *,
    action_id: int | None = None,
    confirm: bool = False,
) -> dict[str, Any]:
    """Execute the pending proposed action — THE SECURITY GATE.

    Returns {"error": "confirmation required"} immediately if confirm is not exactly True;
    no IMAP connection is opened, no state is changed. The confirm=True check is the
    single guarantee that untrusted email content can never trigger a mailbox mutation.
    """
    # *** THE GATE — must be the very first check; nothing else opens IMAP. ***
    if confirm is not True:
        return {"error": "confirmation required"}

    repo.init_db()

    # Load action.
    if action_id is not None:
        action_row = repo.get_email_action(action_id)
    else:
        action_row = repo.get_latest_action_for_email(email_id)

    if action_row is None:
        return {"error": "no action found"}

    action = dict(action_row)
    act_id: int = int(action["id"])

    # Ownership check — prevent a confused-deputy attack where an action
    # belonging to one email is confirmed via a different email_id.
    if int(action["email_id"]) != int(email_id):
        return {"error": "action does not belong to this email"}

    if action["state"] != str(EmailActionState.PROPOSED):
        return {
            "error": (
                f"action {act_id} is not in proposed state (state={action['state']})"
            )
        }

    # Load email row.
    email_row = repo.get_email_message(email_id)
    if email_row is None:
        return {"error": f"email {email_id} not found"}
    email_dict = dict(email_row)

    # Read IMAP credentials.
    host = os.getenv("EMAIL_IMAP_HOST")
    address = os.getenv("EMAIL_ADDRESS")
    password = os.getenv("EMAIL_APP_PASSWORD")
    if not host or not address or not password:
        return {"error": "email not configured"}

    # Parse stored payload.
    payload_raw = action.get("payload") or "{}"
    try:
        payload: dict[str, Any] = (
            json.loads(payload_raw) if isinstance(payload_raw, str) else {}
        )
    except (json.JSONDecodeError, TypeError):
        payload = {}

    try:
        action_kind = EmailActionKind(action["kind"])
    except ValueError:
        return {"error": f"stored action kind '{action['kind']}' is not a recognised action type"}
    now = datetime.now(UTC).isoformat()

    try:
        with reader.connect_imap(host, address, password) as conn:
            if action_kind is EmailActionKind.DRAFT_REPLY:
                # Reconstruct minimal RawEmail for header-building; reply body from payload.
                original = reader.RawEmail(
                    mailbox=email_dict["mailbox"],
                    uid=int(email_dict["uid"]),
                    message_id=email_dict.get("message_id"),
                    thread_id=email_dict.get("thread_id"),
                    from_addr=email_dict.get("from_addr"),
                    from_name=email_dict.get("from_name"),
                    subject=email_dict.get("subject"),
                    received_at=email_dict.get("received_at"),
                    body_text="",  # not used for reply headers; body comes from payload
                )
                draft_bytes = reader.build_reply_draft(original, payload["reply_body"], address)
                reader.append_draft(conn, draft_bytes)

            elif action_kind is EmailActionKind.APPLY_LABEL:
                reader.add_label(
                    conn, email_dict["mailbox"], int(email_dict["uid"]), payload["label"]
                )

            else:  # EmailActionKind.ARCHIVE
                reader.archive(conn, email_dict["mailbox"], int(email_dict["uid"]))

    except Exception as exc:
        logger.exception("IMAP execution failed for action_id=%d: %s", act_id, exc)
        repo.set_email_action_result(
            act_id, state=str(EmailActionState.FAILED), executed_at=now
        )
        return {"error": str(exc)}

    repo.set_email_action_result(
        act_id, state=str(EmailActionState.EXECUTED), executed_at=now
    )
    repo.set_email_action_state(email_id, str(EmailActionState.EXECUTED))

    return {
        "action_id": act_id,
        "kind": action["kind"],
        "state": str(EmailActionState.EXECUTED),
        "executed_at": now,
    }


def dismiss_action(
    email_id: int,
    *,
    action_id: int | None = None,
) -> dict[str, Any]:
    """Mark the pending action DISMISSED and reset the email action_state to none."""
    repo.init_db()

    if action_id is not None:
        action_row = repo.get_email_action(action_id)
    else:
        action_row = repo.get_latest_action_for_email(email_id)

    if action_row is None:
        return {"error": "no action found"}

    action = dict(action_row)
    act_id = int(action["id"])

    # Ownership check — only applies when the caller supplied an explicit
    # action_id; the get_latest_action_for_email path already filters by email_id.
    if action_id is not None and int(action["email_id"]) != int(email_id):
        return {"error": "action does not belong to this email"}

    now = datetime.now(UTC).isoformat()

    repo.set_email_action_result(
        act_id, state=str(EmailActionState.DISMISSED), executed_at=now
    )
    repo.set_email_action_state(email_id, str(EmailActionState.NONE))

    return {"action_id": act_id, "state": str(EmailActionState.DISMISSED)}
