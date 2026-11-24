"""Tests for cold-email outreach: text checks, follow-up template, and the outreach service.

Hermetic — no LLM, no network: SMTP and IMAP are replaced by recording fakes, and the
service runs against the throwaway SQLite DB from the `tmp_db` fixture.
"""
from __future__ import annotations

import logging
import smtplib
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from typing import Any

import pytest

from job_hunt.draft.outreach import (
    MAX_BODY_WORDS,
    build_follow_up_body,
    check_email_text,
    find_placeholders,
)
from job_hunt.enums import OutreachStatus
from job_hunt.services import outreach

_CLEAN_SUBJECT = "Backend engineer, NestJS and PostgreSQL"
_CLEAN_BODY = (
    "Hi Priya,\n\n"
    "I'm a backend engineer at Tapza, where I've merged 587 pull requests on a multi-tenant "
    "pharmacy ERP built with NestJS and PostgreSQL. I saw Acme is hiring for its payments "
    "platform, and my recent work on Razorpay billing and webhook verification looks close "
    "to what the team does.\n\n"
    "Would you be open to a 15-minute call, or could you point me to the right person?\n\n"
    "Thanks,\nBhanu Teja Kokkonda"
)


# ---------- check_email_text ----------


def test_clean_email_has_no_warnings():
    assert check_email_text(_CLEAN_SUBJECT, _CLEAN_BODY) == []


@pytest.mark.parametrize(
    ("subject", "body", "expected"),
    [
        ("", _CLEAN_BODY, "subject is empty"),
        ("one two three four five six seven eight nine", _CLEAN_BODY, "subject is 9 words"),
        (_CLEAN_SUBJECT, "word " * (MAX_BODY_WORDS + 1), f"body is {MAX_BODY_WORDS + 1} words"),
        (_CLEAN_SUBJECT, "Hi [Name], quick note.", "unfilled placeholder: [Name]"),
        (_CLEAN_SUBJECT, "I like {{company}}.", "unfilled placeholder: {{company}}"),
        (_CLEAN_SUBJECT, "Hi <First Name>,", "unfilled placeholder: <First Name>"),
        ("About [Role]", _CLEAN_BODY, "unfilled placeholder: [Role]"),
        (_CLEAN_SUBJECT, "I **love** APIs.", "markdown formatting"),
        (_CLEAN_SUBJECT, "See [my site](https://x.dev).", "markdown formatting"),
        (_CLEAN_SUBJECT, "# Hello\nbody", "markdown formatting"),
        (_CLEAN_SUBJECT, "I am PASSIONATE about backends.", "avoid the phrase: 'passionate'"),
        (_CLEAN_SUBJECT, "I hope this email finds you well.", "avoid the phrase"),
    ],
)
def test_check_email_text_flags(subject, body, expected):
    warnings = check_email_text(subject, body)
    assert any(w.startswith(expected) for w in warnings), warnings


def test_markdown_link_is_not_a_placeholder():
    assert find_placeholders("See [my site](https://x.dev) and [Name].") == ["[Name]"]


@pytest.mark.parametrize("text", ["I led a team of <5 engineers.", "Cut p95 to 11 ms."])
def test_find_placeholders_ignores_normal_text(text):
    assert find_placeholders(text) == []


def test_any_short_bracketed_text_counts_as_placeholder():
    # Deliberately strict: brackets almost never belong in a plain cold email, and a
    # false positive only means "edit, then send", while a miss sends "[Name]" to a stranger.
    assert find_placeholders("Costs dropped [by 40%].") == ["[by 40%]"]


# ---------- build_follow_up_body ----------


def test_follow_up_is_short_clean_and_personal():
    body = build_follow_up_body(first_name="Priya", role="Backend Engineer",
                                sender_name="Bhanu Teja Kokkonda")
    assert body.startswith("Hi Priya,")
    assert "about the Backend Engineer role" in body
    assert "I won't follow up again." in body
    assert body.endswith("Thanks,\nBhanu Teja Kokkonda")
    assert len(body.split()) <= 60
    assert check_email_text(f"Re: {_CLEAN_SUBJECT}", body) == []


def test_follow_up_without_role_or_name_stays_natural():
    body = build_follow_up_body(first_name="  ", role="", sender_name="Bhanu")
    assert body.startswith("Hi there,")
    assert "about the" not in body
    assert find_placeholders(body) == []


# ---------- outreach service ----------

_PASSWORD = "app-password-123"
_ME = "bhanu@gmail.com"


class _FakeSMTP:
    """Stand-in for smtplib.SMTP_SSL; records sends, or raises if `error` is set."""

    sent: list[EmailMessage] = []
    error: Exception | None = None

    def __init__(self, host: str, port: int, *, context: Any, timeout: int) -> None:
        self.host, self.port = host, port

    def __enter__(self) -> _FakeSMTP:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def login(self, user: str, password: str) -> None:
        if _FakeSMTP.error is not None:
            raise _FakeSMTP.error

    def send_message(self, msg: EmailMessage) -> dict[str, Any]:
        _FakeSMTP.sent.append(msg)
        return {}


@pytest.fixture
def svc(tmp_db, monkeypatch):
    """Outreach service on a temp DB with a profile, SMTP env and a fake SMTP server."""
    for var in ("EMAIL_IMAP_HOST", "EMAIL_SMTP_PORT"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("EMAIL_SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("EMAIL_ADDRESS", _ME)
    monkeypatch.setenv("EMAIL_APP_PASSWORD", _PASSWORD)
    _FakeSMTP.sent, _FakeSMTP.error = [], None
    monkeypatch.setattr(outreach.sender.smtplib, "SMTP_SSL", _FakeSMTP)
    tmp_db.set_applicant_profile(fields={
        "first_name": "Bhanu", "last_name": "Teja", "phone": "+91 78938 81841",
        "linkedin_url": "linkedin.com/in/bhanu-teja-kokkonda",
    })
    return outreach


def _save(svc, **overrides: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "company": "Acme", "contact_name": "Priya Sharma", "to_email": "priya@acme.com",
        "subject": _CLEAN_SUBJECT, "body": _CLEAN_BODY,
    }
    fields.update(overrides)
    return svc.save_outreach_draft(**fields)


def _status(svc, oid: int) -> str:
    return svc.get_outreach(oid)["status"]


def test_save_draft_appends_signature_once(svc):
    out = _save(svc)
    assert out["status"] == OutreachStatus.DRAFT
    assert out["warnings"] == []
    assert out["body"].endswith("-- \nBhanu Teja\n+91 78938 81841\nlinkedin.com/in/bhanu-teja-kokkonda")
    assert out["body"].count("-- \n") == 1
    again = svc.edit_outreach(out["id"], body=out["body"])  # already signed: not doubled
    assert again["body"].count("-- \n") == 1


def test_save_draft_keeps_existing_contact_details(svc, tmp_db):
    tmp_db.save_contact(company="Acme", name="Priya Sharma", linkedin_url="linkedin.com/in/p")
    _save(svc)
    (contact,) = tmp_db.list_contacts("Acme")
    assert contact["linkedin_url"] == "linkedin.com/in/p"  # not blanked by an upsert


@pytest.mark.parametrize("bad", [
    "", "priya@acme", "priya@acme.com\nBcc: x@y.com", "Priya <priya@acme.com>",
    "pri ya@acme.com", "a@b@acme.com", "a,b@acme.com",
])
def test_save_draft_rejects_bad_addresses(svc, bad):
    assert "error" in _save(svc, to_email=bad)


def test_save_draft_rejects_multiline_subject_and_unknown_job(svc):
    assert "error" in _save(svc, subject="Hi\nBcc: x@y.com")
    assert "error" in _save(svc, job_id=999)


def test_save_draft_requires_a_name_in_the_profile(svc, tmp_db):
    tmp_db.set_applicant_profile(fields={"first_name": None, "last_name": None})
    assert "applicant profile" in _save(svc)["error"]


@pytest.mark.parametrize("confirm", [False, "yes", 1])
def test_send_without_exact_confirm_does_nothing(svc, confirm):
    oid = _save(svc)["id"]
    assert svc.send_outreach(oid, confirm=confirm) == {"error": "confirmation required"}
    assert _FakeSMTP.sent == []
    assert _status(svc, oid) == OutreachStatus.DRAFT


def test_send_happy_path(svc):
    oid = _save(svc)["id"]
    result = svc.send_outreach(oid, confirm=True)
    assert result["status"] == OutreachStatus.SENT and result["sent_at"]
    (msg,) = _FakeSMTP.sent
    assert (msg["To"], msg["From"]) == ("priya@acme.com", f"Bhanu Teja <{_ME}>")
    assert svc.get_outreach(oid)["message_id"] == msg["Message-ID"]


def test_send_is_exactly_once(svc):
    oid = _save(svc)["id"]
    svc.send_outreach(oid, confirm=True)
    second = svc.send_outreach(oid, confirm=True)
    assert "already sent" in second["error"]
    assert len(_FakeSMTP.sent) == 1


def test_smtp_failure_marks_failed_then_edit_and_resend(svc):
    oid = _save(svc)["id"]
    _FakeSMTP.error = smtplib.SMTPAuthenticationError(535, b"bad credentials")
    tree = logging.getLogger("job_hunt")
    records: list[logging.LogRecord] = []
    handler = logging.Handler()
    handler.emit = records.append  # type: ignore[method-assign]
    tree.addHandler(handler)
    try:
        result = svc.send_outreach(oid, confirm=True)
    finally:
        tree.removeHandler(handler)
    assert result == {"error": "send failed: SMTPAuthenticationError"}
    row = svc.get_outreach(oid)
    assert (row["status"], row["last_error"]) == (OutreachStatus.FAILED, "SMTPAuthenticationError")
    assert "error" not in row  # an "error" key would make the API report this row as a 400
    logged = " ".join(r.getMessage() for r in records)
    assert "send failed" in logged and _PASSWORD not in logged and "priya@acme.com" not in logged

    _FakeSMTP.error = None
    assert "error" not in svc.edit_outreach(oid, subject="Backend engineer, Acme payments")
    assert svc.send_outreach(oid, confirm=True)["status"] == OutreachStatus.SENT


def test_placeholder_blocks_send(svc):
    oid = _save(svc, body="Hi [Name],\n\nShort note.")["id"]
    assert "placeholder" in svc.send_outreach(oid, confirm=True)["error"]
    assert _FakeSMTP.sent == [] and _status(svc, oid) == OutreachStatus.DRAFT


def test_daily_cap(svc, monkeypatch):
    monkeypatch.setattr(svc, "DAILY_SEND_CAP", 2)
    ids = [_save(svc, contact_name=f"P{i}", to_email=f"p{i}@acme.com")["id"] for i in range(3)]
    assert svc.send_outreach(ids[0], confirm=True)["status"] == OutreachStatus.SENT
    assert svc.send_outreach(ids[1], confirm=True)["status"] == OutreachStatus.SENT
    assert "daily cap" in svc.send_outreach(ids[2], confirm=True)["error"]
    assert len(_FakeSMTP.sent) == 2


def test_send_requires_smtp_config(svc, monkeypatch):
    monkeypatch.delenv("EMAIL_SMTP_HOST")
    oid = _save(svc)["id"]
    assert "smtp not configured" in svc.send_outreach(oid, confirm=True)["error"]


def test_cancel(svc):
    oid = _save(svc)["id"]
    assert svc.cancel_outreach(oid)["status"] == OutreachStatus.CANCELLED
    assert "error" in svc.cancel_outreach(oid)
    assert "error" in svc.send_outreach(oid, confirm=True)
    assert "error" in svc.cancel_outreach(12345)


def test_sent_email_cannot_be_edited(svc):
    oid = _save(svc)["id"]
    svc.send_outreach(oid, confirm=True)
    assert "only draft or failed" in svc.edit_outreach(oid, subject="New")["error"]


def _sent_original(svc) -> int:
    oid = _save(svc)["id"]
    svc.send_outreach(oid, confirm=True)
    return oid


def _later(days: int) -> datetime:
    return datetime.now(UTC) + timedelta(days=days)


def test_follow_up_drafted_once_when_due(svc):
    original = _sent_original(svc)
    assert svc.draft_due_followups(now=_later(1))["drafted"] == 0  # not due yet
    first = svc.draft_due_followups(now=_later(7))
    assert first["drafted"] == 1
    follow_up = svc.get_outreach(first["ids"][0])
    assert follow_up["parent_id"] == original
    assert follow_up["subject"] == f"Re: {_CLEAN_SUBJECT}"
    assert follow_up["body"].startswith("Hi Priya,")
    assert "Thanks,\nBhanu\n\n-- \nBhanu Teja" in follow_up["body"]
    assert svc.draft_due_followups(now=_later(8))["drafted"] == 0  # never twice


def test_follow_up_threads_under_original(svc):
    original = _sent_original(svc)
    fid = svc.draft_due_followups(now=_later(7))["ids"][0]
    assert svc.send_outreach(fid, confirm=True)["status"] == OutreachStatus.SENT
    follow_msg = _FakeSMTP.sent[-1]
    assert follow_msg["In-Reply-To"] == svc.get_outreach(original)["message_id"]


def test_reply_stops_follow_ups(svc):
    original = _sent_original(svc)
    fid = svc.draft_due_followups(now=_later(7))["ids"][0]
    assert svc.record_replies(["PRIYA@acme.com"]) == 1
    assert _status(svc, original) == OutreachStatus.REPLIED
    assert _status(svc, fid) == OutreachStatus.CANCELLED
    assert svc.draft_due_followups(now=_later(9))["drafted"] == 0
    assert svc.record_replies([]) == 0


@contextmanager
def _fake_imap(*_args: Any):
    yield object()


def test_follow_up_guard_catches_unsynced_reply(svc, monkeypatch):
    original = _sent_original(svc)
    fid = svc.draft_due_followups(now=_later(7))["ids"][0]
    monkeypatch.setenv("EMAIL_IMAP_HOST", "imap.gmail.com")
    monkeypatch.setattr(svc.reader, "connect_imap", _fake_imap)
    monkeypatch.setattr(svc.reader, "has_reply_from", lambda conn, addr, since: True)
    assert "already replied" in svc.send_outreach(fid, confirm=True)["error"]
    assert len(_FakeSMTP.sent) == 1  # only the original
    assert _status(svc, original) == OutreachStatus.REPLIED
    assert _status(svc, fid) == OutreachStatus.CANCELLED


def test_follow_up_not_sent_when_inbox_check_fails(svc, monkeypatch):
    _sent_original(svc)
    fid = svc.draft_due_followups(now=_later(7))["ids"][0]
    monkeypatch.setenv("EMAIL_IMAP_HOST", "imap.gmail.com")

    @contextmanager
    def _broken(*_args: Any):
        raise OSError("network down")
        yield

    monkeypatch.setattr(svc.reader, "connect_imap", _broken)
    assert "could not check your inbox" in svc.send_outreach(fid, confirm=True)["error"]
    assert _status(svc, fid) == OutreachStatus.DRAFT
    assert len(_FakeSMTP.sent) == 1


# ---------- inbox sync → stop on reply (T6) ----------


def _fake_sync(svc, monkeypatch, from_addr: str) -> None:
    from job_hunt.email.reader import RawEmail
    from job_hunt.services import email_triage

    monkeypatch.setenv("EMAIL_IMAP_HOST", "imap.gmail.com")
    monkeypatch.setattr(email_triage.reader, "connect_imap", _fake_imap)
    monkeypatch.setattr(email_triage.reader, "select_mailbox", lambda conn, mailbox: (1, 2))
    reply = RawEmail(
        mailbox="INBOX", uid=1, message_id="<r1@acme.com>", thread_id=None,
        from_addr=from_addr, from_name="Priya", subject="Re: hello",
        received_at="2026-11-30T10:00:00+00:00", body_text="Happy to chat.",
    )
    monkeypatch.setattr(email_triage.reader, "fetch_new", lambda conn, mb, last, limit: [reply])


def test_inbox_sync_stops_follow_ups_for_people_who_replied(svc, monkeypatch):
    from job_hunt.services import email_triage

    original = _sent_original(svc)
    fid = svc.draft_due_followups(now=_later(7))["ids"][0]
    _fake_sync(svc, monkeypatch, "Priya@Acme.com")
    result = email_triage.sync_inbox()
    assert result == {"fetched": 1, "new": 1, "replied": 1}
    assert _status(svc, original) == OutreachStatus.REPLIED
    assert _status(svc, fid) == OutreachStatus.CANCELLED


def test_inbox_sync_survives_an_outreach_failure(svc, monkeypatch):
    from job_hunt.services import email_triage

    _fake_sync(svc, monkeypatch, "priya@acme.com")

    def _boom(_addrs: list[str]) -> int:
        raise RuntimeError("db hiccup")

    monkeypatch.setattr(email_triage, "record_replies", _boom)
    assert email_triage.sync_inbox() == {"fetched": 1, "new": 1, "replied": 0}


# ---------- CLI + MCP surfaces (T8) ----------


def _cli(*argv: str) -> int:
    from job_hunt.cli.main import build_parser

    args = build_parser().parse_args(list(argv))
    return args.func(args)


def test_cli_add_then_send_without_confirm_only_previews(svc, tmp_path, capsys):
    body = tmp_path / "body.txt"
    body.write_text("Hi Priya,\n\nShort note.\n\nThanks,\nBhanu", encoding="utf-8")
    assert _cli("outreach", "add", "--company", "Acme", "--name", "Priya Sharma",
                "--email", "priya@acme.com", "--subject", _CLEAN_SUBJECT,
                "--body-file", str(body)) == 0
    oid = svc.list_outreach()[0]["id"]
    assert f"hunt outreach send {oid} --confirm" in capsys.readouterr().out

    assert _cli("outreach", "send", str(oid)) == 1
    out = capsys.readouterr().out
    assert "Not sent." in out and "Subject: " + _CLEAN_SUBJECT in out
    assert _FakeSMTP.sent == [] and _status(svc, oid) == OutreachStatus.DRAFT

    assert _cli("outreach", "send", str(oid), "--confirm") == 0
    assert len(_FakeSMTP.sent) == 1


def test_cli_add_reports_unreadable_body_file(svc, tmp_path, capsys):
    assert _cli("outreach", "add", "--company", "Acme", "--name", "P", "--email", "p@acme.com",
                "--subject", "Hi", "--body-file", str(tmp_path / "missing.txt")) == 1
    assert "can't read" in capsys.readouterr().out


def test_mcp_can_save_and_list_but_never_send(svc):
    import asyncio

    from job_hunt.mcp_server import server

    names = {tool.name for tool in asyncio.run(server.mcp.list_tools())}
    assert {"outreach_save_draft", "outreach_list"} <= names
    assert not [n for n in names if "send" in n and "outreach" in n]  # no agent-callable send

    saved = server.outreach_save_draft("Acme", "Priya Sharma", "priya@acme.com",
                                       _CLEAN_SUBJECT, _CLEAN_BODY)
    assert saved["status"] == OutreachStatus.DRAFT
    assert [r["id"] for r in server.outreach_list("draft")] == [saved["id"]]


# ---------- CI follow-up drafting + notify (T9) ----------


class _StubNotifier:
    """Records messages instead of posting to Telegram."""

    def __init__(self) -> None:
        self.sent: list[str] = []

    def send(self, text: str) -> bool:
        self.sent.append(text)
        return True


def test_followups_notify_once_when_some_are_due(svc, monkeypatch):
    _sent_original(svc)
    monkeypatch.setattr(svc, "FOLLOWUP_AFTER_DAYS", 0)  # due immediately
    notifier = _StubNotifier()
    result = svc.draft_followups_and_notify(notifier)
    assert (result["drafted"], result["notified"]) == (1, True)
    (text,) = notifier.sent
    assert "1 cold-email follow-up(s) ready" in text
    assert "priya@acme.com" not in text and "Priya" not in text  # no recipient details in chat


def test_followups_stay_quiet_when_nothing_is_due(svc):
    _sent_original(svc)
    notifier = _StubNotifier()
    assert svc.draft_followups_and_notify(notifier) == {"drafted": 0, "ids": [], "notified": False}
    assert notifier.sent == []


def test_followups_without_profile_is_skipped_not_raised(svc, tmp_db):
    tmp_db.set_applicant_profile(fields={"first_name": None, "last_name": None})
    result = svc.draft_followups_and_notify(_StubNotifier())
    assert result["notified"] is False and "applicant profile" in result["error"]
