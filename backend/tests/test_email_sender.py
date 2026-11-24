"""Tests for outbound SMTP (email/sender.py) and the IMAP reply guard (reader.has_reply_from).

Hermetic: no network. SMTP_SSL and the IMAP connection are replaced by recording fakes.
"""
from __future__ import annotations

import logging
import smtplib
from datetime import date
from email.message import EmailMessage
from typing import Any

import pytest

from job_hunt.email import reader, sender

_PASSWORD = "app-password-123"


def _msg(**overrides: Any) -> EmailMessage:
    fields: dict[str, Any] = {
        "from_address": "bhanu@gmail.com",
        "from_name": "Bhanu Teja",
        "to_address": "priya@acme.com",
        "subject": "Backend engineer — NestJS/PostgreSQL",
        "body": "Hi Priya,\n\nShort note.\n",
    }
    fields.update(overrides)
    return sender.build_message(**fields)


# ---------- build_message ----------


def test_build_message_sets_plain_text_headers():
    msg = _msg()
    assert msg["From"] == "Bhanu Teja <bhanu@gmail.com>"
    assert msg["To"] == "priya@acme.com"
    assert msg["Subject"] == "Backend engineer — NestJS/PostgreSQL"
    assert msg.get_content_type() == "text/plain"
    assert msg["Date"]
    assert msg["In-Reply-To"] is None and msg["References"] is None


def test_message_id_uses_sender_domain_not_machine_hostname():
    msg_id = _msg()["Message-ID"]
    assert msg_id.startswith("<") and msg_id.endswith("@gmail.com>")
    assert _msg()["Message-ID"] != msg_id  # fresh per message


def test_follow_up_threads_under_original():
    msg = _msg(in_reply_to="<orig-1@gmail.com>")
    assert msg["In-Reply-To"] == "<orig-1@gmail.com>"
    assert msg["References"] == "<orig-1@gmail.com>"


@pytest.mark.parametrize("field", ["to_address", "subject", "from_name", "in_reply_to"])
@pytest.mark.parametrize("bad", ["x\nBcc: evil@x.com", "x\rBcc: evil@x.com"])
def test_build_message_rejects_header_injection(field, bad):
    with pytest.raises(ValueError):
        _msg(**{field: bad})


# ---------- send_message ----------


class _FakeSMTP:
    """Stand-in for smtplib.SMTP_SSL; records the connection and what was sent."""

    instances: list[_FakeSMTP] = []
    refused: dict[str, tuple[int, bytes]] = {}

    def __init__(self, host: str, port: int, *, context: Any, timeout: int) -> None:
        self.host, self.port, self.context, self.timeout = host, port, context, timeout
        self.logins: list[tuple[str, str]] = []
        self.sent: list[EmailMessage] = []
        _FakeSMTP.instances.append(self)

    def __enter__(self) -> _FakeSMTP:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def login(self, user: str, password: str) -> None:
        self.logins.append((user, password))

    def send_message(self, msg: EmailMessage) -> dict[str, tuple[int, bytes]]:
        self.sent.append(msg)
        return _FakeSMTP.refused


@pytest.fixture
def fake_smtp(monkeypatch):
    _FakeSMTP.instances = []
    _FakeSMTP.refused = {}
    monkeypatch.setattr(sender.smtplib, "SMTP_SSL", _FakeSMTP)
    return _FakeSMTP


def _send(msg: EmailMessage) -> None:
    sender.send_message(msg, host="smtp.gmail.com", port=465,
                        address="bhanu@gmail.com", password=_PASSWORD)


def test_send_message_uses_verified_tls_login_and_timeout(fake_smtp):
    msg = _msg()
    _send(msg)
    (smtp,) = fake_smtp.instances
    assert (smtp.host, smtp.port, smtp.timeout) == ("smtp.gmail.com", 465, 30)
    assert smtp.context.check_hostname is True
    assert smtp.logins == [("bhanu@gmail.com", _PASSWORD)]
    assert smtp.sent == [msg]


def test_send_message_raises_when_recipient_refused(fake_smtp):
    fake_smtp.refused = {"priya@acme.com": (550, b"no such user")}
    with pytest.raises(smtplib.SMTPRecipientsRefused):
        _send(_msg())


def test_send_message_never_logs_password_or_recipient(fake_smtp, caplog):
    # The `job_hunt` logger tree doesn't propagate to root, so attach caplog to it directly.
    tree = logging.getLogger("job_hunt")
    tree.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.DEBUG, logger="job_hunt"):
            _send(_msg())
    finally:
        tree.removeHandler(caplog.handler)
    assert "SMTP message sent via host=smtp.gmail.com" in caplog.text  # capture is live
    assert _PASSWORD not in caplog.text
    assert "priya@acme.com" not in caplog.text


# ---------- has_reply_from ----------


class _FakeConn:
    """Stand-in for imaplib.IMAP4_SSL; answers UID SEARCH with canned UIDs."""

    def __init__(self, uids: bytes) -> None:
        self.uids = uids
        self.calls: list[tuple[Any, ...]] = []

    def select(self, mailbox: str, readonly: bool = False) -> tuple[str, list[bytes]]:
        self.calls.append(("select", mailbox, readonly))
        return ("OK", [b"1"])

    def uid(self, cmd: str, *args: str) -> tuple[str, list[bytes]]:
        self.calls.append(("uid", cmd, *args))
        return ("OK", [self.uids])


@pytest.mark.parametrize(("uids", "expected"), [(b"12 13", True), (b"", False)])
def test_has_reply_from(uids, expected):
    conn = _FakeConn(uids)
    assert reader.has_reply_from(conn, "priya@acme.com", date(2026, 3, 5)) is expected
    assert conn.calls[0] == ("select", "INBOX", True)  # read-only: never marks mail seen
    assert conn.calls[1] == ("uid", "SEARCH", "FROM", '"priya@acme.com"', "SINCE", "05-Mar-2026")


@pytest.mark.parametrize("bad", ['a"b@x.com', "a\\b@x.com", "a@x.com\r\nX", ""])
def test_has_reply_from_rejects_unsafe_address(bad):
    conn = _FakeConn(b"")
    with pytest.raises(ValueError):
        reader.has_reply_from(conn, bad, date(2026, 3, 5))
    assert conn.calls == []  # nothing sent to the server
