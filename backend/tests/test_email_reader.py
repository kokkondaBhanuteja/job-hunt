"""Tests for job_hunt.email.reader — hermetic, no real sockets.

Covers: multipart body preference, HTML tag stripping, RFC 2047 header
decoding, UID-echo filtering in fetch_new, and plain-text truncation.
"""
from __future__ import annotations

import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pytest

from job_hunt.email.reader import (
    RawEmail,
    _decode_header,
    _extract_plain_text,
    _html_to_text,
    fetch_new,
    select_mailbox,
)

# ---------------------------------------------------------------------------
# Fake IMAP — never touches a socket
# ---------------------------------------------------------------------------


class _FakeIMAP:
    """Minimal imaplib.IMAP4_SSL stand-in for unit tests."""

    def __init__(
        self,
        search_result: list[bytes],
        fetch_map: dict[str, list],
        uidvalidity: bytes = b"100",
        uidnext: bytes = b"200",
    ) -> None:
        self._search_result = search_result
        self._fetch_map = fetch_map  # uid_str → fetch data list
        self._uidvalidity = uidvalidity
        self._uidnext = uidnext
        self.selected_mailbox: str | None = None
        self.selected_readonly: bool | None = None
        self.last_search_args: tuple | None = None

    def select(self, mailbox: str, readonly: bool = False) -> tuple[str, list]:
        self.selected_mailbox = mailbox
        self.selected_readonly = readonly
        return ("OK", [b"10"])

    def response(self, code: str) -> tuple[str, list]:
        if code == "UIDVALIDITY":
            return ("UIDVALIDITY", [self._uidvalidity])
        if code == "UIDNEXT":
            return ("UIDNEXT", [self._uidnext])
        return (code, [None])

    def uid(self, command: str, *args) -> tuple[str, list]:
        if command == "SEARCH":
            self.last_search_args = args
            return ("OK", self._search_result)
        if command == "FETCH":
            uid_str = args[0] if args else ""
            data = self._fetch_map.get(uid_str, [])
            return ("OK", data)
        return ("OK", [None])


def _make_fetch_entry(uid: int, raw_email: bytes, thrid: str = "98765") -> list:
    """Build an imaplib-style fetch response for a single message."""
    header = (
        f"{uid} (UID {uid} X-GM-THRID {thrid} BODY[] {{{len(raw_email)}}})"
        .encode()
    )
    return [(header, raw_email), b")"]


# ---------------------------------------------------------------------------
# _decode_header
# ---------------------------------------------------------------------------


def test_decode_header_plain_string():
    assert _decode_header("Hello") == "Hello"


def test_decode_header_none_returns_none():
    assert _decode_header(None) is None


def test_decode_header_rfc2047_base64_utf8():
    encoded = "=?UTF-8?B?" + base64.b64encode("Héllo Wörld".encode()).decode() + "?="
    result = _decode_header(encoded)
    assert result == "Héllo Wörld"


def test_decode_header_rfc2047_quoted_printable():
    # =?UTF-8?Q?Subject_=E2=80=94_job?=  →  "Subject — job"
    encoded = "=?UTF-8?Q?Subject_=E2=80=94_job?="
    result = _decode_header(encoded)
    assert result == "Subject — job"


# ---------------------------------------------------------------------------
# _html_to_text
# ---------------------------------------------------------------------------


def test_html_to_text_strips_tags():
    result = _html_to_text("<p>Hello <b>World</b></p>")
    assert "Hello" in result
    assert "World" in result
    assert "<" not in result


def test_html_to_text_drops_script():
    result = _html_to_text("<p>Visible</p><script>alert('xss')</script><p>Also</p>")
    assert "Visible" in result
    assert "Also" in result
    assert "alert" not in result
    assert "xss" not in result


def test_html_to_text_drops_style():
    result = _html_to_text("<style>.cls { color: red; }</style><p>Text</p>")
    assert "Text" in result
    assert ".cls" not in result
    assert "color" not in result


def test_html_to_text_nested_script_ignored():
    """Nested script tags are tracked by depth and fully suppressed."""
    html = "<div><script><script>inner</script></script>After</div>"
    result = _html_to_text(html)
    assert "inner" not in result
    assert "After" in result


# ---------------------------------------------------------------------------
# _extract_plain_text
# ---------------------------------------------------------------------------


def test_extract_prefers_plain_in_multipart():
    msg = MIMEMultipart("alternative")
    msg.attach(MIMEText("plain content", "plain", "utf-8"))
    msg.attach(MIMEText("<b>html content</b>", "html", "utf-8"))
    result = _extract_plain_text(msg)
    assert result == "plain content"


def test_extract_html_fallback_when_no_plain():
    msg = MIMEMultipart("alternative")
    msg.attach(MIMEText("<p>Only HTML here</p><script>drop()</script>", "html", "utf-8"))
    result = _extract_plain_text(msg)
    assert "Only HTML here" in result
    assert "drop" not in result


def test_extract_single_plain_part():
    msg = MIMEText("Simple body", "plain", "utf-8")
    assert _extract_plain_text(msg) == "Simple body"


def test_extract_truncates_to_cap():
    long_text = "x" * 500
    msg = MIMEText(long_text, "plain", "utf-8")
    result = _extract_plain_text(msg, cap=100)
    assert len(result) == 100
    assert result == "x" * 100


def test_extract_empty_message_returns_empty_string():
    msg = MIMEMultipart()
    assert _extract_plain_text(msg) == ""


# ---------------------------------------------------------------------------
# select_mailbox
# ---------------------------------------------------------------------------


def test_select_mailbox_parses_uidvalidity_and_uidnext():
    imap = _FakeIMAP(
        search_result=[],
        fetch_map={},
        uidvalidity=b"12345",
        uidnext=b"67890",
    )
    uv, un = select_mailbox(imap, "INBOX")
    assert uv == 12345
    assert un == 67890
    assert imap.selected_mailbox == "INBOX"
    assert imap.selected_readonly is True


# ---------------------------------------------------------------------------
# fetch_new
# ---------------------------------------------------------------------------


def test_fetch_new_filters_uid_echo_of_last_uid():
    """UID n:* always returns at least n; fetch_new must not re-return it."""
    imap = _FakeIMAP(search_result=[b"5"], fetch_map={})
    result = fetch_new(imap, "INBOX", last_uid=5, limit=10)
    assert result == []


def test_fetch_new_empty_search_result():
    imap = _FakeIMAP(search_result=[b""], fetch_map={})
    result = fetch_new(imap, "INBOX", last_uid=10, limit=10)
    assert result == []


def test_fetch_new_builds_raw_email():
    msg = MIMEText("Hello from fetch", "plain", "utf-8")
    msg["From"] = "Alice Test <alice@example.com>"
    msg["Subject"] = "Test Subject"
    msg["Message-ID"] = "<abc123@mail.example.com>"
    msg["Date"] = "Mon, 01 Jan 2024 12:00:00 +0000"

    raw = msg.as_bytes()
    imap = _FakeIMAP(
        search_result=[b"5 6"],  # uid 5 echoed, uid 6 is new
        fetch_map={"6": _make_fetch_entry(6, raw, thrid="999")},
    )
    result = fetch_new(imap, "INBOX", last_uid=5, limit=10)

    assert len(result) == 1
    em = result[0]
    assert isinstance(em, RawEmail)
    assert em.uid == 6
    assert em.mailbox == "INBOX"
    assert em.from_addr == "alice@example.com"
    assert em.from_name == "Alice Test"
    assert em.subject == "Test Subject"
    assert em.message_id == "<abc123@mail.example.com>"
    assert em.thread_id == "999"
    assert em.body_text == "Hello from fetch"
    assert em.received_at is not None
    assert "2024-01-01" in em.received_at


def test_fetch_new_respects_limit():
    """fetch_new returns at most `limit` messages even if more UIDs are found."""
    # Build three new UIDs; limit=2 should give only the first two.
    msgs: dict[str, list] = {}
    for uid in (6, 7, 8):
        m = MIMEText(f"body {uid}", "plain", "utf-8")
        m["From"] = "x@x.com"
        m["Subject"] = f"s{uid}"
        m["Date"] = "Mon, 01 Jan 2024 12:00:00 +0000"
        msgs[str(uid)] = _make_fetch_entry(uid, m.as_bytes())

    imap = _FakeIMAP(search_result=[b"6 7 8"], fetch_map=msgs)
    result = fetch_new(imap, "INBOX", last_uid=5, limit=2)
    assert len(result) == 2
    assert {r.uid for r in result} == {6, 7}


def test_fetch_new_decoded_rfc2047_subject():
    """Subjects encoded with RFC 2047 are decoded in the returned RawEmail."""
    encoded_subj = "=?UTF-8?B?" + base64.b64encode(b"Job offer").decode() + "?="
    msg = MIMEText("body", "plain", "utf-8")
    msg["From"] = "hr@company.com"
    msg["Subject"] = encoded_subj
    msg["Date"] = "Mon, 01 Jan 2024 12:00:00 +0000"

    imap = _FakeIMAP(
        search_result=[b"6"],
        fetch_map={"6": _make_fetch_entry(6, msg.as_bytes())},
    )
    result = fetch_new(imap, "INBOX", last_uid=5, limit=10)
    assert len(result) == 1
    assert result[0].subject == "Job offer"


@pytest.mark.parametrize(
    ("search_bytes", "last_uid", "expected_uids"),
    [
        (b"10 11 12", 9, [10, 11, 12]),
        (b"9 10 11", 9, [10, 11]),   # uid 9 is the echo
        (b"9", 9, []),               # only the echo, no new mail
        (b"", 5, []),                # genuinely empty search
    ],
)
def test_fetch_new_uid_filtering_parametrized(
    search_bytes: bytes,
    last_uid: int,
    expected_uids: list[int],
):
    """Verify that only UIDs strictly greater than last_uid are fetched."""
    fetch_map: dict[str, list] = {}
    for u in expected_uids:
        m = MIMEText(f"body {u}", "plain", "utf-8")
        m["From"] = "x@x.com"
        m["Date"] = "Mon, 01 Jan 2024 12:00:00 +0000"
        fetch_map[str(u)] = _make_fetch_entry(u, m.as_bytes())

    imap = _FakeIMAP(
        search_result=[search_bytes] if search_bytes else [b""],
        fetch_map=fetch_map,
    )
    result = fetch_new(imap, "INBOX", last_uid=last_uid, limit=100)
    assert [r.uid for r in result] == expected_uids
