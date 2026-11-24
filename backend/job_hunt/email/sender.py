"""Outbound email over SMTP — stdlib only, zero new dependencies.

Builds plain-text messages (with threading headers for follow-ups) and sends them over
implicit TLS (``SMTP_SSL``, port 465). Nothing here decides *whether* to send: the
confirm gate, daily cap and exactly-once claim live in ``services.outreach``.
"""
from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

from job_hunt.logging_config import get_logger

logger = get_logger(__name__)

SMTP_TIMEOUT_SECONDS = 30


def _single_line(**fields: str) -> None:
    for name, value in fields.items():
        if "\r" in value or "\n" in value:
            raise ValueError(f"{name} must be a single line")


def build_message(
    *,
    from_address: str,
    from_name: str,
    to_address: str,
    subject: str,
    body: str,
    in_reply_to: str | None = None,
) -> EmailMessage:
    """Return a plain-text message with a fresh Message-ID (and threading headers if given)."""
    _single_line(from_address=from_address, from_name=from_name, to_address=to_address,
                 subject=subject, in_reply_to=in_reply_to or "")
    msg = EmailMessage()
    msg["From"] = formataddr((from_name, from_address))
    msg["To"] = to_address
    msg["Subject"] = subject
    msg["Date"] = formatdate(usegmt=True)
    # Use the sender's domain: the default would put this machine's hostname in the header.
    msg["Message-ID"] = make_msgid(domain=from_address.rpartition("@")[2] or None)
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to
    msg.set_content(body)
    return msg


def send_message(
    msg: EmailMessage,
    *,
    host: str,
    port: int,
    address: str,
    password: str,
    timeout: int = SMTP_TIMEOUT_SECONDS,
) -> None:
    """Send *msg* over SMTP_SSL with certificate verification; raise on any failure."""
    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL(host, port, context=ctx, timeout=timeout) as smtp:
        smtp.login(address, password)
        refused = smtp.send_message(msg)
    if refused:  # only possible with several recipients; we send to one, but never hide it
        raise smtplib.SMTPRecipientsRefused(refused)
    logger.info("SMTP message sent via host=%s", host)
