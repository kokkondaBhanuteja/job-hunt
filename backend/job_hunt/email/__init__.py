"""job_hunt.email — IMAP reader + SMTP sender, stdlib-only.

Re-exports the public surface of `reader` so callers do:
    from job_hunt.email import RawEmail, connect_imap, fetch_new, select_mailbox
Outbound mail lives in `job_hunt.email.sender` (imported directly).
"""
from job_hunt.email.reader import (
    RawEmail,
    connect_imap,
    fetch_new,
    select_mailbox,
)

__all__ = ["RawEmail", "connect_imap", "fetch_new", "select_mailbox"]
