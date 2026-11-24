"""Cold-email outreach services — store drafts, send once on confirm, follow up once, stop on reply.

The email text is written elsewhere (Claude Code in ai-job-search) and arrives via
`save_outreach_draft`. Nothing here sends mail unless `send_outreach(..., confirm=True)`;
the MCP server deliberately has no send tool. Follow-ups use a fixed template.
"""
from __future__ import annotations

import os
from datetime import UTC, date, datetime, timedelta
from email.utils import parseaddr
from typing import Any
from urllib.parse import quote

from job_hunt.draft.outreach import build_follow_up_body, check_email_text, find_placeholders
from job_hunt.email import reader, sender
from job_hunt.enums import OutreachStatus
from job_hunt.logging_config import get_logger
from job_hunt.notify.base import Notifier, get_notifier
from job_hunt.services.applicant import get_applicant
from job_hunt.storage import repo

logger = get_logger(__name__)

DAILY_SEND_CAP = int(os.getenv("OUTREACH_DAILY_CAP", "15"))  # sends per rolling 24 hours
FOLLOWUP_AFTER_DAYS = int(os.getenv("OUTREACH_FOLLOWUP_AFTER_DAYS", "6"))
MAX_SUBJECT_CHARS = 120
MAX_BODY_CHARS = 4000
MAX_EMAIL_CHARS = 254
COLD_EMAIL_SLUG = "cold_email@1"
FOLLOW_UP_SLUG = "follow_up@1"
_SIGNATURE_DELIMITER = "-- "


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds")


def _clean_email(raw: str) -> str | None:
    """Return a single plain address, or None if it is not one."""
    candidate = raw.strip()
    if not candidate or len(candidate) > MAX_EMAIL_CHARS:
        return None
    if any(ch in candidate for ch in ' "\\\r\n\t<>,;'):
        return None
    _name, addr = parseaddr(candidate)
    local, at, domain = addr.rpartition("@")
    if addr != candidate or not at or not local or "@" in local or "." not in domain:
        return None
    return addr


def _validate_text(subject: str, body: str) -> str | None:
    if "\r" in subject or "\n" in subject:
        return "subject must be a single line"
    if not subject.strip() or len(subject) > MAX_SUBJECT_CHARS:
        return f"subject must be 1–{MAX_SUBJECT_CHARS} characters"
    if not body.strip() or len(body) > MAX_BODY_CHARS:
        return f"body must be 1–{MAX_BODY_CHARS} characters"
    return None


def _sender_identity() -> tuple[str, str] | None:
    """Return (full name, signature block) from the applicant profile, or None if no name."""
    profile = get_applicant()
    name = " ".join(p for p in (profile.get("first_name"), profile.get("last_name")) if p)
    if not name.strip():
        return None
    lines = [name, profile.get("phone"), profile.get("linkedin_url")]
    signature = "\n".join([_SIGNATURE_DELIMITER, *(str(v).strip() for v in lines if v)])
    return name, signature


def _with_signature(body: str, signature: str) -> str:
    """Append the profile signature once, so phone and links are never AI-written."""
    if signature in body:
        return body
    return f"{body.rstrip()}\n\n{signature}"


def _mailto(to_email: str, subject: str, body: str) -> str:
    return f"mailto:{quote(to_email)}?subject={quote(subject)}&body={quote(body)}"


def _not_found(outreach_id: int) -> dict[str, Any]:
    # "not found" is one of api/app.py's _NOT_FOUND_HINTS → HTTP 404.
    return {"error": f"outreach {outreach_id} not found"}


def _find_contact(company: str, contact_name: str) -> int | None:
    for row in repo.list_contacts(company):
        if row["name"] == contact_name:
            return int(row["id"])
    return None


def save_outreach_draft(
    company: str,
    contact_name: str,
    to_email: str,
    subject: str,
    body: str,
    *,
    job_id: int | None = None,
) -> dict[str, Any]:
    """Store a cold email written elsewhere as a draft; return it with style warnings."""
    repo.init_db()
    company, contact_name = company.strip(), contact_name.strip()
    if not company or not contact_name:
        return {"error": "company and contact name are required"}
    address = _clean_email(to_email)
    if address is None:
        return {"error": f"not a valid email address: {to_email!r}"}
    problem = _validate_text(subject, body)
    if problem:
        return {"error": problem}
    if job_id is not None and repo.get_job(job_id) is None:
        return {"error": f"no job with id={job_id}"}
    identity = _sender_identity()
    if identity is None:
        return {"error": "set your first name in the applicant profile first (hunt applicant)"}
    _name, signature = identity

    full_body = _with_signature(body, signature)
    # Reuse an existing contact: save_contact's upsert would blank its other fields.
    contact_id = _find_contact(company, contact_name) or repo.save_contact(
        company=company, name=contact_name, email_guess=address,
    )
    outreach_id = repo.insert_outreach(
        contact_id=contact_id, job_id=job_id, to_email=address, subject=subject.strip(),
        body=full_body, mailto_url=_mailto(address, subject, full_body),
        template_slug=COLD_EMAIL_SLUG,
    )
    logger.info("outreach drafted id=%d", outreach_id)
    return {**dict(repo.get_outreach(outreach_id)),
            "warnings": check_email_text(subject, full_body)}


def list_outreach(status: OutreachStatus | None = None, limit: int = 100) -> list[dict[str, Any]]:
    """Return outreach emails, newest first, optionally filtered by status."""
    repo.init_db()
    return [dict(r) for r in repo.list_outreach(status=status, limit=limit)]


def get_outreach(outreach_id: int) -> dict[str, Any]:
    """Return one outreach email or an error."""
    repo.init_db()
    row = repo.get_outreach(outreach_id)
    return dict(row) if row else _not_found(outreach_id)


def edit_outreach(
    outreach_id: int,
    *,
    subject: str | None = None,
    body: str | None = None,
    to_email: str | None = None,
) -> dict[str, Any]:
    """Edit a draft or failed email (the full text, signature included)."""
    repo.init_db()
    row = repo.get_outreach(outreach_id)
    if row is None:
        return _not_found(outreach_id)
    new_subject = row["subject"] if subject is None else subject
    new_body = row["body"] if body is None else body
    address = _clean_email(row["to_email"] if to_email is None else to_email)
    if address is None:
        return {"error": f"not a valid email address: {to_email!r}"}
    problem = _validate_text(new_subject, new_body)
    if problem:
        return {"error": problem}
    if not repo.update_outreach_draft(
        outreach_id, subject=new_subject.strip(), body=new_body, to_email=address,
    ):
        return {"error": f"outreach {outreach_id} is {row['status']}; "
                         "only draft or failed emails can be edited"}
    return {**dict(repo.get_outreach(outreach_id)),
            "warnings": check_email_text(new_subject, new_body)}


def cancel_outreach(outreach_id: int) -> dict[str, Any]:
    """Cancel a draft, failed or sent email (a sent one then gets no follow-up)."""
    repo.init_db()
    row = repo.get_outreach(outreach_id)
    if row is None:
        return _not_found(outreach_id)
    if not repo.set_outreach_cancelled(outreach_id):
        return {"error": f"outreach {outreach_id} is {row['status']} and can't be cancelled"}
    return {"id": outreach_id, "status": str(OutreachStatus.CANCELLED)}


def _follow_up_blocker(row: dict[str, Any]) -> str | None:
    """Return why a follow-up must not go out (and cancel it), or None if it may."""
    parent = repo.get_outreach(int(row["parent_id"]))
    if parent is None or parent["status"] != OutreachStatus.SENT:
        repo.set_outreach_cancelled(int(row["id"]))
        return "the original email is no longer awaiting a reply; follow-up cancelled"
    host = os.getenv("EMAIL_IMAP_HOST")
    address = os.getenv("EMAIL_ADDRESS")
    password = os.getenv("EMAIL_APP_PASSWORD")
    if not (host and address and password):
        return None  # no inbox access configured; rely on the last `hunt email sync`
    # SQLite stores "2026-11-24T10:00:00+00:00", Postgres ::text gives "2026-11-24 10:00:00+00".
    sent_on = date.fromisoformat(str(parent["sent_at"])[:10])
    try:
        with reader.connect_imap(host, address, password) as conn:
            replied = reader.has_reply_from(conn, row["to_email"], sent_on)
    except Exception as exc:  # noqa: BLE001 — any IMAP failure means "unknown", so don't send
        logger.warning("reply check failed for outreach id=%d: %s", row["id"], type(exc).__name__)
        return "could not check your inbox for a reply; try again later"
    if replied:
        repo.mark_outreach_replied([row["to_email"]])
        repo.set_outreach_cancelled(int(row["id"]))
        return "they already replied; follow-up cancelled"
    return None


def send_outreach(outreach_id: int, *, confirm: bool = False) -> dict[str, Any]:
    """Send one draft over SMTP — THE GATE: nothing happens unless confirm is exactly True."""
    if confirm is not True:
        return {"error": "confirmation required"}

    host = os.getenv("EMAIL_SMTP_HOST")
    address = os.getenv("EMAIL_ADDRESS")
    password = os.getenv("EMAIL_APP_PASSWORD")
    if not (host and address and password):
        return {"error": "smtp not configured (EMAIL_SMTP_HOST, EMAIL_ADDRESS, "
                         "EMAIL_APP_PASSWORD)"}
    try:
        port = int(os.getenv("EMAIL_SMTP_PORT", "465"))
    except ValueError:
        return {"error": "EMAIL_SMTP_PORT must be a number"}

    repo.init_db()
    found = repo.get_outreach(outreach_id)
    if found is None:
        return _not_found(outreach_id)
    row = dict(found)
    placeholders = find_placeholders(f"{row['subject']}\n{row['body']}")
    if placeholders:
        return {"error": f"unfilled placeholder left in the email: {', '.join(placeholders)}"}
    sent_recently = repo.count_outreach_sent_since(_iso(_now() - timedelta(days=1)))
    if sent_recently >= DAILY_SEND_CAP:
        logger.info("outreach send refused id=%d reason=cap", outreach_id)
        return {"error": f"daily cap reached ({DAILY_SEND_CAP} emails in 24 hours)"}
    identity = _sender_identity()
    if identity is None:
        return {"error": "set your first name in the applicant profile first (hunt applicant)"}
    from_name, _signature = identity
    in_reply_to = None
    if row["parent_id"] is not None:
        blocker = _follow_up_blocker(row)
        if blocker:
            return {"error": blocker}
        in_reply_to = repo.get_outreach(int(row["parent_id"]))["message_id"]

    if not repo.claim_outreach_for_send(outreach_id):
        return {"error": f"outreach {outreach_id} is {row['status']}; "
                         "already sent or in progress"}
    try:
        msg = sender.build_message(
            from_address=address, from_name=from_name, to_address=row["to_email"],
            subject=row["subject"], body=row["body"], in_reply_to=in_reply_to,
        )
        sender.send_message(msg, host=host, port=port, address=address, password=password)
    except Exception as exc:  # noqa: BLE001 — record any failure on the row, never re-send blindly
        repo.set_outreach_failed(outreach_id, error=type(exc).__name__)
        logger.warning("outreach send failed id=%d err=%s", outreach_id, type(exc).__name__)
        return {"error": f"send failed: {type(exc).__name__}"}
    # A crash between here and the next line leaves the row 'sending'; it is never auto-retried.
    repo.set_outreach_sent(outreach_id, message_id=str(msg["Message-ID"]))
    logger.info("outreach sent id=%d", outreach_id)
    sent = repo.get_outreach(outreach_id)
    return {"id": outreach_id, "status": sent["status"], "sent_at": sent["sent_at"]}


def draft_due_followups(*, now: datetime | None = None) -> dict[str, Any]:
    """Draft one fixed follow-up for each sent email with no reply after FOLLOWUP_AFTER_DAYS."""
    repo.init_db()
    identity = _sender_identity()
    if identity is None:
        return {"error": "set your first name in the applicant profile first (hunt applicant)"}
    sender_name, signature = identity
    cutoff = (now or _now()) - timedelta(days=FOLLOWUP_AFTER_DAYS)
    drafted: list[int] = []
    for due in repo.list_followups_due(_iso(cutoff)):
        original = dict(due)
        job = repo.get_job(int(original["job_id"])) if original["job_id"] else None
        body = _with_signature(
            build_follow_up_body(
                first_name=(original["contact_name"] or "").split(" ")[0],
                role=(job["title"] or "") if job else "",
                sender_name=sender_name.split(" ")[0],
            ),
            signature,
        )
        subject = original["subject"]
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"
        drafted.append(repo.insert_outreach(
            contact_id=int(original["contact_id"]), job_id=original["job_id"],
            to_email=original["to_email"], subject=subject, body=body,
            mailto_url=_mailto(original["to_email"], subject, body),
            template_slug=FOLLOW_UP_SLUG, parent_id=int(original["id"]),
        ))
    if drafted:
        logger.info("follow-ups drafted ids=%s", drafted)
    return {"drafted": len(drafted), "ids": drafted}


def draft_followups_and_notify(notifier: Notifier | None = None) -> dict[str, Any]:
    """Draft due follow-ups and, if any, send one short note to the notify channel (for CI)."""
    result = draft_due_followups()
    if "error" in result or not result["drafted"]:
        return {**result, "notified": False}
    text = (
        f"✉️ {result['drafted']} cold-email follow-up(s) ready to review.\n"
        "On your laptop: hunt outreach list --status draft, "
        "then hunt outreach send <id> --confirm"
    )
    return {**result, "notified": (notifier or get_notifier()).send(text)}


def record_replies(from_addrs: list[str]) -> int:
    """Mark sent emails as replied and cancel their unsent follow-ups; return how many."""
    repo.init_db()
    replied = set(repo.mark_outreach_replied(from_addrs))
    if not replied:
        return 0
    for draft in repo.list_outreach(status=OutreachStatus.DRAFT, limit=500):
        if draft["parent_id"] is not None and int(draft["parent_id"]) in replied:
            repo.set_outreach_cancelled(int(draft["id"]))
    logger.info("outreach replied ids=%s", sorted(replied))
    return len(replied)
