"""Tests for the reversible mailbox-mutation primitives in job_hunt.email.reader.

Hermetic — no real IMAP connections. A _FakeConn records every append/uid/select
call so we can assert the correct IMAP commands are issued (and dangerous ones
are NOT issued).
"""
from __future__ import annotations

import email as _email_stdlib

from job_hunt.email.reader import (
    RawEmail,
    add_label,
    append_draft,
    archive,
    build_reply_draft,
)

# ---------------------------------------------------------------------------
# Fake IMAP connection — records calls, raises on prohibited operations
# ---------------------------------------------------------------------------


class _FakeConn:
    """Record IMAP operations; never touches a socket."""

    def __init__(self) -> None:
        self.appends: list[tuple] = []  # (mailbox, flags, date, data)
        self.uid_calls: list[tuple] = []  # (command, *args)
        self.selects: list[tuple] = []  # (mailbox,) or (mailbox, readonly)

    def append(self, mailbox: str, flags: str, date: object, data: bytes) -> tuple:
        self.appends.append((mailbox, flags, date, data))
        return ("OK", [b"1 (APPENDUID 1 1)"])

    def uid(self, command: str, *args: str) -> tuple:
        self.uid_calls.append((command, *args))
        return ("OK", [b"1"])

    def select(self, mailbox: str, readonly: bool = False) -> tuple:
        self.selects.append((mailbox, readonly))
        return ("OK", [b"10"])

    # convenience: flatten all recorded call strings for the safety assertion
    def all_call_strings(self) -> list[str]:
        parts: list[str] = []
        for a in self.appends:
            parts.extend(str(x) for x in a)
        for u in self.uid_calls:
            parts.extend(str(x) for x in u)
        for s in self.selects:
            parts.extend(str(x) for x in s)
        return parts


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_raw_email(
    *,
    from_addr: str = "recruiter@example.com",
    subject: str = "Job opportunity",
    message_id: str | None = "<abc123@mail.example.com>",
) -> RawEmail:
    return RawEmail(
        mailbox="INBOX",
        uid=42,
        message_id=message_id,
        thread_id="999",
        from_addr=from_addr,
        from_name="Alice Recruiter",
        subject=subject,
        received_at="2024-01-01T12:00:00+00:00",
        body_text="We'd like to discuss an opportunity.",
    )


# ---------------------------------------------------------------------------
# build_reply_draft
# ---------------------------------------------------------------------------


def test_build_reply_draft_headers():
    original = _make_raw_email()
    draft_bytes = build_reply_draft(original, "Thank you!", "me@example.com")
    msg = _email_stdlib.message_from_bytes(draft_bytes)

    assert msg["To"] == "recruiter@example.com"
    assert msg["From"] == "me@example.com"
    assert msg["Subject"] == "Re: Job opportunity"
    assert msg["In-Reply-To"] == "<abc123@mail.example.com>"
    assert msg["References"] == "<abc123@mail.example.com>"


def test_build_reply_draft_no_double_re_prefix():
    original = _make_raw_email(subject="Re: Already a reply")
    draft_bytes = build_reply_draft(original, "Body.", "me@example.com")
    msg = _email_stdlib.message_from_bytes(draft_bytes)
    assert msg["Subject"] == "Re: Already a reply"


def test_build_reply_draft_case_insensitive_re_check():
    original = _make_raw_email(subject="RE: Uppercase Re")
    draft_bytes = build_reply_draft(original, "Body.", "me@example.com")
    msg = _email_stdlib.message_from_bytes(draft_bytes)
    assert msg["Subject"] == "RE: Uppercase Re"


def test_build_reply_draft_no_message_id_omits_headers():
    original = _make_raw_email(message_id=None)
    draft_bytes = build_reply_draft(original, "Body.", "me@example.com")
    msg = _email_stdlib.message_from_bytes(draft_bytes)
    assert msg["In-Reply-To"] is None
    assert msg["References"] is None


def test_build_reply_draft_empty_subject():
    original = _make_raw_email(subject="")
    draft_bytes = build_reply_draft(original, "Body.", "me@example.com")
    msg = _email_stdlib.message_from_bytes(draft_bytes)
    assert msg["Subject"] == "Re: "


def test_build_reply_draft_body_in_payload():
    original = _make_raw_email()
    reply_body = "Hello, thanks for reaching out!"
    draft_bytes = build_reply_draft(original, reply_body, "me@example.com")
    # EmailMessage.set_content uses Content-Type text/plain
    assert b"Hello, thanks for reaching out!" in draft_bytes


def test_build_reply_draft_returns_bytes():
    original = _make_raw_email()
    result = build_reply_draft(original, "Body.", "me@example.com")
    assert isinstance(result, bytes)


# ---------------------------------------------------------------------------
# append_draft
# ---------------------------------------------------------------------------


def test_append_draft_uses_drafts_mailbox():
    conn = _FakeConn()
    draft_bytes = b"MIME-Version: 1.0\r\n\r\nHello"
    append_draft(conn, draft_bytes)
    assert len(conn.appends) == 1
    mailbox, flags, _date, data = conn.appends[0]
    assert mailbox == "[Gmail]/Drafts"
    assert flags == "(\\Draft)"
    assert data == draft_bytes


def test_append_draft_custom_mailbox():
    conn = _FakeConn()
    append_draft(conn, b"draft", drafts_mailbox="Drafts")
    assert conn.appends[0][0] == "Drafts"


def test_append_draft_draft_flag_present():
    conn = _FakeConn()
    append_draft(conn, b"draft")
    assert "(\\Draft)" in conn.appends[0][1]


# ---------------------------------------------------------------------------
# add_label
# ---------------------------------------------------------------------------


def test_add_label_issues_plus_x_gm_labels():
    conn = _FakeConn()
    add_label(conn, "INBOX", 99, "JobHunt")
    assert len(conn.uid_calls) == 1
    cmd, uid_str, op, label_arg = conn.uid_calls[0]
    assert cmd == "STORE"
    assert uid_str == "99"
    assert op == "+X-GM-LABELS"
    assert "JobHunt" in label_arg


def test_add_label_selects_writable():
    conn = _FakeConn()
    add_label(conn, "INBOX", 5, "Interesting")
    assert len(conn.selects) == 1
    mailbox, readonly = conn.selects[0]
    assert mailbox == "INBOX"
    assert readonly is False


# ---------------------------------------------------------------------------
# archive
# ---------------------------------------------------------------------------


def test_archive_issues_minus_x_gm_labels_inbox():
    conn = _FakeConn()
    archive(conn, "INBOX", 77)
    assert len(conn.uid_calls) == 1
    cmd, uid_str, op, label_arg = conn.uid_calls[0]
    assert cmd == "STORE"
    assert uid_str == "77"
    assert op == "-X-GM-LABELS"
    assert "\\Inbox" in label_arg


def test_archive_selects_writable():
    conn = _FakeConn()
    archive(conn, "INBOX", 7)
    assert len(conn.selects) == 1
    mailbox, readonly = conn.selects[0]
    assert mailbox == "INBOX"
    assert readonly is False


# ---------------------------------------------------------------------------
# Safety: no send, no \Deleted, no EXPUNGE across all operations
# ---------------------------------------------------------------------------


def _all_calls_for_all_ops() -> list[str]:
    """Run every mutation primitive and collect all recorded call strings."""
    conn = _FakeConn()
    original = _make_raw_email()
    draft_bytes = build_reply_draft(original, "Body.", "me@example.com")
    append_draft(conn, draft_bytes)
    add_label(conn, "INBOX", 1, "SomeLabel")
    archive(conn, "INBOX", 2)
    return conn.all_call_strings()


def test_no_deleted_flag_in_any_call():
    for call_str in _all_calls_for_all_ops():
        assert "\\Deleted" not in call_str, f"\\Deleted found in: {call_str}"


def test_no_expunge_in_any_call():
    for call_str in _all_calls_for_all_ops():
        assert "EXPUNGE" not in call_str.upper(), f"EXPUNGE found in: {call_str}"


def test_no_send_in_any_call():
    """SMTP SEND / IMAP COPY or MOVE must never appear."""
    for call_str in _all_calls_for_all_ops():
        assert "SEND" not in call_str.upper(), f"SEND found in: {call_str}"
