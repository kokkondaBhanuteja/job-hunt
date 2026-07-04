"""job_hunt.email — read-only IMAP email reader, stdlib-only.

Re-exports the public surface of `reader` so callers do:
    from job_hunt.email import RawEmail, connect_imap, fetch_new, select_mailbox
"""
from job_hunt.email.reader import (
    RawEmail,
    connect_imap,
    fetch_new,
    select_mailbox,
)

__all__ = ["RawEmail", "connect_imap", "fetch_new", "select_mailbox"]
